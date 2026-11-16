"""통합 분석: 영상 1개를 인원·밀도 → 흐름·불안정 → 60초 예측 순서로 돌려 timeline.json 하나를 만든다.

    python -m src.counting.analyze --homography infra/homography/E04_039.json \
        --video data/processed/g1/E04_039.mp4 --out data/processed/timeline/E04_039.json

- 인원·밀도: src.counting.run_density.count_video (density, count)
- 흐름: src.flow.run_flow.analyze_video (vx, vy, speed_var, pressure, inflow_ratio)
- 예측: src.predict (density_pred_60s). 예측 방법은 src/predict/config.yaml, --predictor로 덮어쓴다
머리 점은 인원 세기에서 흐름으로 메모리로만 넘기고 흐름이 끝나면 버린다 (규격 9절 4번).
단계별 처리 시간은 outputs/e8/{영상}_analysis_time.json에 남긴다 (E8: 사전 분석 시간은 기록·공개).
"""
from __future__ import annotations

import argparse
import json
import platform
import time
from dataclasses import replace
from pathlib import Path

import numpy as np
import torch

from src.counting.run_density import ROOT, count_video, save_counts
from src.flow.estimators import FarnebackEstimator
from src.flow.run_flow import analyze_video
from src.predict.config import PREDICTOR_NAMES, load_config
from src.predict.io import load_timeline, save_timeline
from src.predict.model import fill_predictions, make_predictor


def main() -> None:
    """세 단계를 차례로 돌려 timeline.json, 초별 인원 CSV, 처리 시간 기록을 저장한다."""
    ap = argparse.ArgumentParser()
    ap.add_argument("--homography", required=True, help="구역 설정 파일")
    ap.add_argument("--video", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--predictor", choices=PREDICTOR_NAMES, default=None,
                    help="예측 방법 (기본: src/predict/config.yaml)")
    ap.add_argument("--limit", type=int, default=0, help="앞에서 몇 초만 (빠른 확인용)")
    args = ap.parse_args()

    cfg = json.loads(Path(args.homography).read_text(encoding="utf-8"))
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    sec: dict[str, float] = {}

    start = time.time()
    timeline, heads, rows = count_video(cfg, args.video, args.limit)
    out.write_text(json.dumps(timeline, ensure_ascii=False), encoding="utf-8")
    save_counts(cfg["video"], rows)
    sec["counting"] = time.time() - start
    print(f"[1/3] 인원·밀도 {sec['counting']:.0f}초", flush=True)

    start = time.time()
    analyze_video(Path(args.video), out, out, FarnebackEstimator(), heads=heads,
                  h_head=np.array(cfg["head_plane"]["H_head_img_to_ground"]),
                  cell_origin_m=tuple(cfg["cell_origin_m"]))
    del heads  # 머리 점은 여기까지만 쓴다
    sec["flow"] = time.time() - start
    print(f"[2/3] 흐름·불안정 {sec['flow']:.0f}초", flush=True)

    start = time.time()
    pcfg = load_config()
    if args.predictor:
        pcfg = replace(pcfg, predictor=args.predictor)
    save_timeline(fill_predictions(load_timeline(out), make_predictor(pcfg)), out)
    sec["predict"] = time.time() - start
    print(f"[3/3] 60초 예측({pcfg.predictor}) {sec['predict']:.0f}초", flush=True)

    duration = len(rows)
    total = sum(sec.values())
    record = {
        "video": cfg["video"], "duration_s": duration,
        "seconds": {k: round(v, 1) for k, v in sec.items()}, "total_s": round(total, 1),
        "seconds_per_video_second": round(total / max(duration, 1), 2),
        "environment": {"device": "cpu", "cpu": platform.processor(), "torch": torch.__version__},
    }
    e8 = ROOT / "outputs" / "e8" / f"{cfg['video']}_analysis_time.json"
    e8.parent.mkdir(parents=True, exist_ok=True)
    e8.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"저장: {out}, {e8} (영상 {duration}초 → 처리 {total:.0f}초, "
          f"영상 1초당 {record['seconds_per_video_second']}초)")


if __name__ == "__main__":
    main()
