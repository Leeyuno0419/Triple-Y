"""영상을 1초마다 P2PNet으로 세어 셀 밀도 timeline.json을 만든다 (G1: meta, t, density).

    python -m src.counting.run_density --homography infra/homography/E04_039.json \
        --video data/processed/g1/E04_039.mp4 --out data/processed/timeline/E04_039.json

머리 점은 머리 높이 평면 행렬(head_plane)로 지면에 옮긴 뒤 셀마다 센다.
초마다 앞뒤 window_s초 안의 avg_frames장을 세어 평균한다. 사람이 움직이면 장마다 가려지는 사람이
달라 한 장만 세면 들쭉날쭉하다. 축소 배율·판정 기준·평균 장수는 구역 설정의 counter(E2로 정함)를 쓴다.
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
    args = ap.parse_args()

    cfg = json.loads(Path(args.homography).read_text(encoding="utf-8"))
    h_ground = np.array(cfg["H_img_to_ground"])
    h_head = np.array(cfg["head_plane"]["H_head_img_to_ground"])
    origin, cell_m = tuple(cfg["cell_origin_m"]), 2.0
    ctr = cfg["counter"]
    scale, threshold = ctr["scale"], ctr["threshold"]
    offsets = np.linspace(-ctr["window_s"], ctr["window_s"], ctr["avg_frames"])

    cap = cv2.VideoCapture(args.video)
    fps = cap.get(cv2.CAP_PROP_FPS)
    n_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    size = (int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)))
    duration = int(n_frames / fps)
    if args.limit:
        duration = min(duration, args.limit)
    cells = build_cells(h_ground, cfg["walkable_polygon_px"], size, cell_m, origin_m=origin)
    areas = np.array([c["walkable_area_m2"] for c in cells])

    # 프레임 번호 -> 그 프레임을 쓰는 초들 (영상 앞뒤 끝은 안쪽으로 자른다)
    need: dict[int, list[int]] = {}
    for t in range(duration):
        for off in offsets:
            need.setdefault(int(np.clip(round((t + off) * fps), 0, n_frames - 1)), []).append(t)
    acc = np.zeros((duration, len(cells)))
    used = np.zeros(duration)
    frame_total = np.zeros(duration)

    model = load_p2pnet(WEIGHTS)
    start = time.time()
    for idx in range(max(need) + 1):
        if not cap.grab():
            break
        if idx not in need:
            continue
        _, frame = cap.retrieve()
        pts = head_points(model, frame, scale, threshold)
        counts = count_cells(image_to_ground(h_head, pts), cells, origin, cell_m) if len(pts) \
            else np.zeros(len(cells), int)
        for t in need[idx]:
            acc[t] += counts
            used[t] += 1
            frame_total[t] += len(pts)
        if idx % round(fps * 10) < 1:
            print(f"{idx / fps:5.1f}s 처리 중", flush=True)

    mean = acc / used[:, None]
    frames, rows = [], []
    for t in range(duration):
        dens = np.round(mean[t] / areas, 2)
        frames.append({"t": t, "inflow_ratio": None, "count": round(float(mean[t].sum()), 2), "cells": [
            {"cell_id": c["cell_id"], "density": float(d), "vx": None, "vy": None,
             "speed_var": None, "pressure": None, "counterflow": None, "density_pred_60s": None}
            for c, d in zip(cells, dens)]})
        rows.append((t, round(float(mean[t].sum()), 2), round(float(frame_total[t] / used[t]), 2)))

    vid = cfg["video"]
    timeline = validate_timeline({
        "schema_version": SCHEMA_VERSION,
        "meta": {
            "zone_id": f"zone-{vid.lower().replace('_', '-')}",
            "camera_id": f"cam-{vid.lower().replace('_', '-')}",
            "video_id": vid, "duration_s": len(frames), "interval_s": 1, "cell_size_m": cell_m,
            "models": {"counter": f"p2pnet-vgg16 x{scale} th{threshold} avg{len(offsets)}",
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
