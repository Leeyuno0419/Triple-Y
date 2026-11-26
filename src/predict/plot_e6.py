"""E6 예측 대 실측 그래프: 구역 인원의 60초 뒤 예측을 실측과 겹쳐 그린다.

    python -m src.predict.plot_e6 --input data/processed/timeline/g2test_E04_039.json \\
        --predictors persistence linear ml \\
        --output-png outputs/e6/E04_039_pred_vs_actual.png --output-csv outputs/e6/E04_039_pred_vs_actual.csv

evaluate.py 와 같은 방식으로 시각 t 까지의 기록만 보고 t + horizon_s 를 예측한다.
구역 인원 = Σ(셀 밀도 × 보행 면적). 가로축은 예측 대상 시각(t + horizon_s)이라 실측과 같은 시각끼리 겹친다.
"""
from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import numpy as np

from .config import PREDICTOR_NAMES, PredictConfig, load_config
from .io import assert_not_raw, load_timeline
from .model import CellLayout, make_predictor, require_unit_interval, to_arrays
from .schema import Timeline

# 예측기 표시 이름과 색 (dataviz 기본 팔레트 slot 1~3, 라이트 모드. 색 검증 통과, 연두는 대비 경고라 직접 라벨 필수)
LABELS: Dict[str, str] = {"persistence": "현재값 유지", "linear": "직선 추세", "flow": "흐름 이류", "ml": "학습 모델(ml)"}
COLORS: Dict[str, str] = {"persistence": "#2a78d6", "linear": "#eb6834", "ml": "#1baf7a", "flow": "#6250d6"}
INK, INK_SECONDARY, INK_MUTED, SURFACE, GRID = "#0b0b0b", "#52514e", "#8a8984", "#fcfcfb", "#e6e5e1"


@dataclass
class CountSeries:
    """구역 인원 시계열. target_t[i] 시각의 실측과 각 예측기의 예측이 같은 위치에 놓인다."""

    target_t: np.ndarray                 # (S,) 예측 대상 시각(초) = t + horizon_s
    truth: np.ndarray                    # (S,) 실측 구역 인원(명)
    pred: Dict[str, np.ndarray]          # 예측기 이름 → (S,) 예측 구역 인원(명)
    horizon_s: int
    history_s: int


def build_series(timeline: Timeline, config: PredictConfig, predictors: Sequence[str]) -> CountSeries:
    """모든 시작 시각 t 에서 t + horizon_s 의 구역 인원을 예측해 실측과 함께 모은다."""
    require_unit_interval(timeline.meta)
    hs, hz = config.history_s, config.horizon_s
    dens, vx, vy = to_arrays(timeline)
    t_first, t_last = hs - 1, dens.shape[0] - 1 - hz
    if t_last < t_first:
        raise ValueError("프레임이 {}개 이상 필요하다 (history_s {} + horizon_s {}), 현재 {}개".format(
            hs + hz, hs, hz, dens.shape[0]))
    layout = CellLayout.from_meta(timeline.meta)
    area = layout.area_m2
    models = {n: make_predictor(replace(config, predictor=n)) for n in predictors}

    ts = list(range(t_first, t_last + 1))
    truth = np.array([float((dens[t + hz] * area).sum()) for t in ts])
    pred = {
        n: np.array([float((m.predict(layout, dens[t - hs + 1:t + 1], vx[t], vy[t]) * area).sum()) for t in ts])
        for n, m in models.items()
    }
    return CountSeries(np.array(ts) + hz, truth, pred, hz, hs)


def mean_abs_error(series: CountSeries) -> Dict[str, float]:
    """예측기별 구역 인원 평균절대오차(명)."""
    return {n: float(np.mean(np.abs(p - series.truth))) for n, p in series.pred.items()}


def save_csv(series: CountSeries, path: Path) -> None:
    """그래프에 쓴 값을 CSV 로 남긴다 (그래프를 다시 그리거나 표로 옮길 때 쓴다)."""
    names = list(series.pred)
    with open(path, "w", encoding="utf-8-sig", newline="") as fp:
        w = csv.writer(fp)
        w.writerow(["target_t_s", "truth_count"] + ["pred_count_" + n for n in names])
        for i, t in enumerate(series.target_t):
            w.writerow([int(t), round(float(series.truth[i]), 3)] + [round(float(series.pred[n][i]), 3) for n in names])


def _spread(ys: List[float], min_gap: float) -> List[float]:
    """끝 라벨이 겹치지 않게 y 위치를 위아래로 벌린다 (원래 순서 유지)."""
    order = sorted(range(len(ys)), key=lambda i: ys[i])
    out = list(ys)
    for a, b in zip(order, order[1:]):
        if out[b] - out[a] < min_gap:
            out[b] = out[a] + min_gap
    return out


def plot(series: CountSeries, title: str, subtitle: str, png: Path) -> None:
    """위: 구역 인원(실측과 예측), 아래: 예측 오차 크기. 한 축에 한 단위만 쓴다."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams.update({
        "font.family": ["Malgun Gothic", "AppleGothic", "NanumGothic", "DejaVu Sans"],
        "axes.unicode_minus": False,
    })
    names = list(series.pred)
    fig, (ax, ax_err) = plt.subplots(
        2, 1, figsize=(10, 6.4), sharex=True, gridspec_kw={"height_ratios": [3, 1.6], "hspace": 0.12}, dpi=200)
    fig.patch.set_facecolor(SURFACE)
    x = series.target_t

    for a in (ax, ax_err):
        a.set_facecolor(SURFACE)
        a.grid(axis="y", color=GRID, linewidth=0.8)
        a.set_axisbelow(True)
        for side in ("top", "right", "left"):
            a.spines[side].set_visible(False)
        a.spines["bottom"].set_color(GRID)
        a.tick_params(colors=INK_SECONDARY, labelsize=9, length=0)

    # 위 패널: 실측은 짙은 잉크로 두껍게, 예측은 색 선으로
    ax.plot(x, series.truth, color=INK, linewidth=2.6, solid_capstyle="round", label="실측", zorder=5)
    for n in names:
        ax.plot(x, series.pred[n], color=COLORS.get(n, INK_MUTED), linewidth=2.0, label=LABELS.get(n, n), zorder=4)
    ax.set_ylabel("구역 인원 (명)", color=INK_SECONDARY, fontsize=10)
    ax.set_ylim(bottom=0)

    # 끝 라벨 (색 견본 + 잉크색 글자). 연두는 대비가 낮아 라벨이 필수다
    ends = [("실측", INK, float(series.truth[-1]))] + [
        (LABELS.get(n, n), COLORS.get(n, INK_MUTED), float(series.pred[n][-1])) for n in names]
    top = max(float(series.truth.max()), *(float(p.max()) for p in series.pred.values()))
    ys = _spread([e[2] for e in ends], 0.055 * top)
    for (label, color, y0), y in zip(ends, ys):
        ax.annotate("", xy=(x[-1], y0), xytext=(x[-1] + 1.2, y), annotation_clip=False,
                    arrowprops=dict(arrowstyle="-", color=color, linewidth=1.0))
        ax.text(x[-1] + 1.8, y, "■ ", color=color, fontsize=9, va="center", ha="left", clip_on=False)
        ax.text(x[-1] + 4.2, y, label, color=INK, fontsize=9.5, va="center", ha="left", clip_on=False)

    # 아래 패널: 예측 오차 크기 |예측 − 실측|
    for n in names:
        ax_err.plot(x, np.abs(series.pred[n] - series.truth), color=COLORS.get(n, INK_MUTED), linewidth=1.8)
    ax_err.set_ylabel("오차 크기 (명)", color=INK_SECONDARY, fontsize=10)
    ax_err.set_xlabel("예측 대상 시각 (영상 시간, 초)", color=INK_SECONDARY, fontsize=10)
    ax_err.set_ylim(bottom=0)

    # 범례 (2개 이상 계열은 범례 필수)
    leg = ax.legend(loc="upper left", ncol=len(names) + 1, frameon=False, fontsize=9.5, handlelength=1.8)
    for text in leg.get_texts():
        text.set_color(INK)

    fig.text(0.075, 0.965, title, color=INK, fontsize=13.5, fontweight="bold", ha="left", va="top")
    fig.text(0.075, 0.925, subtitle, color=INK_SECONDARY, fontsize=9.5, ha="left", va="top")
    fig.subplots_adjust(left=0.075, right=0.86, top=0.86, bottom=0.095)
    png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(png, facecolor=SURFACE)
    plt.close(fig)


def main(argv: Optional[Sequence[str]] = None) -> None:
    """CLI 진입점."""
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--input", required=True, help="timeline.json (history_s + horizon_s 초 이상)")
    ap.add_argument("--config", default=None, help="설정 YAML (기본: src/predict/config.yaml)")
    ap.add_argument("--predictors", nargs="+", choices=PREDICTOR_NAMES, default=["persistence", "linear", "ml"])
    ap.add_argument("--output-png", required=True, help="그래프 PNG 저장 경로")
    ap.add_argument("--output-csv", default=None, help="그래프에 쓴 값 CSV 저장 경로")
    ap.add_argument("--title", default=None, help="그래프 제목 (기본: 영상 ID 로 만든다)")
    args = ap.parse_args(argv)

    cfg = load_config(args.config)
    timeline = load_timeline(args.input)
    series = build_series(timeline, cfg, args.predictors)
    mae = mean_abs_error(series)

    video = timeline.meta.video_id or Path(args.input).stem
    title = args.title or "{} 구역 인원: {}초 뒤 예측 대 실측".format(video, series.horizon_s)
    subtitle = "시각 t까지 최근 {}초만 보고 t+{}초를 예측. 평균절대오차(명): {}".format(
        series.history_s, series.horizon_s,
        " · ".join("{} {:.1f}".format(LABELS.get(n, n), v) for n, v in mae.items()))
    for p in (args.output_png, args.output_csv):
        if p:
            assert_not_raw(p)
    plot(series, title, subtitle, Path(args.output_png))
    print("저장 완료: {}".format(args.output_png))
    if args.output_csv:
        save_csv(series, Path(args.output_csv))
        print("저장 완료: {}".format(args.output_csv))
    for n, v in mae.items():
        print("  {:<12s} 구역 인원 평균절대오차 {:.2f}명".format(n, v))


if __name__ == "__main__":
    main()
