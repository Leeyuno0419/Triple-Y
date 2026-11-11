"""실제 바닥 셀에 합성 값을 채운 가짜 timeline.json을 만든다 (서버·화면 연동 확인용).

셀(meta.cells)은 호모그래피로 계산한 실제 값이고, 밀도·흐름은 합성이다(models = "synthetic").
시나리오는 E04_022 영상 내용에 맞춘다: 54초부터 사람들이 계단 앞(GATHER_PX)으로 모여 130초쯤 최대가 된다.
예측(density_pred_60s)은 비워 두고, 예측 모듈로 채운다:
    python -m src.counting.fake_timeline --homography infra/homography/E04_022.json \
        --out data/processed/timeline/fake_E04_022.json
    python -m src.predict.run --input data/processed/timeline/fake_E04_022.json \
        --output data/processed/timeline/fake_E04_022.pred.json
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from src.counting.cells import build_cells, image_to_ground
from src.predict.schema import SCHEMA_VERSION, validate_timeline

GATHER_PX = (330, 700)        # 모이는 곳 (영상 좌표): 왼쪽 계단 앞 바닥
EVENT_START_S, PEAK_S = 54, 130
PEAK_DENSITY = 5.5            # 명/㎡, 기획서 3.2 "위험" 수준
SPREAD_M = 4.0                # 군집 반경 (m)
WALK_SPEED = 1.1              # 모일 때 걷는 속도 (m/s)


def _ramp(t: float, a: float, b: float) -> float:
    """t가 a→b로 갈 때 0→1로 부드럽게 오르는 값."""
    x = min(max((t - a) / (b - a), 0.0), 1.0)
    return x * x * (3 - 2 * x)


def make_fake_timeline(h: np.ndarray, walkable_px: list[list[float]], img_size: tuple[int, int],
                       video_id: str, duration_s: int, seed: int = 0) -> dict[str, object]:
    """규격 v0.1 timeline dict를 만들고 validate_timeline으로 검사해 돌려준다."""
    rng = np.random.default_rng(seed)
    cells = build_cells(h, walkable_px, img_size)
    size = np.array(img_size, float)
    centers = np.array([image_to_ground(h, np.array(c["image_polygon"]) * size).mean(axis=0)
                        for c in cells])
    to_gather = image_to_ground(h, [GATHER_PX])[0] - centers
    dist = np.linalg.norm(to_gather, axis=1)
    near = np.exp(-dist ** 2 / (2 * SPREAD_M ** 2))
    base = np.where(rng.random(len(cells)) < 0.6, rng.uniform(0.1, 0.4, len(cells)), 0.0)

    frames = []
    for t in range(duration_s):
        crowd = _ramp(t, EVENT_START_S, PEAK_S)
        walking = crowd * (1 - _ramp(t, PEAK_S - 20, PEAK_S + 30))  # 모이는 동안만 걷는다
        dens = base + PEAK_DENSITY * crowd * near + rng.normal(0, 0.05, len(cells))
        dens = np.round(np.clip(dens, 0, None), 2)
        states = []
        for i, c in enumerate(cells):
            d = float(dens[i])
            if d < 0.05:
                states.append({"cell_id": c["cell_id"], "density": 0.0, "vx": None, "vy": None,
                               "speed_var": None, "pressure": 0.0, "density_pred_60s": None})
                continue
            v = to_gather[i] / max(dist[i], 1e-6) * WALK_SPEED * walking * min(1.0, dist[i] / 3)
            var = 0.003 + 0.04 * crowd * near[i]   # 군집 안쪽일수록 움직임이 제각각
            states.append({"cell_id": c["cell_id"], "density": d,
                           "vx": round(float(v[0]), 2), "vy": round(float(v[1]), 2),
                           "speed_var": round(var, 4), "pressure": round(d * var, 4),
                           "density_pred_60s": None})
        frames.append({"t": t, "inflow_ratio": round(0.1 + 0.5 * walking, 4), "cells": states})

    vid = video_id.lower().replace("_", "-")
    timeline = {
        "schema_version": SCHEMA_VERSION,
        "meta": {
            "zone_id": f"zone-{vid}", "camera_id": f"cam-{vid}", "video_id": video_id,
            "duration_s": duration_s, "interval_s": 1, "cell_size_m": 2.0,
            "models": {"counter": "synthetic", "flow": "synthetic", "predictor": "none"},
            "prediction": {"history_s": 30, "horizon_s": 60},
            "cells": cells,
        },
        "frames": frames,
    }
    return validate_timeline(timeline)


def main() -> None:
    """호모그래피 JSON을 읽어 가짜 timeline.json을 저장한다."""
    ap = argparse.ArgumentParser()
    ap.add_argument("--homography", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--duration", type=int, default=182, help="E04_022 영상 길이(초)")
    ap.add_argument("--size", default="1920x1080")
    args = ap.parse_args()

    cfg = json.loads(Path(args.homography).read_text(encoding="utf-8"))
    size = tuple(int(v) for v in args.size.split("x"))
    tl = make_fake_timeline(np.array(cfg["H_img_to_ground"]), cfg["walkable_polygon_px"],
                            size, cfg["video"], args.duration)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(tl, ensure_ascii=False), encoding="utf-8")
    print(f"저장: {out} (셀 {len(tl['meta']['cells'])}개, {args.duration}초)")


if __name__ == "__main__":
    main()
