"""E5 테스트 경계: src.flow.e5.analysis의 공개 함수 시험.

합성 timeline(e5_helpers.make_timeline)으로 셀 값·판정 대상·구역 P·
P 분포·끊김 통계·봉우리·셀 표를 손으로 계산한 값과 비교한다.
판정 규칙(불안정 연속·유입 평균·알림)은 Java 실행기 몫이라 여기서
시험하지 않는다.
"""
from __future__ import annotations

import copy
import json
import math
from pathlib import Path

import numpy as np
import pytest

from e5_helpers import make_timeline
from src.flow.cells import TemporalInstability
from src.flow.e5.analysis import (
    best_lag, cell_table, cell_values, compare_alerts, count_rate,
    eligible_mask, event_lags, first_index, lagged_corr, load_timeline,
    peak_times, pressure_quantiles, recompute_check, recompute_pressure,
    smooth, streak_breaks, window_stats, zone_pressure,
)
from src.flow.timeline_flow import fill_flow_fields


def three_cell_timeline() -> dict:
    """셀 3개(4.0·4.0·1.5㎡), 3초. 작은 셀(c-0002)에 큰 P를 둔다."""
    return make_timeline(
        areas=[4.0, 4.0, 1.5],
        density=[[1.0, 1.0, 1.0]] * 3,
        pressure=[[0.01, 0.03, 0.5], [None, 0.02, None],
                  [None, None, 0.4]],
        inflow=[None, 0.5, 0.7],
        count=[2.0, 2.0, None],
    )


def test_cell_values_turns_null_into_nan() -> None:
    """(T, n) 배열이고 null은 NaN이다."""
    p = cell_values(three_cell_timeline(), "pressure")
    assert p.shape == (3, 3)
    np.testing.assert_array_equal(
        np.isnan(p),
        [[False, False, False], [True, False, True], [True, True, False]],
    )
    assert p[0, 1] == 0.03


def test_eligible_mask_includes_two_square_metres() -> None:
    """면적 2.0㎡는 판정 대상, 1.99㎡는 아니다 (서버 ≥ 2.0)."""
    tl = make_timeline(
        areas=[2.0, 1.99, 4.0], density=[[0.0, 0.0, 0.0]],
        pressure=[[None, None, None]], inflow=[None], count=[0.0],
    )
    assert eligible_mask(tl).tolist() == [True, False, True]


def test_zone_pressure_is_max_of_eligible_cells() -> None:
    """판정 대상 셀 최댓값. 작은 셀은 무시, 모두 null이면 NaN."""
    zp = zone_pressure(three_cell_timeline())
    assert zp[0] == 0.03
    assert zp[1] == 0.02
    assert math.isnan(zp[2])


def test_pressure_quantiles_hand_computed() -> None:
    """표본 [0.01, 0.02, 0.03, 0.04]: 선형 보간 백분위, 0.02 초과 50%."""
    tl = make_timeline(
        areas=[4.0, 4.0, 1.0],
        density=[[1.0, 1.0, 1.0]] * 2,
        pressure=[[0.01, 0.02, 0.9], [0.03, 0.04, 0.9]],
        inflow=[None, None], count=[1.0, 1.0],
    )
    q = pressure_quantiles(tl, threshold=0.02)
    assert q["n"] == 4
    assert q["p50"] == pytest.approx(0.025)
    assert q["p90"] == pytest.approx(0.037)
    assert q["p95"] == pytest.approx(0.0385)
    assert q["p99"] == pytest.approx(0.0397)
    assert q["max"] == pytest.approx(0.04)
    assert q["over_ratio"] == pytest.approx(0.5)
    assert q["threshold_pct"] == pytest.approx(50.0)


def test_pressure_quantiles_without_samples_are_none() -> None:
    """non-null 표본이 없으면 표본 수 0, 나머지 값은 None."""
    tl = make_timeline(
        areas=[4.0], density=[[1.0]], pressure=[[None]],
        inflow=[None], count=[1.0],
    )
    q = pressure_quantiles(tl)
    assert q["n"] == 0
    assert all(q[k] is None for k in q if k != "n")


def test_streak_breaks_counts_null_and_below() -> None:
    """초과 연속이 null로 1번, 기준 이하로 1번 끊긴다."""
    assert streak_breaks([0.03, 0.03, None, 0.03, 0.01], 0.02) == (1, 1)


def test_streak_breaks_ignores_streak_at_end_and_equal_value() -> None:
    """끝에서 끝난 연속은 세지 않고, 기준과 같은 값은 초과가 아니다."""
    assert streak_breaks([0.01, 0.03, 0.03], 0.02) == (0, 0)
    assert streak_breaks([0.02, None, 0.02, 0.0], 0.02) == (0, 0)
    assert streak_breaks([0.03, 0.0, 0.03, None, None], 0.02) == (1, 1)


def test_peak_times_keeps_gap_and_ignores_nan() -> None:
    """큰 값부터 고르되 고른 초와 10초 미만이면 건너뛴다. NaN 무시."""
    s = np.zeros(40)
    s[3] = np.nan
    s[5], s[8], s[20], s[30] = 1.0, 0.9, 0.8, 0.5
    assert peak_times(s, k=3, min_gap_s=10) == [
        (5, 1.0), (20, 0.8), (30, 0.5),
    ]


def test_peak_times_returns_fewer_when_series_is_short() -> None:
    """간격 조건을 채우는 초가 모자라면 k개보다 적게 돌려준다."""
    s = np.array([np.nan, 0.2, 0.1, np.nan])
    assert peak_times(s, k=5, min_gap_s=10) == [(1, 0.2)]


def test_cell_table_columns_and_boundary() -> None:
    """셀 3개 가로 배치: 양 끝은 경계, 가운데는 구역 중심이라 아니다.

    pressure_null_ratio는 t ≥ 29이고 density > 0인 초 중 null 비율.
    """
    n_t = 32
    density = [[1.0, 0.0, 1.0] for _ in range(n_t)]
    pressure: list[list[float | None]] = [
        [None, 0, 0.0] for _ in range(n_t)
    ]
    pressure[29][0], pressure[30][0], pressure[31][0] = None, 0.03, 0.03
    pressure[0][2], pressure[1][2], pressure[2][2] = 0.03, None, 0.03
    tl = make_timeline(
        areas=[4.0, 1.5, 4.0], density=density, pressure=pressure,
        inflow=[None] * n_t, count=[2.0] * n_t,
    )
    table = cell_table(tl, threshold=0.02)
    assert [r["cell_id"] for r in table] == ["c-0000", "c-0001", "c-0002"]
    assert [r["area_m2"] for r in table] == [4.0, 1.5, 4.0]
    assert [r["eligible"] for r in table] == [True, False, True]
    assert [r["boundary"] for r in table] == [True, False, True]
    assert table[0]["pressure_null_ratio"] == pytest.approx(1 / 3)
    assert table[1]["pressure_null_ratio"] is None  # density 0뿐
    assert table[2]["pressure_null_ratio"] == 0.0
    assert (table[0]["breaks_null"], table[0]["breaks_below"]) == (0, 0)
    assert (table[2]["breaks_null"], table[2]["breaks_below"]) == (1, 1)


def test_load_timeline_rejects_spec_violation(tmp_path: Path) -> None:
    """규격 위반(count 키 없음) 파일은 ValueError, 정상 파일은 dict."""
    good = three_cell_timeline()
    ok_path = tmp_path / "ok.json"
    ok_path.write_text(json.dumps(good), encoding="utf-8")
    assert load_timeline(ok_path) == good
    bad = three_cell_timeline()
    del bad["frames"][1]["count"]
    bad_path = tmp_path / "bad.json"
    bad_path.write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(ValueError, match="count"):
        load_timeline(bad_path)


def alternating_timeline(n_t: int, density: float = 1.0) -> dict:
    """판정 대상 셀 1개, vx가 0·1을 번갈아, vy 0. pressure는 모두 null."""
    return make_timeline(
        areas=[4.0], density=[[density]] * n_t,
        pressure=[[None]] * n_t, inflow=[None] * n_t, count=[1.0] * n_t,
        vx=[[float(t % 2)] for t in range(n_t)], vy=[[0.0]] * n_t,
    )


def test_recompute_pressure_window_two_hand_computed() -> None:
    """T=2: t0 null, t1~t3 speed_var 0.25 = mean((±0.5)²), P 0.25."""
    out = recompute_pressure(alternating_timeline(4), 2.0)
    cells = [f["cells"][0] for f in out["frames"]]
    assert cells[0]["speed_var"] is None and cells[0]["pressure"] is None
    assert [c["speed_var"] for c in cells[1:]] == [0.25, 0.25, 0.25]
    assert [c["pressure"] for c in cells[1:]] == [0.25, 0.25, 0.25]
    assert [c["vx"] for c in cells] == [0.0, 1.0, 0.0, 1.0]


def test_recompute_pressure_keeps_input_unchanged() -> None:
    """입력 timeline은 바꾸지 않는다 (깊은 비교)."""
    tl = alternating_timeline(4)
    before = copy.deepcopy(tl)
    recompute_pressure(tl, 2.0)
    assert tl == before


def test_recompute_pressure_empty_cell_is_zero() -> None:
    """density 0 셀은 사람이 없어 pressure 0, 속도 null (규격 5절)."""
    out = recompute_pressure(alternating_timeline(4, density=0.0), 2.0)
    assert [f["cells"][0]["pressure"] for f in out["frames"]] == [0] * 4
    assert all(f["cells"][0]["vx"] is None for f in out["frames"])


def flow_file_timeline(n_t: int = 40) -> dict:
    """run_flow._fill_frames와 같은 순서(창 갱신 → fill_flow_fields)로
    T=30 speed_var·pressure를 채운 합성 파일. 셀 2개, 둘째 셀은 t%7==0일
    때 속도가 없다(머리 부족). 속도는 소수 2자리라 반올림 차이가 없다.
    """
    rng = np.random.default_rng(0)
    vxs = np.round(rng.uniform(-1, 1, (n_t, 2)), 2)
    vys = np.round(rng.uniform(-1, 1, (n_t, 2)), 2)
    tl = make_timeline(
        areas=[4.0, 4.0], density=[[1.25, 2.5]] * n_t,
        pressure=[[None, None]] * n_t, inflow=[None] * n_t,
        count=[3.0] * n_t,
    )
    tracker = TemporalInstability(2, window_s=30.0)
    for t, frame in enumerate(tl["frames"]):
        mean_v = np.stack([vxs[t], vys[t]], axis=1)
        quality = np.array([1, 0 if t % 7 == 0 else 1])
        s, _ = tracker.update(
            np.where((quality < 1)[:, None], np.nan, mean_v))
        frame["cells"] = fill_flow_fields(frame["cells"], mean_v, s,
                                          quality, 1)
    return tl


def test_recompute_check_matches_file_made_with_same_window() -> None:
    """T=30 재계산은 T=30으로 만든 파일 값과 같다 (차이 0, null 불일치 0)."""
    tl = flow_file_timeline()
    check = recompute_check(tl)
    assert check["n_both"] > 0
    assert check["max_abs_diff"] == 0.0
    assert check["n_null_mismatch"] == 0


def test_recompute_check_reports_differences() -> None:
    """파일 값 하나를 바꾸면 최대 차이, null로 바꾸면 불일치 1."""
    tl = flow_file_timeline()
    tl["frames"][35]["cells"][0]["pressure"] += 0.5
    tl["frames"][36]["cells"][0]["pressure"] = None
    check = recompute_check(tl)
    assert check["max_abs_diff"] == pytest.approx(0.5)
    assert check["n_null_mismatch"] == 1


def test_window_stats_three_rows() -> None:
    """40초, 셀 1개: T=10은 t9부터 31/40, T=30은 11/40, T=60은 없음."""
    rows = window_stats(alternating_timeline(40), threshold=0.02)
    assert [r["window_s"] for r in rows] == [10.0, 30.0, 60.0]
    assert rows[0]["nonnull_ratio"] == pytest.approx(31 / 40)
    assert rows[1]["nonnull_ratio"] == pytest.approx(11 / 40)
    assert rows[2]["nonnull_ratio"] == 0.0
    assert rows[0]["p95"] == pytest.approx(0.25)
    assert rows[0]["over_ratio"] == 1.0
    assert rows[2]["p95"] is None and rows[2]["over_ratio"] is None


def test_smooth_centred_window_three() -> None:
    """[0, 0, 3, 0, 0], 창 3 → [nan, 1, 1, 1, nan] (넘치는 끝은 NaN)."""
    out = smooth(np.array([0.0, 0.0, 3.0, 0.0, 0.0]), 3)
    np.testing.assert_allclose(out, [np.nan, 1.0, 1.0, 1.0, np.nan])


def test_smooth_nan_in_window_gives_nan() -> None:
    """NaN이 섞인 창은 NaN이다."""
    out = smooth(np.array([1.0, np.nan, 1.0, 1.0, 1.0]), 3)
    np.testing.assert_allclose(out, [np.nan, np.nan, np.nan, 1.0, np.nan])


@pytest.mark.parametrize("window", [2, 0, -1])
def test_smooth_rejects_even_or_small_window(window: int) -> None:
    """창이 짝수거나 1보다 작으면 ValueError."""
    with pytest.raises(ValueError):
        smooth(np.zeros(5), window)


def test_count_rate_of_straight_line() -> None:
    """count = 2t이면 안쪽 기울기 2.0명/초, 평활·차분이 닿지 않는 끝은 NaN."""
    rate = count_rate(2.0 * np.arange(20), window=5)
    np.testing.assert_allclose(rate[3:-3], 2.0)
    assert np.isnan(rate[:3]).all() and np.isnan(rate[-3:]).all()


def pulse_pair(n: int = 100, shift: int = 15) -> tuple[np.ndarray, ...]:
    """x = 1 (20 ≤ t < 30) 아니면 0, y = x를 shift초 뒤로 민 것."""
    x = np.zeros(n)
    x[20:30] = 1.0
    y = np.zeros(n)
    y[20 + shift:30 + shift] = 1.0
    return x, y


def test_lagged_corr_finds_shift_of_pulse() -> None:
    """y가 x보다 15초 늦으면 최대 r의 지연은 +15, r ≈ 1."""
    x, y = pulse_pair()
    rows = lagged_corr(x, y, range(-30, 61))
    best = best_lag(rows)
    assert best is not None
    assert best["lag_s"] == 15
    assert best["r"] == pytest.approx(1.0, abs=1e-9)
    assert best["n_pairs"] == 85
    assert set(rows[0]) == {"lag_s", "r", "n_pairs"}


def test_lagged_corr_too_few_pairs_or_flat_gives_none() -> None:
    """쌍이 min_pairs보다 적거나 한쪽 분산이 0이면 r None, best_lag None."""
    x, y = pulse_pair(n=20, shift=2)
    rows = lagged_corr(x, y, range(-3, 4))
    assert all(r["r"] is None for r in rows)
    assert best_lag(rows) is None
    flat = lagged_corr(np.ones(50), np.arange(50.0), [0], min_pairs=30)
    assert flat == [{"lag_s": 0, "r": None, "n_pairs": 50}]


def test_lagged_corr_skips_nan_pairs() -> None:
    """한쪽이 NaN인 쌍은 세지 않는다."""
    x, y = pulse_pair()
    x[:10] = np.nan
    rows = lagged_corr(x, y, [15])
    assert rows[0]["n_pairs"] == 75


def test_first_index() -> None:
    """처음 True인 위치, 없으면 None."""
    assert first_index(np.array([False, True, True])) == 1
    assert first_index(np.array([False, False])) is None


def rising_count(n: int = 100) -> np.ndarray:
    """t < 30은 1명, 30~40초에 1명씩 늘어 11명, 그 뒤 11명 (끝 NaN 2개)."""
    c = np.clip(1.0 + np.arange(n) - 30, 1.0, 11.0)
    c[-2:] = np.nan
    return c


def test_event_lags_hand_computed() -> None:
    """t_in 20. 기준선 1, 상승 폭 10: ≥3명 t32, +10% t31, +50% t35."""
    inflow_avg = np.zeros(100)
    inflow_avg[:5] = np.nan
    inflow_avg[20:25] = 0.8
    rows = event_lags(inflow_avg, rising_count(), t_alarm=25)
    assert [r["level"] for r in rows] == [3.0, 2.0, 6.0]
    assert [r["t_cnt"] for r in rows] == [32, 31, 35]
    assert all(r["t_in"] == 20 for r in rows)
    assert [r["lag_signal_s"] for r in rows] == [12, 11, 15]
    assert [r["lag_alarm_s"] for r in rows] == [7, 6, 10]
    assert set(rows[0]) == {"criterion", "level", "t_cnt", "t_in",
                            "lag_signal_s", "t_alarm", "lag_alarm_s"}


def test_event_lags_without_signal_or_alarm_gives_none() -> None:
    """유입 신호·경보가 없으면 그 시간 차는 None, t_cnt는 그대로."""
    rows = event_lags(np.full(100, 0.1), rising_count(), t_alarm=None)
    assert all(r["t_in"] is None and r["lag_signal_s"] is None
               for r in rows)
    assert all(r["t_alarm"] is None and r["lag_alarm_s"] is None
               for r in rows)
    assert rows[2]["t_cnt"] == 35


def server_alert(t: int, reason: str, level: str, value: float | None,
                 cell_ids: list[str]) -> dict:
    """GET /api/zones/{id}/alerts 원소 모양 (ID·시각·문구 포함)."""
    return {"type": "alert", "alert_id": f"a-20261116-{t:04d}",
            "zone_id": "zone-test", "t": t,
            "frame_ts": "2026-11-16T10:00:00.000+09:00", "level": level,
            "reason": reason, "message": "문구", "value": value,
            "cell_ids": cell_ids, "acked_at": None}


def runner_alert(t: str, reason: str, level: str, value: str | None,
                 cell_ids: str | None) -> dict:
    """실행기 alerts.csv를 읽은 행 (문자열, 빈칸은 None)."""
    return {"t": t, "reason": reason, "level": level, "value": value,
            "cell_ids": cell_ids}


SERVER = [
    server_alert(2, "INSTABILITY", "CRITICAL", 0.03, ["c-0000", "c-0001"]),
    server_alert(12, "INFLOW", "CAUTION", 0.8, []),
]
RUNNER = [
    runner_alert("2", "INSTABILITY", "CRITICAL", "0.03", "c-0000;c-0001"),
    runner_alert("12", "INFLOW", "CAUTION", "0.8", None),
]


def test_compare_alerts_same_lists_match() -> None:
    """같은 알림이면 일치. 서버 JSON의 ID·시각·문구는 보지 않는다."""
    out = compare_alerts(SERVER, RUNNER)
    assert out["match"] is True
    assert (out["n_server"], out["n_runner"]) == (2, 2)
    assert out["diffs"] == []


def test_compare_alerts_reports_different_row() -> None:
    """t 하나가 다르면 diffs 1행 (순번, 서버 행, 실행기 행)."""
    runner = [RUNNER[0], runner_alert("13", "INFLOW", "CAUTION", "0.8",
                                      None)]
    out = compare_alerts(SERVER, runner)
    assert out["match"] is False
    assert len(out["diffs"]) == 1
    index, srv, run = out["diffs"][0]
    assert index == 1
    assert srv["t"] == 12 and run["t"] == 13


def test_compare_alerts_value_tolerance_and_none() -> None:
    """value는 1e-9 안이면 같고, 둘 다 None이면 같고, 한쪽만 None이면 다르다."""
    near = [runner_alert("2", "INSTABILITY", "CRITICAL", "0.0300000005",
                         "c-0000;c-0001"), RUNNER[1]]
    assert compare_alerts(SERVER, near)["match"] is True
    srv_none = [server_alert(12, "INFLOW", "CAUTION", None, [])]
    run_none = [runner_alert("12", "INFLOW", "CAUTION", None, None)]
    assert compare_alerts(srv_none, run_none)["match"] is True
    assert compare_alerts(srv_none, [RUNNER[1]])["match"] is False


def test_compare_alerts_different_lengths() -> None:
    """개수가 다르면 남는 행이 diffs에 한쪽 None으로 들어간다."""
    out = compare_alerts(SERVER, RUNNER[:1])
    assert out["match"] is False
    assert out["diffs"] == [(1, out["diffs"][0][1], None)]
    assert out["diffs"][0][1]["reason"] == "INFLOW"
