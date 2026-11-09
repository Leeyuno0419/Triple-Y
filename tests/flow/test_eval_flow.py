"""S12 테스트 경계: eval_flow.g1_decision 시험 (기획 5.2 판정 규칙).

추정기별 요약 지표를 손으로 정해 넣고 채택 여부만 확인한다.
기대 판정은 기획 5.2와 구현 계획 7.2·7.3·8의 규칙에서 손으로 정했다.
"""
from __future__ import annotations

from src.flow.eval_flow import choose_fallback, g1_decision

PRE = {
    "noise_floor_median": 0.0040,
    "mae_advect": 0.200,
    "moving_speed_ratio": 1.0,
}


def test_adopts_when_noise_lower_and_mae_not_worse() -> None:
    """노이즈 0.0030 < 0.0040, MAE 0.190 <= 0.200, 속력비 0.9면 채택한다."""
    ft = {
        "noise_floor_median": 0.0030,
        "mae_advect": 0.190,
        "moving_speed_ratio": 0.9,
    }
    adopt, reason = g1_decision(ft, PRE)
    assert adopt is True
    assert isinstance(reason, str) and reason


def test_rejects_when_noise_not_lower() -> None:
    """노이즈 0.0040 = 0.0040(낮지 않음)이면 MAE가 좋아도 채택하지 않는다."""
    ft = {
        "noise_floor_median": 0.0040,
        "mae_advect": 0.150,
        "moving_speed_ratio": 1.0,
    }
    adopt, reason = g1_decision(ft, PRE)
    assert adopt is False
    assert "fail: noise" in reason and "fail: mae" not in reason


def test_rejects_when_mae_worse_beyond_tolerance() -> None:
    """mae_tol 5%: 기준 0.200 대비 0.205는 허용, 0.215는 불채택이다."""
    within = {
        "noise_floor_median": 0.0030,
        "mae_advect": 0.205,
        "moving_speed_ratio": 1.0,
    }
    beyond = dict(within, mae_advect=0.215)
    assert g1_decision(within, PRE, mae_tol=0.05)[0] is True
    adopt, reason = g1_decision(beyond, PRE, mae_tol=0.05)
    assert adopt is False
    assert "fail: mae" in reason and "fail: noise" not in reason


def test_rejects_zero_flow_estimator() -> None:
    """흐름을 전부 0으로 내면 노이즈 0·MAE=현재값 유지여도 채택하지 않는다.

    MAE 0.200은 기준과 같아 조건 2를 통과하지만, 속력비 0이라 불채택이다.
    """
    zero = {
        "noise_floor_median": 0.0,
        "mae_advect": 0.200,
        "moving_speed_ratio": 0.0,
    }
    adopt, reason = g1_decision(zero, PRE)
    assert adopt is False
    assert "fail: speed" in reason and "fail: mae" not in reason


def test_rejects_near_zero_flow_on_speed_only() -> None:
    """속력비 0.01·노이즈 0이면 노이즈·MAE는 통과하고 속력만 걸려 불채택이다."""
    near_zero = {
        "noise_floor_median": 0.0,
        "mae_advect": 0.200,
        "moving_speed_ratio": 0.01,
    }
    adopt, reason = g1_decision(near_zero, PRE)
    assert adopt is False
    assert "fail: speed" in reason
    assert "fail: noise" not in reason and "fail: mae" not in reason


def test_missing_or_nan_metric_is_not_adopted() -> None:
    """mae_advect가 NaN이거나 속력비가 빠지면 불채택이고 근거에 이름이 남는다."""
    nan_mae = {
        "noise_floor_median": 0.0030,
        "mae_advect": float("nan"),
        "moving_speed_ratio": 1.0,
    }
    no_speed = {"noise_floor_median": 0.0030, "mae_advect": 0.190}
    adopt, reason = g1_decision(nan_mae, PRE)
    assert adopt is False
    assert reason == "missing or non-finite: ft.mae_advect"
    adopt, reason = g1_decision(no_speed, PRE)
    assert adopt is False
    assert reason == "missing or non-finite: ft.moving_speed_ratio"


def test_nan_in_pretrained_reference_is_not_adopted() -> None:
    """기준(pre)의 노이즈 바닥이 NaN이면 후보가 좋아 보여도 불채택이다."""
    ft = {
        "noise_floor_median": 0.0020,
        "mae_advect": 0.190,
        "moving_speed_ratio": 1.0,
    }
    pre = dict(PRE, noise_floor_median=float("nan"))
    adopt, reason = g1_decision(ft, pre)
    assert adopt is False
    assert reason == "missing or non-finite: pre.noise_floor_median"


def _m(noise: float, mae: float, ratio: float = 1.0) -> dict[str, float]:
    """후보 추정기 지표 사전을 만든다."""
    return {
        "noise_floor_median": noise,
        "mae_advect": mae,
        "moving_speed_ratio": ratio,
    }


def test_fallback_picks_estimator_best_on_both_else_none() -> None:
    """불채택 시 노이즈·mae_advect 둘 다 가장 나은 사전학습 추정기를 고른다.

    DIS가 둘 다 최저면 "dis". 노이즈 최저(farneback)와 MAE 최저(raft)가
    엇갈리면 팀이 정하므로 None이다 (계획 7.3).
    """
    clear = {
        "raft": _m(0.0040, 0.200),
        "farneback": _m(0.0050, 0.230),
        "dis": _m(0.0035, 0.190),
    }
    split = {
        "raft": _m(0.0040, 0.190),
        "farneback": _m(0.0030, 0.230),
    }
    assert choose_fallback(clear) == "dis"
    assert choose_fallback(split) is None


def test_rejects_uniformly_shrunk_flow() -> None:
    """흐름을 0.6배로 줄인 RAFT는 노이즈가 0.36배로 줄어도 불채택이다.

    속력 정규화 노이즈 0.0015 / 0.6² = 0.00417 > 0.0040이다.
    (0.36배 = 0.00144는 정규화 후 정확히 0.0040이라 부동소수점 경계에
    걸리므로 조금 위인 0.0015를 쓴다.)
    """
    shrunk = {
        "noise_floor_median": 0.0015,
        "mae_advect": 0.200,
        "moving_speed_ratio": 0.6,
    }
    adopt, reason = g1_decision(shrunk, PRE)
    assert adopt is False
    assert "fail: noise" in reason


def test_adopts_genuinely_lower_noise_at_same_speed() -> None:
    """속력비 1.0에서 노이즈 0.0020(기준의 0.5배)이면 채택한다."""
    better = {
        "noise_floor_median": 0.0020,
        "mae_advect": 0.200,
        "moving_speed_ratio": 1.0,
    }
    assert g1_decision(better, PRE)[0] is True


def test_exaggerated_flow_judged_on_normalised_noise() -> None:
    """속력비 1.5·노이즈 0.0048(1.2배)은 정규화 0.00213 < 0.0040이라 채택한다."""
    fast = {
        "noise_floor_median": 0.0048,
        "mae_advect": 0.200,
        "moving_speed_ratio": 1.5,
    }
    assert g1_decision(fast, PRE)[0] is True


def test_rejects_speed_ratio_above_max() -> None:
    """속력비 2.5는 기본 상한 2.0을 넘어 불채택, 상한 None이면 채택한다.

    정규화 노이즈 0.0048 / 2.5² = 0.00077 < 0.0040이라 노이즈는 통과한다.
    """
    too_fast = {
        "noise_floor_median": 0.0048,
        "mae_advect": 0.200,
        "moving_speed_ratio": 2.5,
    }
    adopt, reason = g1_decision(too_fast, PRE)
    assert adopt is False
    assert "fail: speed" in reason and "fail: noise" not in reason
    assert g1_decision(too_fast, PRE, max_speed_ratio=None)[0] is True


def test_reason_reports_persist_skill_without_gating() -> None:
    """mae_persist가 있으면 근거에 skill(= persist − advect)을 적되 판정엔 안 쓴다.

    skill 0.25 − 0.19 = 0.06은 양수, 0.15 − 0.19 = −0.04는 음수지만
    둘 다 채택한다. 수치는 유효숫자 3자리(.3g)로 적는다.
    """
    ft = {
        "noise_floor_median": 0.0020,
        "mae_advect": 0.190,
        "moving_speed_ratio": 1.0,
        "mae_persist": 0.250,
    }
    adopt, reason = g1_decision(ft, PRE)
    assert adopt is True
    assert "mae_persist 0.25, skill 0.06" in reason
    assert "noise_n 0.002 vs 0.004" in reason
    negative = dict(ft, mae_persist=0.150)
    adopt, reason = g1_decision(negative, PRE)
    assert adopt is True
    assert "skill -0.04" in reason


def test_boundaries_mae_equal_and_speed_ratio_floor() -> None:
    """mae_tol 0에서 MAE 0.200 = 0.200은 채택, 속력비 0.5는 채택·0.49는 불채택.

    노이즈 0.0005는 0.5²로 나눠 0.0020, 0.49²로 나눠 0.00208이라
    둘 다 노이즈 조건은 통과한다.
    """
    equal_mae = {
        "noise_floor_median": 0.0020,
        "mae_advect": 0.200,
        "moving_speed_ratio": 1.0,
    }
    at_floor = {
        "noise_floor_median": 0.0005,
        "mae_advect": 0.200,
        "moving_speed_ratio": 0.5,
    }
    below = dict(at_floor, moving_speed_ratio=0.49)
    assert g1_decision(equal_mae, PRE, mae_tol=0.0)[0] is True
    assert g1_decision(at_floor, PRE)[0] is True
    adopt, reason = g1_decision(below, PRE)
    assert adopt is False
    assert "fail: speed" in reason and "fail: noise" not in reason


def test_fallback_ignores_invalid_and_out_of_range_candidates() -> None:
    """NaN 지표 후보와 속력비 0.1(하한 0.5 미만) 후보는 빼고 고른다.

    둘 다 숫자만 보면 최저지만 빠지고, 남은 raft·dis 중 dis가 둘 다 최저다.
    """
    pool = {
        "raft": _m(0.0040, 0.200),
        "dis": _m(0.0035, 0.190),
        "broken": _m(float("nan"), 0.100),
        "frozen": _m(0.0, 0.150, ratio=0.1),
    }
    assert choose_fallback(pool) == "dis"


def test_fallback_uses_speed_normalised_noise() -> None:
    """0.6배로 줄어든 farneback(노이즈 0.0015)은 정규화 0.00417로 raft보다 높다.

    MAE가 0.200으로 같으므로 raft 하나가 둘 다 최저다.
    """
    pool = {
        "raft": _m(0.0040, 0.200),
        "farneback": _m(0.0015, 0.200, ratio=0.6),
    }
    assert choose_fallback(pool) == "raft"


def test_fallback_ties_and_empty() -> None:
    """두 지표 모두 같으면 None, 노이즈만 같으면 MAE가 낮은 쪽, 빈 후보는 None."""
    both_tie = {"raft": _m(0.0040, 0.200), "dis": _m(0.0040, 0.200)}
    noise_tie = {"raft": _m(0.0040, 0.200), "dis": _m(0.0040, 0.190)}
    all_bad = {"broken": _m(float("nan"), 0.100)}
    assert choose_fallback(both_tie) is None
    assert choose_fallback(noise_tie) == "dis"
    assert choose_fallback({}) is None
    assert choose_fallback(all_bad) is None
