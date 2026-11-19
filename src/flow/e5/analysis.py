"""E5 분석: 불안정 지표 P 시계열·셀 표·창 길이 T 확인·유입 시간 차.

파일을 쓰지 않는 순수 함수만 둔다(numpy만). 판정 규칙(불안정 연속·
유입 평균·히스테리시스·알림)은 계산하지 않는다. 그 값은 Java 실행기
e5Sweep의 CSV에서 읽는다 (계획 확정 2).
"""
from __future__ import annotations

import copy
import json
from collections.abc import Sequence
from pathlib import Path

import numpy as np

from src.flow.cells import TemporalInstability
from src.flow.inflow import boundary_inward
from src.flow.timeline_flow import fill_flow_fields
from src.predict.schema import validate_timeline

FIRST_FULL_T = 29  # 30초 창이 처음 차는 t (cells.py:125-127)
QUANTILES = (50, 90, 95, 99)
T_WINDOWS = (10.0, 30.0, 60.0)


def load_timeline(path: Path) -> dict:
    """timeline.json을 읽어 validate_timeline으로 확인한 dict.

    규격에 어긋나면 ValueError다.
    """
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    validate_timeline(data)
    return data


def cell_values(timeline: dict, key: str) -> np.ndarray:
    """(T, n) float 배열. null은 NaN. key는 density·pressure 등."""
    return np.array(
        [[np.nan if c[key] is None else float(c[key]) for c in f["cells"]]
         for f in timeline["frames"]],
        dtype=np.float64,
    ).reshape(len(timeline["frames"]), len(timeline["meta"]["cells"]))


def eligible_mask(timeline: dict, min_area_m2: float = 2.0) -> np.ndarray:
    """(n,) bool. walkable_area_m2 ≥ min_area_m2 (서버 기본값 2.0)."""
    return np.array(
        [c["walkable_area_m2"] >= min_area_m2
         for c in timeline["meta"]["cells"]],
        dtype=bool,
    )


def zone_pressure(
    timeline: dict, min_area_m2: float = 2.0,
) -> np.ndarray:
    """(T,) 구역 P = 판정 대상 셀 non-null pressure 최댓값 (제안 P3).

    판정 대상 셀이 모두 null이면 NaN.
    """
    p = cell_values(timeline, "pressure")[:, eligible_mask(
        timeline, min_area_m2)]
    out = np.full(p.shape[0], np.nan)
    has = np.isfinite(p).any(axis=1)
    out[has] = np.nanmax(p[has], axis=1)
    return out


def pressure_quantiles(
    timeline: dict, threshold: float = 0.02, min_area_m2: float = 2.0,
) -> dict[str, float | int | None]:
    """판정 대상 셀-초 non-null P의 분포.

    키: n(표본 수), p50·p90·p95·p99(선형 보간 백분위), max,
    over_ratio(threshold 초과 비율), threshold_pct(threshold 이하 표본
    비율 × 100 = threshold의 백분위 위치). 표본 0이면 n 밖의 값은 None.
    """
    p = cell_values(timeline, "pressure")[:, eligible_mask(
        timeline, min_area_m2)]
    v = p[np.isfinite(p)]
    keys = [f"p{q}" for q in QUANTILES] + [
        "max", "over_ratio", "threshold_pct"]
    if v.size == 0:
        return {"n": 0, **{k: None for k in keys}}
    out: dict[str, float | int | None] = {"n": int(v.size)}
    for q in QUANTILES:
        out[f"p{q}"] = float(np.percentile(v, q))
    out["max"] = float(v.max())
    out["over_ratio"] = float((v > threshold).mean())
    out["threshold_pct"] = float((v <= threshold).mean() * 100)
    return out


def streak_breaks(
    pressures: Sequence[float | None], threshold: float,
) -> tuple[int, int]:
    """기준 초과 연속(길이 ≥ 1)이 끝난 원인을 센다 (자료 기술, 판정 아님).

    (null로 끊김, 기준 이하로 끊김). 시계열 끝에서 끝난 연속은 세지
    않는다. 기준과 같은 값은 초과가 아니다(서버 InstabilityTracker와
    같은 '초과'). NaN은 null로 본다. null 건너뜀 [토론](12장) 자료.
    """
    by_null = by_below = 0
    in_streak = False
    for p in pressures:
        missing = p is None or not np.isfinite(p)
        if not missing and p > threshold:
            in_streak = True
            continue
        if in_streak:
            if missing:
                by_null += 1
            else:
                by_below += 1
        in_streak = False
    return by_null, by_below


def peak_times(
    series: np.ndarray, k: int = 5, min_gap_s: int = 10,
) -> list[tuple[int, float]]:
    """값이 큰 순서로 서로 min_gap_s초 이상 떨어진 (t, 값) k개. NaN 무시.

    같은 값이면 앞 초를 먼저 고른다. 조건을 채우는 초가 모자라면 k개보다
    적다.
    """
    s = np.asarray(series, dtype=np.float64)
    order = sorted(
        (t for t in range(s.size) if np.isfinite(s[t])),
        key=lambda t: (-s[t], t),
    )
    picked: list[tuple[int, float]] = []
    for t in order:
        if len(picked) == k:
            break
        if all(abs(t - u) >= min_gap_s for u, _ in picked):
            picked.append((t, float(s[t])))
    return picked


def cell_table(timeline: dict, threshold: float = 0.02) -> list[dict]:
    """셀별 표 (안건 #17·[토론] 근거).

    키: cell_id, area_m2, eligible(면적 ≥ 2㎡), boundary(boundary_inward
    재사용), pressure_null_ratio(t ≥ 29이고 소수 2자리 density > 0인
    초 중 pressure null 비율, 그런 초가 없으면 None), breaks_null,
    breaks_below(streak_breaks).
    """
    meta = timeline["meta"]
    is_boundary, _ = boundary_inward(meta["cells"], meta["cell_size_m"])
    eligible = eligible_mask(timeline)
    density = np.round(cell_values(timeline, "density"), 2)
    pressure = cell_values(timeline, "pressure")
    rows = []
    for i, cell in enumerate(meta["cells"]):
        occupied = density[FIRST_FULL_T:, i] > 0
        late = pressure[FIRST_FULL_T:, i][occupied]
        null_ratio = (
            float(np.isnan(late).mean()) if late.size else None
        )
        breaks_null, breaks_below = streak_breaks(
            pressure[:, i].tolist(), threshold,
        )
        rows.append({
            "cell_id": cell["cell_id"],
            "area_m2": cell["walkable_area_m2"],
            "eligible": bool(eligible[i]),
            "boundary": bool(is_boundary[i]),
            "pressure_null_ratio": null_ratio,
            "breaks_null": breaks_null,
            "breaks_below": breaks_below,
        })
    return rows


def recompute_pressure(timeline: dict, window_s: float) -> dict:
    """저장된 vx·vy로 창 window_s초 speed_var·pressure를 다시 낸 사본.

    셀 순서대로 (vx, vy)를 넣는다(둘 중 하나라도 null이면 NaN).
    TemporalInstability(n, window_s)로 S를 내고 fill_flow_fields(cells,
    v, S, quality=(v 유한)·1, min_quality=1)로 같은 반올림 규칙을 쓴다.
    입력은 바꾸지 않는다. vx·vy가 0.01 m/s로 반올림돼 있어 원래 값과
    약 1.7×10⁻⁵ m²/s² 차이가 날 수 있다 (조사 C.6).
    """
    out = copy.deepcopy(timeline)
    vx = cell_values(timeline, "vx")
    vy = cell_values(timeline, "vy")
    tracker = TemporalInstability(vx.shape[1], window_s=window_s)
    for t, frame in enumerate(out["frames"]):
        v = np.stack([vx[t], vy[t]], axis=1)
        quality = np.isfinite(v).all(axis=1).astype(int)
        s, _ = tracker.update(v)
        frame["cells"] = fill_flow_fields(frame["cells"], v, s, quality, 1)
    return out


def recompute_check(timeline: dict) -> dict[str, float | int | None]:
    """T=30 재계산 pressure와 파일 pressure 비교 (방법 검증, 제안 P7).

    키: n_both(둘 다 숫자인 셀-초 수), max_abs_diff(그 최대 절대 차이,
    n_both가 0이면 None), n_null_mismatch(한쪽만 null인 셀-초 수).
    """
    file_p = cell_values(timeline, "pressure")
    new_p = cell_values(recompute_pressure(timeline, 30.0), "pressure")
    both = np.isfinite(file_p) & np.isfinite(new_p)
    diff = np.abs(file_p[both] - new_p[both])
    return {
        "n_both": int(both.sum()),
        "max_abs_diff": float(diff.max()) if diff.size else None,
        "n_null_mismatch": int(
            (np.isfinite(file_p) != np.isfinite(new_p)).sum()),
    }


def window_stats(timeline: dict, threshold: float = 0.02) -> list[dict]:
    """T ∈ T_WINDOWS마다 재계산한 판정 대상 P의 분포 (제안 P7).

    행 = {window_s, nonnull_ratio, p95, over_ratio}. 분모는 모든 t의
    판정 대상 셀 중 소수 2자리 density > 0인 셀-초다(T가 길면 앞
    T−1초가 null이라 비율이 준다). p95·over_ratio(threshold 초과 비율)는
    non-null P로 내고, 없으면 None이다. 알림 수는 내지 않는다.
    """
    eligible = eligible_mask(timeline)
    occupied = np.round(cell_values(timeline, "density"), 2)[:, eligible] > 0
    rows = []
    for window_s in T_WINDOWS:
        p = cell_values(recompute_pressure(timeline, window_s),
                        "pressure")[:, eligible][occupied]
        v = p[np.isfinite(p)]
        rows.append({
            "window_s": window_s,
            "nonnull_ratio": (
                float(v.size / p.size) if p.size else None),
            "p95": float(np.percentile(v, 95)) if v.size else None,
            "over_ratio": float((v > threshold).mean()) if v.size else None,
        })
    return rows


def smooth(x: np.ndarray, window: int) -> np.ndarray:
    """가운데 이동평균(window 홀수).

    창이 넘치는 끝과 NaN이 섞인 창은 NaN이다. window가 짝수거나 1보다
    작으면 ValueError다.
    """
    if window < 1 or window % 2 == 0:
        raise ValueError(f"창은 1 이상 홀수여야 한다: {window}")
    x = np.asarray(x, dtype=np.float64)
    half = window // 2
    out = np.full(x.size, np.nan)
    for t in range(half, x.size - half):
        out[t] = x[t - half:t + half + 1].mean()  # NaN이 있으면 NaN
    return out


def count_rate(count: np.ndarray, window: int = 5) -> np.ndarray:
    """smooth(count, window)의 가운데 차분 (명/초). 양 끝은 NaN."""
    s = smooth(count, window)
    out = np.full(s.size, np.nan)
    out[1:-1] = (s[2:] - s[:-2]) / 2
    return out


def lagged_corr(
    x: np.ndarray, y: np.ndarray, lags: Sequence[int],
    min_pairs: int = 30,
) -> list[dict]:
    """지연 k마다 x[t]와 y[t+k]의 피어슨 r. k > 0이면 x가 k초 앞섬.

    둘 다 유한한 쌍만 쓴다. 쌍 < min_pairs이거나 한쪽 분산이 0이면
    r은 None. 행 = {"lag_s", "r", "n_pairs"}.
    """
    x = np.asarray(x, dtype=np.float64)
    y = np.asarray(y, dtype=np.float64)
    n = min(x.size, y.size)
    rows = []
    for k in lags:
        lo, hi = max(0, -k), min(n, n - k)
        a = x[lo:hi] if hi > lo else np.empty(0)
        b = y[lo + k:hi + k] if hi > lo else np.empty(0)
        ok = np.isfinite(a) & np.isfinite(b)
        a, b = a[ok], b[ok]
        r = None
        if a.size >= min_pairs and a.std() > 0 and b.std() > 0:
            r = float(np.corrcoef(a, b)[0, 1])
        rows.append({"lag_s": int(k), "r": r, "n_pairs": int(a.size)})
    return rows


def best_lag(rows: Sequence[dict]) -> dict | None:
    """r이 가장 큰 행(같으면 앞 행). r이 모두 None이면 None."""
    scored = [row for row in rows if row["r"] is not None]
    return max(scored, key=lambda row: row["r"]) if scored else None


def first_index(mask: np.ndarray) -> int | None:
    """처음 True인 위치. 없으면 None."""
    hits = np.flatnonzero(np.asarray(mask, dtype=bool))
    return int(hits[0]) if hits.size else None


def event_lags(
    inflow_avg: np.ndarray,
    count_s: np.ndarray,
    t_alarm: int | None,
    ratio: float = 0.6,
    abs_count: float = 3.0,
    fractions: Sequence[float] = (0.1, 0.5),
    baseline_s: int = 30,
) -> list[dict]:
    """사건 기준 시간 차 표 (제안 P8).

    inflow_avg는 실행기 ticks.csv 값(서버 InflowMonitor 평균)이다.
    t_in = 처음 inflow_avg > ratio인 초. count_s(평활 count)의 기준
    (i) ≥ abs_count, (ii)(iii) ≥ 기준선 + f × (최댓값 − 기준선),
    기준선 = count_s[:baseline_s]의 nanmedian. 행 = {"criterion",
    "level"(인원 기준값), "t_cnt", "t_in", "lag_signal_s"(t_cnt − t_in),
    "t_alarm", "lag_alarm_s"(t_cnt − t_alarm)}. 한쪽이 None이면 시간
    차도 None. NaN은 기준에 닿지 않은 것으로 본다.
    """
    inflow_avg = np.asarray(inflow_avg, dtype=np.float64)
    count_s = np.asarray(count_s, dtype=np.float64)
    with np.errstate(invalid="ignore"):
        t_in = first_index(inflow_avg > ratio)
        base = float(np.nanmedian(count_s[:baseline_s]))
        rise = float(np.nanmax(count_s)) - base
    levels = [(f"count ≥ {abs_count:g}명", abs_count)] + [
        (f"기준선 + 상승 폭 {f:.0%}", base + f * rise) for f in fractions
    ]
    rows = []
    for criterion, level in levels:
        with np.errstate(invalid="ignore"):
            t_cnt = first_index(count_s >= level)
        rows.append({
            "criterion": criterion,
            "level": level,
            "t_cnt": t_cnt,
            "t_in": t_in,
            "lag_signal_s": _diff(t_cnt, t_in),
            "t_alarm": t_alarm,
            "lag_alarm_s": _diff(t_cnt, t_alarm),
        })
    return rows


def _diff(a: int | None, b: int | None) -> int | None:
    """a − b. 한쪽이 None이면 None."""
    return None if a is None or b is None else a - b


def _alert_key(
    t: object, reason: object, level: object, value: object,
    cell_ids: object,
) -> dict:
    """비교용 알림 (t 정수, value float|None, cell_ids 목록)."""
    if isinstance(cell_ids, str):
        cell_ids = cell_ids.split(";") if cell_ids else []
    return {
        "t": int(t), "reason": str(reason), "level": str(level),
        "value": None if value is None else float(value),
        "cell_ids": list(cell_ids or []),
    }


def _same_alert(a: dict, b: dict) -> bool:
    """t·사유·단계·셀이 같고 value가 둘 다 None이거나 차이 ≤ 1e-9."""
    if (a["t"], a["reason"], a["level"], a["cell_ids"]) != (
            b["t"], b["reason"], b["level"], b["cell_ids"]):
        return False
    if a["value"] is None or b["value"] is None:
        return a["value"] is None and b["value"] is None
    return abs(a["value"] - b["value"]) <= 1e-9


def compare_alerts(
    server: Sequence[dict], runner: Sequence[dict],
) -> dict:
    """서버 알림(REST JSON 원소)과 실행기 alerts.csv 행을 순서대로 비교.

    비교 키: t, reason, level, cell_ids(목록), value(둘 다 None이거나
    차이 ≤ 1e-9). 결과 = {"match": bool, "n_server", "n_runner",
    "diffs": [(순번, 서버 행, 실행기 행)]}. 개수가 다르면 남는 행은 다른
    쪽이 None이다. 서버 JSON의 다른 키(ID·시각·문구)는 보지 않는다
    (제안 P17).
    """
    keys = ("t", "reason", "level", "value", "cell_ids")
    srv = [_alert_key(*(row[k] for k in keys)) for row in server]
    run = [_alert_key(*(row[k] for k in keys)) for row in runner]
    diffs = []
    for i in range(max(len(srv), len(run))):
        a = srv[i] if i < len(srv) else None
        b = run[i] if i < len(run) else None
        if a is None or b is None or not _same_alert(a, b):
            diffs.append((i, a, b))
    return {"match": not diffs, "n_server": len(srv), "n_runner": len(run),
            "diffs": diffs}


def _opt(x: float) -> float | None:
    """NaN이면 None, 아니면 float (CSV·md용)."""
    return None if np.isnan(x) else float(x)


def build_report(
    timeline: dict,
    ticks: Sequence[dict],
    alerts: Sequence[dict],
    sweep_instability: Sequence[dict],
    sweep_inflow: Sequence[dict],
    server_alerts: Sequence[dict] | None = None,
) -> dict:
    """보고서에 쓸 값을 모두 계산한 dict (파일 쓰기 없음).

    ticks·alerts·sweep_*는 실행기 CSV를 읽은 행(문자열 dict, 빈칸 None)
    이다. 키: series(초별 행), cells, quantiles, peaks, window,
    recompute_check, lag_rows, best_lag, events, sweep_instability,
    sweep_inflow, default_instability·default_inflow(is_default 행),
    server_check(server_alerts가 None이면 None), meta(video_id,
    duration_s, models, n_cells, n_eligible). 그림용으로
    cell_pressure(판정 대상 셀 ID → 초별 P, null은 None)와
    inflow_avg(초별 실행기 평균, 빈칸은 None)도 담는다. ticks의 t가
    timeline 초 0..T−1과 다르면(다른 timeline으로 돌린 실행기 결과)
    ValueError다.
    """
    frames = timeline["frames"]
    if [int(row["t"]) for row in ticks] != list(range(len(frames))):
        raise ValueError(
            "ticks.csv의 t가 timeline 초와 다르다. 같은 timeline으로 "
            "e5Sweep을 돌렸는지 확인한다")
    count = np.array(
        [np.nan if f["count"] is None else float(f["count"])
         for f in frames])
    count_s = smooth(count, 5)
    rate = count_rate(count, 5)
    zp = zone_pressure(timeline)
    eligible = eligible_mask(timeline)
    pressure = cell_values(timeline, "pressure")
    n_pressure = np.isfinite(pressure[:, eligible]).sum(axis=1)
    inflow_avg = np.array(
        [np.nan if row["inflow_avg"] is None else float(row["inflow_avg"])
         for row in ticks])
    series = [
        {"t": t, "count": _opt(count[t]), "count_smooth": _opt(count_s[t]),
         "count_rate": _opt(rate[t]),
         "inflow_ratio": frames[t]["inflow_ratio"],
         "zone_pressure": _opt(zp[t]), "n_pressure": int(n_pressure[t])}
        for t in range(len(frames))
    ]
    t_alarm = next(
        (int(a["t"]) for a in alerts if a["reason"] == "INFLOW"), None)
    lag_rows = lagged_corr(inflow_avg, rate, range(-30, 61))
    meta = timeline["meta"]
    return {
        "series": series,
        "cells": cell_table(timeline),
        "quantiles": pressure_quantiles(timeline),
        "peaks": peak_times(zp),
        "window": window_stats(timeline),
        "recompute_check": recompute_check(timeline),
        "lag_rows": lag_rows,
        "best_lag": best_lag(lag_rows),
        "events": event_lags(inflow_avg, count_s, t_alarm),
        "sweep_instability": list(sweep_instability),
        "sweep_inflow": list(sweep_inflow),
        "default_instability": next(
            (r for r in sweep_instability if r["is_default"] == "true"),
            None),
        "default_inflow": next(
            (r for r in sweep_inflow if r["is_default"] == "true"), None),
        "server_check": (
            None if server_alerts is None
            else compare_alerts(server_alerts, alerts)),
        "meta": {
            "video_id": meta["video_id"], "duration_s": meta["duration_s"],
            "models": meta["models"], "n_cells": len(meta["cells"]),
            "n_eligible": int(eligible.sum()),
        },
        "cell_pressure": {
            c["cell_id"]: [_opt(v) for v in pressure[:, i]]
            for i, c in enumerate(meta["cells"]) if eligible[i]
        },
        "inflow_avg": [_opt(v) for v in inflow_avg],
    }
