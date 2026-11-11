"""tests/predict 공용 fixture: 밀도 배열에서 규격 v0.1 Timeline 을 만든다."""
from typing import Callable, Optional

import numpy as np
import pytest

from src.predict.schema import (
    SCHEMA_VERSION, CellMeta, CellState, Frame, Meta, Models, Prediction, Timeline,
)

CELL_M = 2.0


@pytest.fixture
def make_timeline() -> Callable[..., Timeline]:
    """make_timeline(dens, vx=None, vy=None, area=None, ...) -> Timeline.

    dens: (T, rows, cols) 밀도 배열. vx, vy: 모든 셀에 넣을 속도(m/s), None 이면 null.
    area: (rows, cols) 보행 가능 면적(기본 CELL_M²). 예측값은 비어 있다.
    """

    def build(
        dens: np.ndarray,
        vx: Optional[float] = None,
        vy: Optional[float] = None,
        area: Optional[np.ndarray] = None,
        history_s: int = 30,
        horizon_s: int = 60,
        interval_s: int = 1,
    ) -> Timeline:
        steps, rows, cols = dens.shape
        area = np.full((rows, cols), CELL_M ** 2) if area is None else area
        cells_meta = [
            CellMeta(
                cell_id="c-{:02d}{:02d}".format(r, c), row=r, col=c,
                walkable_area_m2=float(area[r, c]),
                image_polygon=[(c / cols, r / rows), ((c + 1) / cols, r / rows),
                               ((c + 1) / cols, (r + 1) / rows), (c / cols, (r + 1) / rows)],
            )
            for r in range(rows) for c in range(cols)
        ]
        meta = Meta(
            zone_id="z", camera_id="cam", video_id="V", duration_s=steps, interval_s=interval_s,
            cell_size_m=CELL_M, models=Models("test", "test", "none"),
            prediction=Prediction(history_s, horizon_s), cells=cells_meta,
        )
        frames = [
            Frame(t=t, inflow_ratio=None, cells=[
                CellState(cm.cell_id, float(dens[t, cm.row, cm.col]), vx, vy, None, None, None)
                for cm in cells_meta
            ])
            for t in range(steps)
        ]
        return Timeline(meta=meta, frames=frames, schema_version=SCHEMA_VERSION)

    return build
