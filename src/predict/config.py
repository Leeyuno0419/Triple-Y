"""예측 모듈 설정 로더 (config.yaml → PredictConfig)."""
from __future__ import annotations

from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import List, Optional, Union

import yaml

DEFAULT_CONFIG_PATH = Path(__file__).with_name("config.yaml")


@dataclass(frozen=True)
class PredictConfig:
    horizons_s: List[float] = field(default_factory=lambda: [30.0, 60.0, 120.0, 300.0])
    step_s: float = 5.0
    cfl_max: float = 0.5
    scheme: str = "tvd"
    flow_decay_tau_s: float = 120.0
    outside_flow_decay: float = 0.9
    outside_flow_max_iters: int = 50
    prior_mode: str = "extend"
    prior_density: float = 0.0
    extend_decay: float = 0.8
    extend_max_cells: int = 3
    max_speed_cells_per_s: float = 3.0

    def __post_init__(self) -> None:
        if self.step_s <= 0:
            raise ValueError("step_s 는 0보다 커야 한다")
        if not 0 < self.cfl_max <= 1:
            raise ValueError("cfl_max 는 (0, 1] 범위여야 한다")
        if self.scheme not in ("tvd", "upwind"):
            raise ValueError("scheme 은 'tvd' 또는 'upwind' 여야 한다: {!r}".format(self.scheme))
        if self.prior_mode not in ("extend", "constant"):
            raise ValueError("prior_mode 는 'extend' 또는 'constant' 여야 한다: {!r}".format(self.prior_mode))
        if not 0 <= self.extend_decay <= 1:
            raise ValueError("extend_decay 는 [0, 1] 범위여야 한다")
        if self.extend_max_cells < 0:
            raise ValueError("extend_max_cells 는 0 이상이어야 한다")
        if self.prior_density < 0:
            raise ValueError("prior_density 는 0 이상이어야 한다")
        if not self.horizons_s or any(h <= 0 for h in self.horizons_s):
            raise ValueError("horizons_s 는 양수 리스트여야 한다")


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
