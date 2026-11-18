"""E5 보고서: 실행기 CSV 읽기·서버 알림 대조·md·csv·png 쓰기.

    python -m src.flow.e5.report \
        --timeline data/processed/timeline/E04_039.json \
        --sweep-dir outputs/e5 \
        [--server-alerts data/processed/e5/E04_039_server_alerts.json] \
        --out outputs/e5

값 계산은 src.flow.e5.analysis.build_report가 하고, 이 모듈은 읽기·
쓰기만 한다. matplotlib는 그림 함수 안에서만 import한다. 그래서 md·csv
시험은 matplotlib 없이 돈다. 결과 파일에는 셀·구역 집계값과 알림만
담는다(좌표 없음).
"""
from __future__ import annotations

import argparse
import csv
import json
from collections.abc import Sequence
from importlib import metadata
from pathlib import Path
from types import ModuleType

import numpy as np

from src.flow.e5.analysis import build_report, load_timeline
from src.predict.io import assert_not_raw

ROOT = Path(__file__).resolve().parents[3]
OUT_DIR = ROOT / "outputs" / "e5"
FONTS = ("Malgun Gothic", "AppleGothic", "NanumGothic")
BLUE, ORANGE, GREEN, YELLOW = "#2a78d6", "#eb6834", "#1baf7a", "#eda100"
RED_SHADE, YELLOW_SHADE = "#d03b3b", "#fab219"

TICKS_COLUMNS = ("t", "zone_grade", "max_density", "inflow_avg",
                 "inflow_alert", "n_unstable", "unstable_cells", "events")
ALERTS_COLUMNS = ("t", "reason", "level", "value", "cell_ids")
SUMMARY_COLUMNS = ("n_instability", "n_grade_up", "n_inflow",
                   "first_instability_t", "first_grade_up_t",
                   "first_inflow_t", "unstable_s", "critical_s",
                   "inflow_on_s")
INSTABILITY_COLUMNS = ("pressure", "seconds", "is_default") + SUMMARY_COLUMNS
INFLOW_COLUMNS = ("ratio", "window_seconds", "min_samples", "min_count",
                  "off_seconds", "is_default") + SUMMARY_COLUMNS
THRESHOLD = 0.02  # 서버 기본 pressure 기준 (application.yml, 문헌 참고선)

LIMITS = (
    "- 상승 사건이 1~2개라 시간 차는 일반화하지 않는다.",
    "- 잡음 바닥을 빼지 않아 P에 측정 잡음이 들어 있다 (cells.py:84-86).",
    "- 속도 축척 오차 k배 → P k²배 (가로 배율 5~10% 작을 수 있음,\n"
    "  infra/homography/E04_039.json:52).",
    "- E04_039 경계 셀은 화면 아래 줄 3개뿐이라 다른 방향 유입은 보지 "
    "못한다.",
    "- 민감도는 서버가 가진 규칙만 바꿔 본 것이다. null 건너뜀 같은 "
    "변형은 없다.",
)


def read_runner_csv(path: Path, columns: Sequence[str]) -> list[dict]:
    """실행기 CSV를 읽는다.

    머리줄에 columns가 모두 없으면 ValueError다(Java 머리줄과의 약속,
    9.1절). 값은 문자열 그대로, 빈칸은 None이다.
    """
    with Path(path).open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        missing = [c for c in columns if c not in (reader.fieldnames or [])]
        if missing:
            raise ValueError(
                f"{path} 머리줄에 열이 없다: {', '.join(missing)} "
                "(Java E5Sweep 머리줄과 report.py 열 상수를 같이 고친다)")
        return [{k: (v if v != "" else None) for k, v in row.items()}
                for row in reader]


def _cell(value: object) -> str:
    """CSV 칸: None은 빈칸, bool은 0/1, float는 repr, 나머지는 str."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, float):
        return repr(value)
    return str(value)


def write_csv(path: Path, rows: Sequence[dict]) -> None:
    """첫 행 키를 머리줄로 CSV를 쓴다 (UTF-8, LF).

    None은 빈칸, bool은 0/1, float는 repr 그대로(결정적). 행이 없으면
    머리줄 없이 빈 파일이다.
    """
    with Path(path).open("w", encoding="utf-8", newline="") as f:
        if not rows:
            return
        writer = csv.writer(f, lineterminator="\n")
        columns = list(rows[0])
        writer.writerow(columns)
        for row in rows:
            writer.writerow([_cell(row[c]) for c in columns])


def _fmt(value: object) -> str:
    """md 칸: None은 '-', bool은 예/아니오, float는 유효숫자 4자리."""
    if value is None:
        return "-"
    if isinstance(value, bool):
        return "예" if value else "아니오"
    if isinstance(value, float):
        return f"{value:.4g}"
    return str(value)


def _table(
    header: Sequence[str], rows: Sequence[Sequence[object]],
    bold: Sequence[bool] | None = None,
) -> list[str]:
    """md 표 줄 목록. bold[i]가 참인 행은 칸마다 굵게."""
    lines = ["| " + " | ".join(header) + " |",
             "|" + "---|" * len(header)]
    for i, row in enumerate(rows):
        cells = [_fmt(v) for v in row]
        if bold is not None and bold[i]:
            cells = [f"**{c}**" for c in cells]
        lines.append("| " + " | ".join(cells) + " |")
    return lines


def _version(package: str) -> str:
    """설치된 패키지 버전. 없으면 '없음'."""
    try:
        return metadata.version(package)
    except metadata.PackageNotFoundError:
        return "없음"


def _section_series(report: dict, video: str) -> list[str]:
    """1절: P 분포·봉우리·셀 표."""
    q = report["quantiles"]
    lines = [
        "## 1. 불안정 지표 P 시계열",
        f"그림 `{video}_series.png`, 초별 값 `{video}_series.csv`. "
        "구역 P = 판정 대상 셀(≥ 2㎡) non-null pressure의 최댓값.",
        "",
        "### P 분포 (판정 대상 셀-초, non-null)",
    ]
    lines += _table(
        ["표본 수", "p50", "p90", "p95", "p99", "최대",
         f"{THRESHOLD} 초과 비율", f"{THRESHOLD}의 백분위"],
        [[q["n"], q["p50"], q["p90"], q["p95"], q["p99"], q["max"],
          q["over_ratio"], q["threshold_pct"]]],
    )
    lines += ["", "### 구역 P 봉우리 (서로 10초 이상, 큰 순서)"]
    lines += _table(["t (초)", "구역 P"], report["peaks"])
    lines += ["", "### 셀 표"]
    lines += _table(
        ["셀", "면적(㎡)", "판정 대상", "경계",
         "pressure null 비율 (t ≥ 29, 사람 있음)", "null로 끊김",
         "기준 이하로 끊김"],
        [[c["cell_id"], c["area_m2"], c["eligible"], c["boundary"],
          c["pressure_null_ratio"], c["breaks_null"], c["breaks_below"]]
         for c in report["cells"]],
    )
    return lines


def _section_sweep(report: dict, video: str) -> list[str]:
    """2절: 불안정·유입 민감도와 창 길이 T."""
    inst = report["sweep_instability"]
    lines = [
        "## 2. 기준값 민감도 (서버 판정 클래스 재생)",
        f"그림 `{video}_sweep.png`. 굵은 행이 기본값(application.yml).",
        "",
        "### 2.1 불안정",
    ]
    lines += _table(
        ["pressure", "seconds", "INSTABILITY 수", "GRADE_UP 수",
         "첫 INSTABILITY", "첫 GRADE_UP", "unstable_s", "critical_s"],
        [[r["pressure"], r["seconds"], r["n_instability"],
          r["n_grade_up"], r["first_instability_t"],
          r["first_grade_up_t"], r["unstable_s"], r["critical_s"]]
         for r in inst],
        [r["is_default"] == "true" for r in inst],
    )
    flow = [r for r in report["sweep_inflow"] if r["window_seconds"] == "5"]
    lines += ["", "### 2.2 유입 (창 5초 행, 전체는 CSV)"]
    lines += _table(
        ["ratio", "min_count", "INFLOW 수", "첫 INFLOW", "inflow_on_s"],
        [[r["ratio"], r["min_count"], r["n_inflow"], r["first_inflow_t"],
          r["inflow_on_s"]] for r in flow],
        [r["is_default"] == "true" for r in flow],
    )
    check = report["recompute_check"]
    lines += [
        "", "### 2.3 창 길이 T (P 분포만, 알림 수는 내지 않음)",
        "non-null 비율의 분모는 모든 t의 판정 대상 셀 중 사람이 있는"
        "(소수 2자리 density > 0) 셀-초다. 창이 차기 전 앞 T−1초는 늘 "
        "null이라, T=60의 낮은 비율은 대부분 창이 덜 찬 탓이다.",
        "",
    ]
    lines += _table(
        ["T (초)", "non-null 비율", "p95", f"{THRESHOLD} 초과 비율"],
        [[w["window_s"], w["nonnull_ratio"], w["p95"], w["over_ratio"]]
         for w in report["window"]],
    )
    lines += [
        "",
        f"T=30 재계산 검증: 비교 셀-초 {check['n_both']}, 최대 차이 "
        f"{_fmt(check['max_abs_diff'])}, null 불일치 "
        f"{check['n_null_mismatch']}.",
    ]
    return lines


def _section_lag(report: dict, video: str) -> list[str]:
    """3절: 상호상관과 사건 기준 시간 차."""
    best = report["best_lag"]
    lines = [
        "## 3. 유입 → 인원 증가 시간 차",
        f"그림 `{video}_lag.png`, 지연별 r `{video}_lag.csv`.",
        "",
        "### 3.1 상호상관",
        "x = 실행기 inflow_avg(서버 5초 평균), y = count 5초 평활의 "
        "기울기(명/초). 지연 k > 0이면 유입이 k초 앞선다.",
    ]
    if best is None:
        lines.append("측정 불가 (쌍이 30개 이상인 지연이 없다).")
    else:
        lines += _table(["최대 r의 지연 (초)", "r", "쌍 수"],
                        [[best["lag_s"], best["r"], best["n_pairs"]]])
    lines += ["", "### 3.2 사건 기준",
              "t_in = inflow_avg > 0.6이 처음인 초(인원 조건 없음), "
              "t_alarm = 실행기 첫 INFLOW 알림 초(기본값)."]
    lines += _table(
        ["기준", "인원 기준값", "t_cnt", "t_in", "신호 기준 차 (초)",
         "t_alarm", "경보 기준 차 (초)"],
        [[e["criterion"], e["level"], e["t_cnt"], e["t_in"],
          e["lag_signal_s"], e["t_alarm"], e["lag_alarm_s"]]
         for e in report["events"]],
    )
    return lines


def _section_server(report: dict) -> list[str]:
    """4절: 실제 서버 알림과 실행기 알림 대조."""
    lines = ["## 4. 서버 확인 (G2 통합 시험 첫 단계)"]
    check = report["server_check"]
    if check is None:
        return lines + ["하지 않음 (`--server-alerts` 없음)."]
    lines += _table(["서버 알림 수", "실행기 알림 수", "일치"],
                    [[check["n_server"], check["n_runner"],
                      check["match"]]])
    if check["diffs"]:
        lines += ["", "다른 행:"]
        lines += _table(["순번", "서버", "실행기"],
                        [[i, _alert_text(a), _alert_text(b)]
                         for i, a, b in check["diffs"]])
    return lines


def _alert_text(alert: dict | None) -> str:
    """대조 표의 알림 한 줄 요약. 없으면 '-'."""
    if alert is None:
        return "-"
    return (f"t={alert['t']} {alert['reason']} {alert['level']} "
            f"{_fmt(alert['value'])} [{';'.join(alert['cell_ids'])}]")


def render_markdown(report: dict, timeline_path: str) -> str:
    """9.2절 구성의 md 문자열. 기본 설정 행은 굵게 표시."""
    meta = report["meta"]
    video = meta["video_id"]
    models = meta["models"]
    lines = [
        f"# E5 {video}: 불안정 지표·기준값 민감도·유입 시간 차",
        "",
        "| 항목 | 값 |",
        "|---|---|",
        f"| timeline | {timeline_path} |",
        f"| 모델 | counter {models.get('counter')}, flow "
        f"{models.get('flow')} |",
        f"| 길이·셀 | {meta['duration_s']}초, 셀 {meta['n_cells']}개 "
        f"(판정 대상 {meta['n_eligible']}개) |",
        "| 서버 판정 | ./gradlew e5Sweep (서버 판정 클래스 그대로), "
        "기본값 = application.yml |",
        f"| 환경 | numpy {np.__version__}, matplotlib "
        f"{_version('matplotlib')} |",
        "",
        "정답 클립이 없어 감지 성능은 주장하지 않는다. "
        f"{THRESHOLD}/s²는 문헌 참고선이다.",
        "",
    ]
    lines += _section_series(report, video) + [""]
    lines += _section_sweep(report, video) + [""]
    lines += _section_lag(report, video) + [""]
    lines += _section_server(report) + [""]
    lines += ["## 5. 한계", *LIMITS]
    return "\n".join(lines) + "\n"


def _pyplot() -> ModuleType:
    """Agg 백엔드 pyplot. 한글 글꼴은 FONTS 중 설치된 첫 글꼴 + DejaVu Sans.

    matplotlib는 여기서만 import한다(md·csv는 matplotlib 없이 쓴다).
    """
    import matplotlib
    matplotlib.use("Agg")
    from matplotlib import font_manager
    from matplotlib import pyplot as plt

    names = {f.name for f in font_manager.fontManager.ttflist}
    family = [f for f in FONTS if f in names][:1] + ["DejaVu Sans"]
    plt.rcParams["font.family"] = family
    plt.rcParams["axes.unicode_minus"] = False
    return plt


def _spans(mask: Sequence[bool]) -> list[tuple[int, int]]:
    """참이 이어진 구간 (시작 t, 끝 t) 목록."""
    spans: list[tuple[int, int]] = []
    start = None
    for t, on in enumerate(list(mask) + [False]):
        if on and start is None:
            start = t
        elif not on and start is not None:
            spans.append((start, t - 1))
            start = None
    return spans


def _shade(ax: object, mask: Sequence[bool], color: str,
           alpha: float) -> None:
    """참인 초를 세로 띠로 칠한다 (경보 음영)."""
    for start, end in _spans(mask):
        ax.axvspan(start - 0.5, end + 0.5, color=color, alpha=alpha, lw=0)


def _arr(values: Sequence[float | None]) -> np.ndarray:
    """None을 NaN으로 바꾼 float 배열."""
    return np.array([np.nan if v is None else float(v) for v in values])


def plot_series(report: dict, ticks: Sequence[dict], path: Path) -> None:
    """3칸 그림 (제안 P9).

    위: 판정 대상 셀 P(회색 가는 선) + 구역 P(파랑) + 기준 0.02(회색
    점선) + 불안정 초 음영(ticks n_unstable > 0, 빨강 투명 0.12).
    가운데: count + 3명 점선. 아래: inflow_ratio 점(주황) + inflow_avg
    선(파랑, ticks) + 0.6 점선 + 유입 경보 초 음영(ticks inflow_alert,
    노랑 투명 0.2). x축 10초 간격 눈금.
    """
    plt = _pyplot()
    series = report["series"]
    t = np.array([r["t"] for r in series])
    fig, (ax_p, ax_c, ax_i) = plt.subplots(3, 1, figsize=(12, 9),
                                          sharex=True)
    for i, values in enumerate(report["cell_pressure"].values()):
        ax_p.plot(t, _arr(values), color="#9a9a9a", lw=0.6,
                  label="판정 대상 셀 P" if i == 0 else None)
    ax_p.plot(t, _arr([r["zone_pressure"] for r in series]), color=BLUE,
              lw=1.5, label="구역 P (셀 최댓값)")
    ax_p.axhline(THRESHOLD, color="gray", ls="--", lw=1,
                 label=f"기준 {THRESHOLD} (문헌 참고선)")
    _shade(ax_p, [int(r["n_unstable"]) > 0 for r in ticks], RED_SHADE,
           0.12)
    ax_p.set_ylabel("군중 압력 P (1/s²)")
    ax_p.legend(loc="upper left")
    ax_c.plot(t, _arr([r["count"] for r in series]), color=BLUE, lw=1.5,
              label="count")
    ax_c.axhline(3.0, color="gray", ls="--", lw=1, label="3명 (유입 조건)")
    ax_c.set_ylabel("구역 인원 (명)")
    ax_c.legend(loc="upper left")
    ax_i.plot(t, _arr([r["inflow_ratio"] for r in series]), "o",
              color=ORANGE, ms=3, label="inflow_ratio")
    ax_i.plot(t, _arr(report["inflow_avg"]), color=BLUE, lw=1.5,
              label="inflow_avg (서버 5초 평균)")
    ax_i.axhline(0.6, color="gray", ls="--", lw=1, label="기준 0.6")
    _shade(ax_i, [r["inflow_alert"] == "true" for r in ticks],
           YELLOW_SHADE, 0.2)
    ax_i.set_ylabel("유입 비율")
    ax_i.set_xlabel("t (초)")
    ax_i.legend(loc="upper left")
    ax_i.set_xticks(np.arange(0, len(t) + 1, 10))
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def _num(value: str | None) -> float:
    """CSV 문자열 숫자. 빈칸은 NaN."""
    return np.nan if value is None else float(value)


def plot_sweep(report: dict, path: Path) -> None:
    """2칸. 왼쪽: x = pressure 기준(로그), y = unstable_s, seconds별 선.

    색 순서 파랑·주황·초록·노랑, 기본점은 검은 테두리. 오른쪽: x = ratio,
    y = first_inflow_t(창 5), min_count별 선.
    """
    plt = _pyplot()
    colors = (BLUE, ORANGE, GREEN, YELLOW)
    fig, (ax_s, ax_f) = plt.subplots(1, 2, figsize=(12, 4.5))
    inst = report["sweep_instability"]
    for color, sec in zip(colors, sorted({r["seconds"] for r in inst},
                                         key=int)):
        rows = [r for r in inst if r["seconds"] == sec]
        ax_s.plot([_num(r["pressure"]) for r in rows],
                  [_num(r["unstable_s"]) for r in rows], "o-", color=color,
                  lw=1.5, ms=4, label=f"{sec}초 연속")
    for r in inst:
        if r["is_default"] == "true":
            ax_s.plot(_num(r["pressure"]), _num(r["unstable_s"]), "o",
                      mfc="none", mec="black", ms=9, label="기본값")
    ax_s.set_xscale("log")
    # 격자 값을 그대로 눈금으로 (로그 눈금의 수식 빼기 기호는 한글 글꼴에 없다)
    grid = sorted({r["pressure"] for r in inst}, key=float)
    ax_s.set_xticks([float(p) for p in grid], labels=grid)
    ax_s.minorticks_off()
    ax_s.set_xlabel("pressure 기준 (1/s², 로그)")
    ax_s.set_ylabel("불안정 초 수 (unstable_s)")
    ax_s.legend()
    flow = [r for r in report["sweep_inflow"] if r["window_seconds"] == "5"]
    for color, mc in zip(colors, sorted({r["min_count"] for r in flow},
                                        key=float)):
        rows = [r for r in flow if r["min_count"] == mc]
        ax_f.plot([_num(r["ratio"]) for r in rows],
                  [_num(r["first_inflow_t"]) for r in rows], "o-",
                  color=color, lw=1.5, ms=4, label=f"min_count {mc}")
    for r in flow:
        if r["is_default"] == "true":
            ax_f.plot(_num(r["ratio"]), _num(r["first_inflow_t"]), "o",
                      mfc="none", mec="black", ms=9, label="기본값")
    ax_f.set_xlabel("ratio 기준 (창 5초)")
    ax_f.set_ylabel("첫 INFLOW 알림 초")
    ax_f.legend()
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def plot_lag(report: dict, path: Path) -> None:
    """3칸. 지연별 r(최대 지점 세로선) / inflow_avg와 t_in 표시 /
    평활 count와 t_cnt(50%) 표시. 이중 y축 없음.
    """
    plt = _pyplot()
    fig, (ax_r, ax_i, ax_c) = plt.subplots(3, 1, figsize=(12, 9))
    lags = report["lag_rows"]
    ax_r.plot([r["lag_s"] for r in lags], _arr([r["r"] for r in lags]),
              color=BLUE, lw=1.5)
    best = report["best_lag"]
    if best is not None:
        ax_r.axvline(best["lag_s"], color="gray", ls="--", lw=1,
                     label=f"최대 r 지연 {best['lag_s']}초")
        ax_r.legend(loc="upper left")
    ax_r.set_xlabel("지연 k (초, 양수면 유입이 앞섬)")
    ax_r.set_ylabel("피어슨 r")
    t = np.arange(len(report["series"]))
    event = report["events"][-1]  # (iii) 기준선 + 상승 폭 50%
    ax_i.plot(t, _arr(report["inflow_avg"]), color=BLUE, lw=1.5,
              label="inflow_avg")
    ax_i.axhline(0.6, color="gray", ls="--", lw=1, label="기준 0.6")
    if event["t_in"] is not None:
        ax_i.axvline(event["t_in"], color=ORANGE, lw=1.5,
                     label=f"t_in {event['t_in']}초")
    ax_i.set_ylabel("유입 비율")
    ax_i.legend(loc="upper left")
    ax_c.plot(t, _arr([r["count_smooth"] for r in report["series"]]),
              color=BLUE, lw=1.5, label="count (5초 평활)")
    if event["t_cnt"] is not None:
        ax_c.axvline(event["t_cnt"], color=GREEN, lw=1.5,
                     label=f"t_cnt (50%) {event['t_cnt']}초")
    ax_c.set_xlabel("t (초)")
    ax_c.set_ylabel("구역 인원 (명)")
    ax_c.legend(loc="upper left")
    for ax in (ax_i, ax_c):
        ax.set_xticks(np.arange(0, len(t) + 1, 10))
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def write_report(
    timeline_path: Path,
    sweep_dir: Path,
    out_dir: Path,
    server_alerts_path: Path | None = None,
) -> list[Path]:
    """timeline과 실행기 CSV(+ 서버 JSON)를 읽어 9.1절 D 파일을 모두 쓴다.

    sweep_dir의 {stem}_ticks·_alerts·_sweep_instability·_sweep_inflow.csv를
    읽는다. stem은 timeline 파일 이름에서 확장자를 뺀 것이다(E5Sweep이
    CSV 이름을 짓는 규칙과 같다. 그래서 같은 폴더의 다른 실행 CSV를 읽지
    않는다). 출력 파일 이름은 {video_id}_*다(9.1절). 쓴 경로 목록을
    돌려준다. out_dir이 data/raw 아래면 PermissionError(assert_not_raw),
    실행기 CSV가 없으면 FileNotFoundError(먼저 e5Sweep을 돌리라는 한국어
    메시지), 서버 JSON 최상위가 목록이 아니면 ValueError다. 모두 파일을
    쓰고 그림을 그리기 전에 검사한다. 서버 JSON은 BOM이 있어도 읽는다
    (PowerShell 저장).
    """
    out_dir = Path(out_dir)
    assert_not_raw(out_dir)
    timeline = load_timeline(timeline_path)
    video = timeline["meta"]["video_id"]
    stem = Path(timeline_path).stem
    specs = {"ticks": TICKS_COLUMNS, "alerts": ALERTS_COLUMNS,
             "sweep_instability": INSTABILITY_COLUMNS,
             "sweep_inflow": INFLOW_COLUMNS}
    files = {k: Path(sweep_dir) / f"{stem}_{k}.csv" for k in specs}
    missing = [str(p) for p in files.values() if not p.is_file()]
    if missing:
        raise FileNotFoundError(
            f"실행기 CSV가 없다: {', '.join(missing)}. 먼저 server/에서 "
            "./gradlew e5Sweep --args=\"<timeline> <출력 폴더>\"를 돌린다")
    runner = {k: read_runner_csv(files[k], specs[k]) for k in specs}
    server = None
    if server_alerts_path is not None:
        server = json.loads(Path(server_alerts_path).read_text(
            encoding="utf-8-sig"))
        if not isinstance(server, list):
            raise ValueError(
                f"{server_alerts_path}: 서버 알림 JSON 최상위는 목록이어야 "
                "한다 (GET /api/zones/{zone_id}/alerts 응답 그대로)")
    report = build_report(timeline, runner["ticks"], runner["alerts"],
                          runner["sweep_instability"],
                          runner["sweep_inflow"], server)
    out_dir.mkdir(parents=True, exist_ok=True)
    md = out_dir / f"{video}_e5.md"
    md.write_text(render_markdown(report, Path(timeline_path).as_posix()),
                  encoding="utf-8", newline="\n")
    paths = [md]
    for name, rows in (("series", report["series"]),
                       ("window", report["window"]),
                       ("lag", report["lag_rows"])):
        paths.append(out_dir / f"{video}_{name}.csv")
        write_csv(paths[-1], rows)
    paths.append(out_dir / f"{video}_series.png")
    plot_series(report, runner["ticks"], paths[-1])
    paths.append(out_dir / f"{video}_sweep.png")
    plot_sweep(report, paths[-1])
    paths.append(out_dir / f"{video}_lag.png")
    plot_lag(report, paths[-1])
    return paths


def main() -> None:
    """CLI: --timeline, --sweep-dir(기본 = --out), --server-alerts(선택),
    --out(기본 outputs/e5).
    """
    ap = argparse.ArgumentParser()
    ap.add_argument("--timeline", required=True)
    ap.add_argument("--sweep-dir", default=None,
                    help="실행기 CSV 폴더 (기본 = --out)")
    ap.add_argument("--server-alerts", default=None,
                    help="GET /api/zones/{zone_id}/alerts JSON (선택)")
    ap.add_argument("--out", default=str(OUT_DIR))
    args = ap.parse_args()
    out = Path(args.out)
    paths = write_report(
        Path(args.timeline), Path(args.sweep_dir or out), out,
        None if args.server_alerts is None else Path(args.server_alerts),
    )
    for path in paths:
        print(f"저장: {path}")


if __name__ == "__main__":
    main()
