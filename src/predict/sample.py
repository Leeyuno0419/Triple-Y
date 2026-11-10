"""개발용 샘플 timeline 생성 (관측 프레임 + 흐름). 실제 데이터 연동 전 파이프라인/화면 확인용.

인파 덩어리가 동쪽(+col)으로 이동하고, 오른쪽 열들은 화각 밖(NaN)이다.
마지막 관측 시점에 덩어리가 화각 경계에 걸쳐 있어, 예측에서 화각 밖으로 넘어가는 모습이 보인다.

    python -m src.predict.sample --output data/processed/timeline.sample.json
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Sequence

import numpy as np

from .io import save_timeline
from .schema import SCHEMA_VERSION, Bounds, Frame, Timeline, ZoneFrame, ZoneMeta

ROWS, COLS, CELL_M, VISIBLE_COLS = 8, 12, 12.0, 8
CENTER_LAT, CENTER_LNG = 37.5663, 126.9779   # 서울시청 (web/src/config/app.ts 와 동일)
SPEED_CELLS_PER_S = 0.05
FRAME_INTERVAL_S = 30


def make_sample_timeline(n_frames: int = 5, peak: float = 6.2) -> Timeline:  # 셀 최대 ≈5.4명/m² (기획서 3.2 "심각")
    d_lat = (ROWS * CELL_M / 2) / 111_320
    d_lng = (COLS * CELL_M / 2) / (111_320 * np.cos(np.radians(CENTER_LAT)))
    zone = ZoneMeta(
        zone_id="Z01", name="샘플 구역 (predict.sample)",
        bounds=Bounds(CENTER_LAT - d_lat, CENTER_LNG - d_lng, CENTER_LAT + d_lat, CENTER_LNG + d_lng),
        rows=ROWS, cols=COLS, cell_size_m=CELL_M,
    )

    rr, cc = np.mgrid[0:ROWS, 0:COLS]
    visible = cc < VISIBLE_COLS
    kst = timezone(timedelta(hours=9))
    now = datetime.now(kst).replace(microsecond=0)

    frames: List[Frame] = []
    for i in range(n_frames):
        center = 1.5 + i * SPEED_CELLS_PER_S * FRAME_INTERVAL_S
        dens = peak * np.exp(-((cc - center) ** 2 / 4.0 + (rr - 3.5) ** 2 / 3.0))
        dens = np.where(visible, dens, np.nan)
        u = np.where(visible, SPEED_CELLS_PER_S, np.nan)
        v = np.where(visible, 0.0, np.nan)
        count = float(np.nansum(dens) * zone.cell_area_m2)
        t = (now + timedelta(seconds=(i - n_frames + 1) * FRAME_INTERVAL_S)).isoformat()
        frames.append(Frame(t=t, kind="observed", zones=[ZoneFrame("Z01", dens, u, v, count)]))

    return Timeline(SCHEMA_VERSION, [zone], frames)


def main(argv: Optional[Sequence[str]] = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--output", required=True)
    args = ap.parse_args(argv)
    save_timeline(make_sample_timeline(), args.output)
    print("저장 완료:", args.output)


if __name__ == "__main__":
    main()
