"""화각 밖 예측 모델.

BasePredictor 인터페이스를 두어 이후 학습 기반 모델(ConvLSTM, GNN 등)로 교체할 수 있게 한다.
기본 구현 FlowExtrapolationPredictor 는 학습 없이 "마지막 관측의 흐름을 외삽"한다:

    1) 화각 밖 셀의 초기 밀도는 화각 경계 밀도를 바깥으로 감쇠 연장(prior_mode=extend, 기본)하거나
       고정 prior 로 두고(constant), 흐름은 화각 경계에서 바깥으로 번져 채운다.
       ※ extend 는 관측되지 않은 인원을 "추정"해 더하므로, 예측 count 는 마지막 관측 count 보다 클 수 있다.
    2) 흐름 속도는 exp(-t/tau) 로 감쇠시키며 밀도를 이류(기본 2차 TVD)로 이동시킨다.
    3) 요청된 horizon 마다 밀도 격자와 구역 합계를 기록한다.

TODO: 구역 경계를 넘어 유출된 인원을 인접 구역으로 넘기는 처리 (구역 그래프 필요).
"""
from __future__ import annotations

import math
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Sequence

import numpy as np

from .config import PredictConfig
from .extrapolate import advect_density, extend_density_outside_view, fill_flow_outside_view
from .schema import ZoneFrame, ZoneMeta


@dataclass
class ZonePrediction:
    zone_id: str
    horizon_s: float
    density: np.ndarray        # (rows, cols) 명/m² — 화각 밖 셀도 값이 채워진다
    count: float               # 구역 합계(명)
    outflow_count: float       # 구역 경계 밖으로 누적 유출된 인원(명)
    extrapolated: np.ndarray   # (rows, cols) bool — 관측이 아닌 외삽으로 채운 셀


class BasePredictor(ABC):
    """모든 예측 모델의 공통 인터페이스."""

    @abstractmethod
    def predict(
        self, meta: ZoneMeta, frame: ZoneFrame, horizons_s: Sequence[float]
    ) -> List[ZonePrediction]:
        """마지막 관측 frame 으로부터 horizons_s 각 시점의 상태를 예측한다."""


class FlowExtrapolationPredictor(BasePredictor):
    def __init__(self, config: PredictConfig) -> None:
        self.cfg = config

    def predict(
        self, meta: ZoneMeta, frame: ZoneFrame, horizons_s: Sequence[float]
    ) -> List[ZonePrediction]:
        cfg = self.cfg
        visible = np.isfinite(frame.density)
        density = self.initial_density(frame)

        u0 = frame.flow_u if frame.flow_u is not None else np.zeros_like(density)
        v0 = frame.flow_v if frame.flow_v is not None else np.zeros_like(density)
        u0 = np.clip(u0, -cfg.max_speed_cells_per_s, cfg.max_speed_cells_per_s)
        v0 = np.clip(v0, -cfg.max_speed_cells_per_s, cfg.max_speed_cells_per_s)
        u0, v0 = fill_flow_outside_view(
            u0, v0, visible, decay=cfg.outside_flow_decay, max_iters=cfg.outside_flow_max_iters
        )

        area = meta.cell_area_m2
        results: List[ZonePrediction] = []
        t = 0.0
        outflow_density = 0.0

        for horizon in sorted(set(float(h) for h in horizons_s)):
            while t < horizon - 1e-9:
                dt = min(cfg.step_s, horizon - t)
                damp = self._damping(t + dt / 2.0)
                density, out = advect_density(
                    density, u0 * damp, v0 * damp, dt, cfg.cfl_max, cfg.scheme
                )
                outflow_density += out
                t += dt
            results.append(
                ZonePrediction(
                    zone_id=frame.zone_id,
                    horizon_s=horizon,
                    density=density.copy(),
                    count=float(density.sum() * area),
                    outflow_count=float(outflow_density * area),
                    extrapolated=~visible,
                )
            )
        return results

    def initial_density(self, frame: ZoneFrame) -> np.ndarray:
        """예측 시작 시점의 전체 격자 밀도: 관측 셀은 그대로, 화각 밖은 prior_mode 에 따라 채운다.
        (이동 없이 이것만 쓰면 "정지 가정" 기준선이 되어 평가 때 비교 대상으로 쓴다.)"""
        cfg = self.cfg
        visible = np.isfinite(frame.density)
        if cfg.prior_mode == "extend":
            return extend_density_outside_view(
                frame.density, visible, cfg.extend_decay, cfg.extend_max_cells, cfg.prior_density
            )
        return np.where(visible, frame.density, cfg.prior_density).astype(float)

    def _damping(self, t: float) -> float:
        tau = self.cfg.flow_decay_tau_s
        return 1.0 if tau <= 0 else math.exp(-t / tau)
