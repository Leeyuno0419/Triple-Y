"""개발용 샘플 timeline 생성 (규격 v0.1, 합성 데이터). 실제 데이터 연동 전 파이프라인/화면 확인용.

인파 덩어리가 동쪽(+col)으로 일정 속도로 이동한다. 1초 간격 프레임이며 예측값(density_pred_60s)은 비어 있다.
빈 셀(밀도 0)은 규격대로 density·pressure = 0, vx·vy·speed_var = null 로 둔다.

    python -m src.predict.sample --output data/processed/timeline/SAMPLE.json
"""
from __future__ import annotations

import argparse
from typing import List, Optional, Sequence

import numpy as np

from .io import save_timeline
from .schema import (
    SCHEMA_VERSION, CellMeta, CellState, Frame, Meta, Models, Prediction, Timeline,
)

ROWS, COLS, CELL_M = 6, 10, 2.0
HISTORY_S, HORIZON_S = 30, 60
SPEED_CELLS_PER_S = 0.05            # 덩어리 이동 속도 (셀/초)
SPEED_VAR = 0.004                   # 점유 셀의 속도 분산 (m²/s²)
PEAK = 6.2                          # 셀 최대 밀도(명/㎡), 기획서 3.2 "심각" 수준


def _cell_id(row: int, col: int) -> str:
    return "c-{:02d}{:02d}".format(row, col)


def make_sample_timeline(duration_s: int = 150, peak: float = PEAK) -> Timeline:
    """덩어리가 동쪽으로 이동하는 합성 timeline 을 만든다 (프레임 duration_s 개)."""
    cells_meta: List[CellMeta] = []
    for r in range(ROWS):
        for c in range(COLS):
            x0, x1, y0, y1 = c / COLS, (c + 1) / COLS, r / ROWS, (r + 1) / ROWS
            cells_meta.append(
                CellMeta(
                    cell_id=_cell_id(r, c), row=r, col=c,
                    walkable_area_m2=CELL_M ** 2 * (0.8 if r == 0 else 1.0),  # 첫 행은 보행 면적이 작다
                    image_polygon=[(x0, y0), (x1, y0), (x1, y1), (x0, y1)],
                )
            )
    meta = Meta(
        zone_id="zone-sample", camera_id="cam-sample", video_id="SAMPLE",
        duration_s=duration_s, interval_s=1, cell_size_m=CELL_M,
        models=Models(counter="synthetic", flow="synthetic", predictor="none"),
        prediction=Prediction(history_s=HISTORY_S, horizon_s=HORIZON_S),
        cells=cells_meta,
    )

    rr, cc = np.mgrid[0:ROWS, 0:COLS]
    vx_ms = SPEED_CELLS_PER_S * CELL_M
    frames: List[Frame] = []
    for t in range(duration_s):
        center = 1.5 + SPEED_CELLS_PER_S * t
        dens = np.round(peak * np.exp(-((cc - center) ** 2 / 4.0 + (rr - 2.5) ** 2 / 3.0)), 2)
        cells: List[CellState] = []
        for cm in cells_meta:
            d = float(dens[cm.row, cm.col])
            if d > 0:
                cells.append(CellState(cm.cell_id, d, vx_ms, 0.0, SPEED_VAR, d * SPEED_VAR, None))
            else:
                cells.append(CellState(cm.cell_id, 0.0, None, None, None, 0.0, None))
        frames.append(Frame(t=t, inflow_ratio=round(min(0.1 + 0.002 * t, 0.4), 4), cells=cells))

    return Timeline(meta=meta, frames=frames, schema_version=SCHEMA_VERSION)


def main(argv: Optional[Sequence[str]] = None) -> None:
    """CLI 진입점."""
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--output", required=True)
    ap.add_argument("--duration", type=int, default=150, help="분석 길이(초). 예측을 보려면 90 이상")
    args = ap.parse_args(argv)
    save_timeline(make_sample_timeline(args.duration), args.output)
    print("저장 완료:", args.output)


if __name__ == "__main__":
    main()
