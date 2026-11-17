"""60초 뒤 밀도 예측 모델 학습 (Ridge 회귀 등 가벼운 모델) + 성능(MAE, RMSE) 출력 + 모델 저장.

    python -m src.predict.train_forecast                          # 실제 timeline 이 3개 이상이면 그걸로, 없으면 합성 데이터로
    python -m src.predict.train_forecast --source synthetic        # 합성 데이터로 강제
    python -m src.predict.train_forecast --model hgb               # Ridge 대신 트리 부스팅 (LightGBM 계열, 추가 설치 없음)

학습이 끝나면 outputs/models/forecast_ridge.joblib 에 저장한다 (경로는 config.yaml 의 model_path).
그 뒤 python -m src.predict.run --input ... --output ... --predictor ml 로 timeline 에 예측을 채운다.

흐름
    1. 데이터 준비: 기록(영상)별 셀 밀도 시계열 (T, 셀 수). 실제 timeline.json 또는 합성 데이터.
    2. 영상 단위로 학습 60% / 검증 20% / 시험 20% 로 나눈다. (같은 영상의 앞뒤가 학습·시험에 섞이면 점수가 부풀려진다)
    3. 검증 데이터로 Ridge 의 규제 세기(alpha)를 고르고, 학습+검증으로 다시 학습한다.
    4. 한 번도 안 본 시험 영상에서 '현재값 유지', '직선 추세', 'ML 모델'의 MAE·RMSE 를 비교한다.
"""
from __future__ import annotations

import argparse
import glob
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from .config import load_config
from .io import load_timeline
from .ml_forecast import (
    DEFAULT_N_LAGS, REPO_ROOT, ForecastBundle, feature_names, make_xy, persistence_baseline, resolve_path,
    save_bundle,
)
from .model import to_arrays
from .synthetic import make_synthetic_series

DEFAULT_TIMELINE_GLOB = "data/processed/timeline/*.json"
ALPHA_GRID = (0.01, 0.1, 1.0, 10.0, 100.0, 1000.0, 1e4, 1e5)   # Ridge 규제 세기 후보 (클수록 단순한 모델)
MIN_REAL_SERIES = 3                                     # 학습·검증·시험에 최소 1개씩 필요


# --------------------------------------------------------------------------- #
# 데이터 준비
# --------------------------------------------------------------------------- #
def load_real_series(paths: Sequence[str], need_s: int) -> List[np.ndarray]:
    """timeline.json 들에서 셀별 밀도 시계열 (T, 셀 수)을 읽는다. history+horizon 보다 짧은 파일은 건너뛴다."""
    series: List[np.ndarray] = []
    for p in paths:
        timeline = load_timeline(p)
        if timeline.meta.interval_s != 1:
            print("건너뜀 (interval_s != 1): {}".format(p))
            continue
        dens = to_arrays(timeline)[0]
        if dens.shape[0] < need_s:
            print("건너뜀 (기록 {}초 < {}초): {}".format(dens.shape[0], need_s, p))
            continue
        series.append(dens)
    return series


def find_timelines(pattern: str) -> List[str]:
    """예측이 이미 채워진 결과(*.pred.json)는 빼고 원본 timeline 만 찾는다 (같은 영상이 두 번 들어가는 것을 막는다)."""
    base = pattern if Path(pattern).is_absolute() else str(REPO_ROOT / pattern)
    return sorted(p for p in glob.glob(base) if not p.endswith(".pred.json"))


def split_series(n: int, seed: int) -> Tuple[List[int], List[int], List[int]]:
    """기록 번호를 (학습, 검증, 시험)으로 나눈다. 약 60/20/20 이고 각각 최소 1개. 같은 seed 면 같은 결과."""
    if n < MIN_REAL_SERIES:
        raise ValueError("기록이 {}개 이상 필요하다 (현재 {}개)".format(MIN_REAL_SERIES, n))
    order = [int(i) for i in np.random.default_rng(seed).permutation(n)]
    n_test = max(1, round(0.2 * n))
    n_val = max(1, round(0.2 * n))
    return order[n_test + n_val:], order[n_test:n_test + n_val], order[:n_test]


# --------------------------------------------------------------------------- #
# 모델 · 점수
# --------------------------------------------------------------------------- #
def make_model(kind: str, alpha: float, seed: int):
    """회귀 모델을 만든다. 피처는 단위가 제각각이라 표준화(StandardScaler)를 앞에 붙인다."""
    from sklearn.ensemble import HistGradientBoostingRegressor
    from sklearn.linear_model import Ridge
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    if kind == "ridge":
        return make_pipeline(StandardScaler(), Ridge(alpha=alpha))
    if kind == "hgb":    # LightGBM 과 같은 계열의 히스토그램 부스팅 (scikit-learn 에 들어 있어 따로 설치하지 않는다)
        return make_pipeline(StandardScaler(), HistGradientBoostingRegressor(
            max_depth=4, learning_rate=0.05, max_iter=300, l2_regularization=1.0, random_state=seed))
    raise ValueError("알 수 없는 모델: {!r}".format(kind))


@dataclass
class Scores:
    """예측 방법 하나의 점수."""

    mae: float      # 평균절대오차 (명/㎡)
    rmse: float     # 제곱평균제곱근오차 (명/㎡). 큰 오차에 더 민감하다


def score(pred: np.ndarray, truth: np.ndarray) -> Scores:
    """MAE, RMSE 를 계산한다."""
    err = np.asarray(pred) - np.asarray(truth)
    return Scores(mae=float(np.mean(np.abs(err))), rmse=float(np.sqrt(np.mean(err ** 2))))


def final_pred(model, X: np.ndarray, cur: np.ndarray) -> np.ndarray:
    """모델이 맞힌 변화량을 지금 밀도에 더해 60초 뒤 밀도로 되돌린다 (0 미만은 0)."""
    return np.clip(cur + model.predict(X), 0.0, None)


def pick_alpha(kind: str, data: Dict[str, Tuple[np.ndarray, ...]], seed: int) -> float:
    """검증 데이터에서 MAE 가 가장 낮은 alpha 를 고른다 (ridge 만. 다른 모델은 고정값)."""
    if kind != "ridge":
        return 0.0
    Xtr, ytr, _, _ = data["train"]
    Xva, yva, cva, _ = data["val"]
    best_alpha, best_mae = ALPHA_GRID[0], float("inf")
    for a in ALPHA_GRID:
        m = make_model(kind, a, seed).fit(Xtr, ytr)
        mae = score(final_pred(m, Xva, cva), cva + yva).mae
        if mae < best_mae:
            best_alpha, best_mae = a, mae
    return best_alpha


def format_report(rows: Dict[str, Dict[str, Scores]]) -> str:
    """구간별 점수 비교표를 문자열로 만든다. '개선'은 현재값 유지 대비 MAE 감소율이다."""
    lines: List[str] = []
    for part, by_name in rows.items():
        base = by_name["persistence"].mae
        lines.append("[{}]".format(part))
        lines.append("  {:<22s} {:>8s} {:>8s} {:>14s}".format("예측 방법", "MAE", "RMSE", "MAE 개선(vs 유지)"))
        for name, s in by_name.items():
            gain = "-" if name == "persistence" or base < 1e-12 else "{:+.1%}".format(1.0 - s.mae / base)
            lines.append("  {:<22s} {:>8.4f} {:>8.4f} {:>14s}".format(name, s.mae, s.rmse, gain))
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# 메인
# --------------------------------------------------------------------------- #
def main(argv: Optional[Sequence[str]] = None) -> None:
    """학습 → 점수 출력 → 저장."""
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--config", default=None, help="설정 YAML (기본: src/predict/config.yaml)")
    ap.add_argument("--source", choices=("auto", "real", "synthetic"), default="auto",
                    help="auto: 실제 timeline 이 3개 이상이면 실제, 아니면 합성 (기본)")
    ap.add_argument("--timeline-glob", default=DEFAULT_TIMELINE_GLOB, help="실제 timeline 경로 패턴")
    ap.add_argument("--model", choices=("ridge", "hgb"), default="ridge", help="ridge(기본) | hgb(트리 부스팅)")
    ap.add_argument("--n-lags", type=int, default=DEFAULT_N_LAGS, help="직접 입력으로 쓸 최근 초 수 (기본 10)")
    ap.add_argument("--series", type=int, default=24, help="합성 기록 개수")
    ap.add_argument("--duration", type=int, default=1200, help="합성 기록 길이(초)")
    ap.add_argument("--rows", type=int, default=4, help="합성 격자 행 수")
    ap.add_argument("--cols", type=int, default=6, help="합성 격자 열 수")
    ap.add_argument("--stride", type=int, default=3, help="학습 표본을 몇 초 간격으로 뽑을지 (인접 시각은 거의 같은 표본)")
    ap.add_argument("--seed", type=int, default=42, help="무작위 시드 (같으면 결과도 같다)")
    ap.add_argument("--out", default=None, help="모델 저장 경로 (기본: config.yaml 의 model_path)")
    args = ap.parse_args(argv)

    cfg = load_config(args.config)
    hs, hz = cfg.history_s, cfg.horizon_s
    if not 2 <= args.n_lags <= hs:
        raise SystemExit("--n-lags 는 2 이상, history_s({}) 이하여야 한다: {}".format(hs, args.n_lags))
    out_path = resolve_path(args.out or cfg.model_path)

    # 1) 데이터 준비 ---------------------------------------------------------
    paths = find_timelines(args.timeline_glob)
    use_real = args.source == "real" or (args.source == "auto" and len(paths) >= MIN_REAL_SERIES)
    if args.source == "auto" and not use_real:
        print("실제 timeline {}개 발견 ({}개 이상 필요) -> 합성 데이터로 학습한다.".format(len(paths), MIN_REAL_SERIES))
    if use_real:
        series = load_real_series(paths, hs + hz)
        trained_on = "real"
        print("실제 timeline {}개 사용".format(len(series)))
    else:
        series = make_synthetic_series(args.series, args.seed, args.rows, args.cols, args.duration)
        trained_on = "synthetic"
        print("합성 데이터 {}개 생성 (격자 {}x{}, 각 {}초, seed {})".format(
            len(series), args.rows, args.cols, args.duration, args.seed))
    if len(series) < MIN_REAL_SERIES:
        raise SystemExit("학습에 쓸 기록이 {}개 이상 필요하다 (현재 {}개)".format(MIN_REAL_SERIES, len(series)))

    # 2) 영상 단위 분할 ------------------------------------------------------
    tr_i, va_i, te_i = split_series(len(series), args.seed)
    data = {
        name: make_xy([series[i] for i in idx], hs, hz, args.n_lags, args.stride)
        for name, idx in (("train", tr_i), ("val", va_i), ("test", te_i))
    }
    print("기록 분할: 학습 {} / 검증 {} / 시험 {}개, 표본(셀x시각) {} / {} / {}".format(
        len(tr_i), len(va_i), len(te_i), len(data["train"][0]), len(data["val"][0]), len(data["test"][0])))

    # 3) alpha 선택 후 학습+검증으로 다시 학습 ----------------------------------
    alpha = pick_alpha(args.model, data, args.seed)
    X_fit = np.concatenate([data["train"][0], data["val"][0]])
    y_fit = np.concatenate([data["train"][1], data["val"][1]])
    model = make_model(args.model, alpha, args.seed).fit(X_fit, y_fit)
    if args.model == "ridge":
        print("선택된 alpha = {} (검증 MAE 기준)".format(alpha))

    # 4) 시험 점수 -----------------------------------------------------------
    Xte, yte, cte, lte = data["test"]
    truth = cte + yte
    preds = {
        "persistence": persistence_baseline(cte),
        "linear": lte,
        "ml-{}".format(args.model): final_pred(model, Xte, cte),
    }
    sharp = np.abs(yte) >= np.quantile(np.abs(yte), 0.8)       # 실제로 크게 변한 상위 20% (급변 구간)
    rows = {
        "시험 전체": {n: score(p, truth) for n, p in preds.items()},
        "급변 구간 (실제 변화 상위 20%)": {n: score(p[sharp], truth[sharp]) for n, p in preds.items()},
    }
    print()
    print(format_report(rows))
    if trained_on == "synthetic":
        print("\n※ 합성 데이터 점수입니다. 코드·모델이 돌아가는지 확인하는 용도이며 실제 영상의 성능이 아닙니다.")
        print("   실제 timeline 이 {}개 이상 생기면 같은 명령으로 다시 학습·평가하세요.".format(MIN_REAL_SERIES))

    # 5) 저장 ----------------------------------------------------------------
    import sklearn

    meta = {
        "kind": args.model, "alpha": alpha, "n_lags": args.n_lags, "feature_names": feature_names(args.n_lags),
        "history_s": hs, "horizon_s": hz, "target": "delta(rho(t+horizon) - rho(t))",
        "trained_on": trained_on, "n_series": len(series), "seed": args.seed,
        "sklearn_version": sklearn.__version__,
        "test": {part: {n: {"mae": s.mae, "rmse": s.rmse} for n, s in by.items()} for part, by in rows.items()},
    }
    saved = save_bundle(ForecastBundle(model=model, meta=meta), out_path)
    sidecar = saved.with_suffix(".json")                        # 사람이 읽는 요약 (가중치 없음)
    sidecar.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n저장 완료: {}\n요약 JSON: {}".format(saved, sidecar))


if __name__ == "__main__":
    main()
