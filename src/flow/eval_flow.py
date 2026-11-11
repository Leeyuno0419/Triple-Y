"""추정기별 중간 1·2 지표를 모아 G1 판정을 낸다 (기획 5.2)."""
from __future__ import annotations

import math

_PRE_KEYS = ("noise_floor_median", "mae_advect")
_FT_KEYS = _PRE_KEYS + ("moving_speed_ratio",)


def g1_decision(
    ft: dict[str, float],
    pre: dict[str, float],
    mae_tol: float = 0.0,
    min_speed_ratio: float = 0.5,
    max_speed_ratio: float | None = 2.0,
) -> tuple[bool, str]:
    """추가 학습(ft)과 사전학습 RAFT(pre)의 지표로 채택 여부와 근거를 돌려준다.

    조건 1: 속력 정규화 노이즈(ft 노이즈 / 속력비²)가 pre 노이즈보다 낮다.
    흐름을 k배 줄이면 노이즈 바닥이 k²배 줄어 원래 비교로는 통과하므로
    척도를 맞춘다. (가정) [토론] 팀 결정 대기.
    조건 2: 흐름 외삽 MAE가 사전학습 대비 mae_tol 비율 이상 나빠지지 않는다.
    mae_tol이 음수면 그만큼 개선을 요구한다.
    조건 3: 움직이는 셀 평균 속력비(사전학습 RAFT 대비)가
    [min_speed_ratio, max_speed_ratio] 안이다. max_speed_ratio None은 상한
    없음. 0 흐름 붕괴(계획 8)와 과장된 흐름을 막는 하한·상한 확인이다.
    (가정) [토론] 팀 결정 대기.
    mae_persist가 있으면 근거에 skill(mae_persist − mae_advect)을 적지만
    판정에는 쓰지 않는다. (가정) [토론] 팀 결정 대기.
    근거 문자열은 "pass" 또는 "fail: noise"·"fail: mae"·"fail: speed"로
    시작하고, 지표가 빠지거나 유한하지 않으면 "missing or non-finite: "로
    시작한다. 수치 기준(mae_tol, min·max_speed_ratio)은 [토론]이다
    (기획 9장 11번).
    """
    bad = [
        f"{who}.{key}"
        for who, metrics, keys in (
            ("ft", ft, _FT_KEYS), ("pre", pre, _PRE_KEYS),
        )
        for key in keys
        if not math.isfinite(metrics.get(key, math.nan))
    ]
    if bad:
        return False, "missing or non-finite: " + ", ".join(bad)
    ratio = ft["moving_speed_ratio"]
    noise_n = _normalised_noise(ft)
    fails = []
    if not noise_n < pre["noise_floor_median"]:
        fails.append("noise")
    if not ft["mae_advect"] <= pre["mae_advect"] * (1.0 + mae_tol):
        fails.append("mae")
    if not _speed_ok(ratio, min_speed_ratio, max_speed_ratio):
        fails.append("speed")
    head = "; ".join(f"fail: {f}" for f in fails) if fails else "pass"
    reason = (
        f"{head}; "
        f"noise_n {noise_n:.3g} vs {pre['noise_floor_median']:.3g}, "
        f"mae_advect {ft['mae_advect']:.3g} vs {pre['mae_advect']:.3g}, "
        f"speed_ratio {ratio:.3g}"
        f" (min {min_speed_ratio:.3g}, max {max_speed_ratio})"
    )
    persist = ft.get("mae_persist", math.nan)
    if math.isfinite(persist):
        skill = persist - ft["mae_advect"]
        reason += f", mae_persist {persist:.3g}, skill {skill:.3g}"
    return not fails, reason


def _speed_ok(
    ratio: float, min_ratio: float, max_ratio: float | None,
) -> bool:
    """속력비가 [min_ratio, max_ratio] 안인지 본다. max_ratio None은 상한 없음."""
    if not ratio >= min_ratio:
        return False
    return max_ratio is None or ratio <= max_ratio


def _normalised_noise(m: dict[str, float]) -> float:
    """노이즈 바닥 중앙값을 속력비²로 나눠 속력 척도를 맞춘다.

    흐름을 k배 하면 노이즈 바닥(속도 분산)은 k²배가 된다. 속력비가 0 이하면
    비교할 수 없으므로 무한대를 돌려준다.
    """
    ratio = m["moving_speed_ratio"]
    if ratio <= 0.0:
        return math.inf
    return m["noise_floor_median"] / ratio**2


def choose_fallback(
    pretrained: dict[str, dict[str, float]],
    min_speed_ratio: float = 0.5,
    max_speed_ratio: float | None = 2.0,
) -> str | None:
    """불채택 시 고정할 사전학습 추정기 이름을 고른다 (계획 7.3).

    지표가 빠지거나 유한하지 않은 후보, 속력비가 [min_speed_ratio,
    max_speed_ratio] 밖인 후보는 뺀다. 남은 후보 중 속력 정규화 노이즈와
    mae_advect가 둘 다 가장 낮은 추정기 하나를 돌려준다. 남은 후보가 없거나,
    두 지표의 최저가 엇갈리거나, 둘 다 같은 후보가 여럿이면 팀이 정하므로
    None을 돌려준다. (가정) [토론] 팀 결정 대기.
    """
    valid = {
        name: m for name, m in pretrained.items()
        if all(math.isfinite(m.get(k, math.nan)) for k in _FT_KEYS)
        and _speed_ok(m["moving_speed_ratio"], min_speed_ratio,
                      max_speed_ratio)
    }
    if not valid:
        return None
    best = None
    for score in (_normalised_noise, lambda m: m["mae_advect"]):
        low = min(score(m) for m in valid.values())
        names = {n for n, m in valid.items() if score(m) == low}
        best = names if best is None else best & names
    return next(iter(best)) if len(best) == 1 else None
