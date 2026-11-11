"""CLI: timeline.json 의 마지막 관측 프레임에서 화각 밖 예측을 만들어 새 파일로 저장.

    python -m src.predict.run --input data/processed/timeline.json \
                              --output data/processed/timeline.pred.json
"""
from __future__ import annotations

import argparse
from typing import Optional, Sequence

from .config import load_config
from .io import append_predictions, load_timeline, save_timeline
from .model import FlowExtrapolationPredictor


def main(argv: Optional[Sequence[str]] = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--input", required=True, help="입력 timeline.json (관측 프레임 포함)")
    ap.add_argument("--output", required=True, help="출력 경로 (data/raw/ 는 불가)")
    ap.add_argument("--config", default=None, help="설정 YAML (기본: src/predict/config.yaml)")
    args = ap.parse_args(argv)

    cfg = load_config(args.config)
    timeline = load_timeline(args.input)
    result = append_predictions(timeline, FlowExtrapolationPredictor(cfg), cfg.horizons_s)
    save_timeline(result, args.output)
    n_pred = sum(1 for f in result.frames if f.kind == "predicted")
    print("저장 완료: {} (예측 프레임 {}개)".format(args.output, n_pred))


if __name__ == "__main__":
    main()
