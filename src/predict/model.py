"""60초 밀도 예측 모델 (timeline.json 규격 v0.1).

매 초 t 마다 "t 까지의 최근 history_s 초 밀도 기록"만 보고 셀별 ρ(t + horizon_s) 를 예측해
frames[t].cells[].density_pred_60s 에 채운다. t 이후 값은 절대 쓰지 않는다 (E6 결과가 무효가 되므로).

예측기 (config.predictor)
    persistence : 현재값 유지 (기준선, 규격 예시의 기본값)
    linear      : 최근 history_s 초 밀도의 최소제곱 직선을 horizon 만큼 연장 (기준선)
    flow        : 현재 셀별 인원을 vx, vy 로 이류시켜 이동 (extrapolate.advect_density)

BasePredictor 인터페이스를 두어 이후 학습 기반 모델로 교체할 수 있게 한다.

flow 예측기의 가정·한계
    - 속도 방향: vx > 0 → col 증가, vy > 0 → row 증가 (영상 좌표: x 오른쪽, y 아래). 규격 문서에 정의가 없어 가정이다.
    - 이류 대상은 밀도가 아니라 셀별 인원수(밀도 × 보행 가능 면적)다. 면적이 다른 셀 사이에서도 인원이 보존된다.
    - meta.cells 에 없는 칸(보행 불가)으로 흘러간 인원은 사라진다.
TODO: 구역 경계를 넘어 유출된 인원을 인접 구역으로 넘기는 처리 (구역 그래프 필요).
"""
from __future__ import annotations

import math
from abc import ABC, abstractmethod
from dataclasses import dataclass, replace
from typing import Dict, List, Optional, Tuple, Type

import numpy as np

from .config import PredictConfig
from .extrapolate import advect_density
from .schema import Frame, Meta, Prediction, Timeline


# --------------------------------------------------------------------------- #
# 셀 배치 / 배열 변환
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class CellLayout:
    """meta.cells 순서를 따르는 셀 배치. 배열의 k 번째 값 = meta.cells[k]."""

    rows: int
    cols: int
    cell_size_m: float
    row: np.ndarray        # (N,) int
    col: np.ndarray        # (N,) int
    area_m2: np.ndarray    # (N,) 보행 가능 면적

    @classmethod
    def from_meta(cls, meta: Meta) -> "CellLayout":
        """Meta 에서 격자 크기와 셀 위치·면적 배열을 만든다."""
        if not meta.cells:
            raise ValueError("meta.cells 가 비어 있다")
        row = np.array([c.row for c in meta.cells], dtype=int)
        col = np.array([c.col for c in meta.cells], dtype=int)
        area = np.array([c.walkable_area_m2 for c in meta.cells], dtype=float)
        return cls(int(row.max()) + 1, int(col.max()) + 1, float(meta.cell_size_m), row, col, area)


def require_unit_interval(meta: Meta) -> None:
    """MVP 는 1초 간격(interval_s = 1)만 지원한다. history_s·horizon_s 를 프레임 개수로 그대로 쓰기 때문이다."""
    if meta.interval_s != 1:
        raise ValueError("interval_s={} 는 지원하지 않는다 (MVP 는 1초 간격만)".format(meta.interval_s))


def _nan(v: Optional[float]) -> float:
    """None 을 NaN 으로 바꾼다."""
    return float("nan") if v is None else float(v)


def to_arrays(timeline: Timeline) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(density, vx, vy) 를 각각 (T, N) 배열로 바꾼다. null 은 NaN. 열 순서는 meta.cells."""
    ids = [c.cell_id for c in timeline.meta.cells]
    n, total = len(ids), len(timeline.frames)
    dens = np.full((total, n), np.nan)
    vx = np.full((total, n), np.nan)
    vy = np.full((total, n), np.nan)
    for t, fr in enumerate(timeline.frames):
        by_id = {c.cell_id: c for c in fr.cells}
        if len(by_id) != n or any(i not in by_id for i in ids):
            raise ValueError("t={}: frames.cells 가 meta.cells 와 다르다".format(fr.t))
        for k, cid in enumerate(ids):
            c = by_id[cid]
            dens[t, k], vx[t, k], vy[t, k] = c.density, _nan(c.vx), _nan(c.vy)
    return dens, vx, vy


# --------------------------------------------------------------------------- #
# 예측기
# --------------------------------------------------------------------------- #
class BasePredictor(ABC):
    """모든 예측 모델의 공통 인터페이스."""

    name: str = ""

    def __init__(self, config: PredictConfig) -> None:
        self.cfg = config

    @abstractmethod
    def predict(
        self, layout: CellLayout, density_hist: np.ndarray, vx: np.ndarray, vy: np.ndarray
    ) -> np.ndarray:
        """현재 시각 t 까지의 기록으로 셀별 ρ(t + horizon_s) 를 예측한다.

        density_hist: (T, N) 최근 밀도 기록 (마지막 행 = 현재 시각 t, T = history_s)
        vx, vy      : (N,) 현재 시각 t 의 셀 평균 속도(m/s). 값이 없으면 NaN
        반환값      : (N,) 예측 밀도(명/㎡), 0 이상
        """


class PersistencePredictor(BasePredictor):
    """현재값 유지: 60초 뒤에도 지금 밀도 그대로라고 본다. 모델이 이겨야 하는 기준선."""

    name = "persistence"

    def predict(
        self, layout: CellLayout, density_hist: np.ndarray, vx: np.ndarray, vy: np.ndarray
    ) -> np.ndarray:
        return np.clip(np.asarray(density_hist[-1], dtype=float), 0.0, None)


class LinearTrendPredictor(BasePredictor):
    """직선 추세: 최근 기록에 최소제곱 직선을 맞춰 horizon 만큼 연장한다. 기준선."""

    name = "linear"

    def predict(
        self, layout: CellLayout, density_hist: np.ndarray, vx: np.ndarray, vy: np.ndarray
    ) -> np.ndarray:
        y = np.asarray(density_hist, dtype=float)
        steps = y.shape[0]
        if steps < 2:
            return np.clip(y[-1], 0.0, None)
        x = np.arange(steps, dtype=float) - (steps - 1)        # 현재 시각 = 0
        xm = x.mean()
        xc = x - xm
        slope = (xc[:, None] * y).sum(axis=0) / float((xc ** 2).sum())
        at_now = y.mean(axis=0) - slope * xm                    # 맞춘 직선의 현재 값
        return np.clip(at_now + slope * self.cfg.horizon_s, 0.0, None)


class FlowAdvectionPredictor(BasePredictor):
    """흐름 이류: 현재 셀별 인원을 (vx, vy) 로 horizon 만큼 이동시킨다 (속도는 exp(-t/tau) 로 감쇠)."""

    name = "flow"

    def predict(
        self, layout: CellLayout, density_hist: np.ndarray, vx: np.ndarray, vy: np.ndarray
    ) -> np.ndarray:
        cfg = self.cfg
        row, col = layout.row, layout.col
        counts = np.zeros((layout.rows, layout.cols))
        counts[row, col] = np.asarray(density_hist[-1], dtype=float) * layout.area_m2

        # m/s → 셀/초. 값이 없는 셀은 정지로 본다.
        lim = cfg.max_speed_cells_per_s
        u = np.zeros_like(counts)
        v = np.zeros_like(counts)
        u[row, col] = np.clip(np.nan_to_num(vx) / layout.cell_size_m, -lim, lim)
        v[row, col] = np.clip(np.nan_to_num(vy) / layout.cell_size_m, -lim, lim)

        t = 0.0
        horizon = float(cfg.horizon_s)
        while t < horizon - 1e-9:
            dt = min(cfg.step_s, horizon - t)
            damp = self._damping(t + dt / 2.0)
            counts, _ = advect_density(counts, u * damp, v * damp, dt, cfg.cfl_max, cfg.scheme)
            t += dt
        return np.clip(counts[row, col] / layout.area_m2, 0.0, None)

    def _damping(self, t: float) -> float:
        tau = self.cfg.flow_decay_tau_s
        return 1.0 if tau <= 0 else math.exp(-t / tau)


PREDICTORS: Dict[str, Type[BasePredictor]] = {
    PersistencePredictor.name: PersistencePredictor,
    LinearTrendPredictor.name: LinearTrendPredictor,
    FlowAdvectionPredictor.name: FlowAdvectionPredictor,
}


def make_predictor(config: PredictConfig) -> BasePredictor:
    """config.predictor 이름에 해당하는 예측기를 만든다."""
    return PREDICTORS[config.predictor](config)


# --------------------------------------------------------------------------- #
# timeline 에 예측 채우기
# --------------------------------------------------------------------------- #
def fill_predictions(timeline: Timeline, predictor: BasePredictor) -> Timeline:
    """모든 프레임의 density_pred_60s 를 채운 새 Timeline 을 반환한다 (입력은 변경하지 않음).

    - t < history_s - 1 (입력이 부족한 구간)은 null 로 둔다. 기존 값이 있어도 지운다.
    - t 의 예측에는 frames[t - history_s + 1 .. t] 만 쓴다.
    - meta.models.predictor 와 meta.prediction 을 이 예측기·설정 값으로 갱신한다.
    """
    cfg = predictor.cfg
    require_unit_interval(timeline.meta)
    layout = CellLayout.from_meta(timeline.meta)
    dens, vx, vy = to_arrays(timeline)

    frames: List[Frame] = []
    for t, fr in enumerate(timeline.frames):
        if t >= cfg.history_s - 1:
            lo = t - cfg.history_s + 1
            pred = predictor.predict(layout, dens[lo:t + 1], vx[t], vy[t])
            preds: List[Optional[float]] = [float(p) for p in pred]
        else:
            preds = [None] * len(timeline.meta.cells)
        by_id = {c.cell_id: p for c, p in zip(timeline.meta.cells, preds)}
        cells = [replace(c, density_pred_60s=by_id[c.cell_id]) for c in fr.cells]
        frames.append(Frame(t=fr.t, inflow_ratio=fr.inflow_ratio, cells=cells))

    meta = replace(
        timeline.meta,
        models=replace(timeline.meta.models, predictor=predictor.name),
        prediction=Prediction(history_s=cfg.history_s, horizon_s=cfg.horizon_s),
    )
    return Timeline(meta=meta, frames=frames, schema_version=timeline.schema_version)
