"""CLI: timeline.json 의 모든 프레임에 60초 뒤 밀도 예측(density_pred_60s)을 채워 새 파일로 저장.

    python -m src.predict.run --input data/processed/timeline/E04_039.json \
                              --output data/processed/timeline/E04_039.pred.json [--predictor linear]
"""
from __future__ import annotations

import argparse
from dataclasses import replace
from typing import Optional, Sequence

from .config import PREDICTOR_NAMES, load_config
from .io import load_timeline, save_timeline
from .model import fill_predictions, make_predictor


def main(argv: Optional[Sequence[str]] = None) -> None:
    """CLI 진입점."""
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--input", required=True, help="입력 timeline.json")
    ap.add_argument("--output", required=True, help="출력 경로 (data/raw/ 는 불가)")
    ap.add_argument("--config", default=None, help="설정 YAML (기본: src/predict/config.yaml)")
    ap.add_argument("--predictor", choices=PREDICTOR_NAMES, default=None, help="설정의 predictor 를 덮어쓴다")
    args = ap.parse_args(argv)

    cfg = load_config(args.config)
    if args.predictor:
        cfg = replace(cfg, predictor=args.predictor)
    result = fill_predictions(load_timeline(args.input), make_predictor(cfg))
    save_timeline(result, args.output)
    n_pred = sum(1 for f in result.frames if f.cells and f.cells[0].density_pred_60s is not None)
    print("저장 완료: {} (예측 predictor={}, 예측이 채워진 프레임 {}/{}개)".format(
        args.output, cfg.predictor, n_pred, len(result.frames)))


if __name__ == "__main__":
    main()
