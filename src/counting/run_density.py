"""영상을 1초마다 P2PNet으로 세어 셀 밀도 timeline.json을 만든다 (G1: meta, t, density).

    python -m src.counting.run_density --homography infra/homography/E04_039.json \
        --video data/processed/g1/E04_039.mp4 --out data/processed/timeline/E04_039.json

머리 점은 머리 높이 평면 행렬(head_plane)로 지면에 옮긴 뒤 셀마다 센다.
머리 좌표는 메모리에서만 쓰고 저장하지 않는다. 저장하는 값은 셀 밀도와 초별 구역 인원(집계)뿐이다.
흐름·예측 필드는 아직 만들지 않았으므로 null로 둔다 (규격 6절 G1 단계).
"""
from __future__ import annotations

import argparse
import csv
import json
import time
from pathlib import Path

import cv2
import numpy as np

from src.counting.cells import build_cells, image_to_ground
from src.counting.eval_e1 import WEIGHTS, head_points, load_p2pnet
from src.predict.schema import SCHEMA_VERSION, validate_timeline

ROOT = Path(__file__).resolve().parents[2]


def count_cells(ground_pts: np.ndarray, cells: list[dict[str, object]],
                origin_m: tuple[float, float], cell_m: float) -> np.ndarray:
    """지면 좌표 점들을 셀(row, col)에 넣어 셀별 인원을 센다. 셀 밖 점은 버린다."""
    index = {(c["row"], c["col"]): i for i, c in enumerate(cells)}
    counts = np.zeros(len(cells), int)
    rc = np.floor((ground_pts - origin_m) / cell_m).astype(int)
    for col, row in rc:
        i = index.get((row, col))
        if i is not None:
            counts[i] += 1
    return counts


def main() -> None:
    """영상 전체를 1초 간격으로 처리해 timeline.json과 초별 구역 인원 CSV를 저장한다."""
    ap = argparse.ArgumentParser()
    ap.add_argument("--homography", required=True)
    ap.add_argument("--video", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--limit", type=int, default=0, help="앞에서 몇 초만 (빠른 확인용)")
    ap.add_argument("--scale", type=float, default=0.4, help="P2PNet 입력 축소 배율 (머리 크기 맞춤)")
    ap.add_argument("--threshold", type=float, default=0.4, help="머리 점 점수 기준")
    args = ap.parse_args()

    cfg = json.loads(Path(args.homography).read_text(encoding="utf-8"))
    h_ground = np.array(cfg["H_img_to_ground"])
    h_head = np.array(cfg["head_plane"]["H_head_img_to_ground"])
    origin, cell_m = tuple(cfg["cell_origin_m"]), 2.0

    cap = cv2.VideoCapture(args.video)
    fps = cap.get(cv2.CAP_PROP_FPS)
    size = (int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)))
    duration = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) / fps)
    if args.limit:
        duration = min(duration, args.limit)
    cells = build_cells(h_ground, cfg["walkable_polygon_px"], size, cell_m, origin_m=origin)
    areas = np.array([c["walkable_area_m2"] for c in cells])

    model = load_p2pnet(WEIGHTS)
    frames, rows, start = [], [], time.time()
    idx, t = 0, 0
    while t < duration:
        ok = cap.grab()
        if not ok:
            break
        if idx == round(t * fps):
            _, frame = cap.retrieve()
            pts = head_points(model, frame, args.scale, args.threshold)
            counts = count_cells(image_to_ground(h_head, pts), cells, origin, cell_m) if len(pts) \
                else np.zeros(len(cells), int)
            dens = np.round(counts / areas, 2)
            frames.append({"t": t, "inflow_ratio": None, "cells": [
                {"cell_id": c["cell_id"], "density": float(d), "vx": None, "vy": None,
                 "speed_var": None, "pressure": None, "density_pred_60s": None}
                for c, d in zip(cells, dens)]})
            rows.append((t, int(counts.sum()), len(pts)))
            print(f"t={t:3d}s 구역 {counts.sum():3d}명 / 화면 전체 {len(pts):3d}명", flush=True)
            t += 1
        idx += 1

    vid = cfg["video"]
    timeline = validate_timeline({
        "schema_version": SCHEMA_VERSION,
        "meta": {
            "zone_id": f"zone-{vid.lower().replace('_', '-')}",
            "camera_id": f"cam-{vid.lower().replace('_', '-')}",
            "video_id": vid, "duration_s": len(frames), "interval_s": 1, "cell_size_m": cell_m,
            "models": {"counter": f"p2pnet-vgg16 x{args.scale} th{args.threshold}",
                       "flow": "none", "predictor": "none"},
            "prediction": {"history_s": 30, "horizon_s": 60},
            "cells": cells,
        },
        "frames": frames,
    })
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(timeline, ensure_ascii=False), encoding="utf-8")

    stat = ROOT / "outputs" / "g1" / f"{vid}_counts.csv"
    stat.parent.mkdir(parents=True, exist_ok=True)
    with open(stat, "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows([("t", "zone_count", "frame_count"), *rows])
    el = time.time() - start
    print(f"저장: {out}, {stat} ({len(frames)}초, 셀 {len(cells)}개, {el:.0f}초 소요)")


if __name__ == "__main__":
    main()
