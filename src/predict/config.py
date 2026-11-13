"""예측 모듈 설정 로더 (config.yaml → PredictConfig)."""
from __future__ import annotations

from dataclasses import dataclass, fields
from pathlib import Path
from typing import Optional, Tuple, Union

import yaml

DEFAULT_CONFIG_PATH = Path(__file__).with_name("config.yaml")

# 사용할 수 있는 예측기 이름 (model.py 의 PREDICTORS 와 같은 키)
PREDICTOR_NAMES: Tuple[str, ...] = ("persistence", "linear", "flow")


@dataclass(frozen=True)
class PredictConfig:
    """60초 예측 설정. 값은 config.yaml 에서만 조정한다."""

    predictor: str = "persistence"
    history_s: int = 30          # 예측 입력 기간(초). meta.prediction.history_s 로 저장
    horizon_s: int = 60          # 예측 시점(초). meta.prediction.horizon_s 로 저장
    # flow 예측기 전용
    step_s: float = 5.0
    cfl_max: float = 0.5
    scheme: str = "tvd"
    flow_decay_tau_s: float = 120.0
    max_speed_cells_per_s: float = 3.0
    # 평가(evaluate) 전용: 이 면적(㎡) 이상인 셀만 모은 지표를 따로 낸다 (결정 2026-11-11 #4와 같은 기준)
    eval_min_cell_area_m2: float = 2.0

    def __post_init__(self) -> None:
        if self.predictor not in PREDICTOR_NAMES:
            raise ValueError("predictor 는 {} 중 하나여야 한다: {!r}".format(PREDICTOR_NAMES, self.predictor))
        if self.history_s < 2:
            raise ValueError("history_s 는 2 이상이어야 한다 (직선 추세에 2점 필요)")
        if self.horizon_s < 1:
            raise ValueError("horizon_s 는 1 이상이어야 한다")
        if self.step_s <= 0:
            raise ValueError("step_s 는 0보다 커야 한다")
        if not 0 < self.cfl_max <= 1:
            raise ValueError("cfl_max 는 (0, 1] 범위여야 한다")
        if self.scheme not in ("tvd", "upwind"):
            raise ValueError("scheme 은 'tvd' 또는 'upwind' 여야 한다: {!r}".format(self.scheme))
        if self.max_speed_cells_per_s <= 0:
            raise ValueError("max_speed_cells_per_s 는 0보다 커야 한다")
        if self.eval_min_cell_area_m2 < 0:
            raise ValueError("eval_min_cell_area_m2 는 0 이상이어야 한다")


def load_config(path: Optional[Union[str, Path]] = None) -> PredictConfig:
    """YAML 설정을 읽는다. 알 수 없는 키는 오타 방지를 위해 에러로 처리한다."""
    cfg_path = Path(path) if path else DEFAULT_CONFIG_PATH
    with open(cfg_path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    known = {f_.name for f_ in fields(PredictConfig)}
    unknown = set(raw) - known
    if unknown:
        raise ValueError("알 수 없는 설정 키: {}".format(sorted(unknown)))
    return PredictConfig(**raw)
