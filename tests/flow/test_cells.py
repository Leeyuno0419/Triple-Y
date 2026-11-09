"""S4 seam: cells.reduce_to_cells 시험.

픽셀마다 셀 번호와 지면 속도를 손으로 정해 넣고,
셀 평균 V_c, 유효 픽셀 수 Q_c, 역방향 비율 B_c를 손으로 계산한 값과 비교한다.
기대값은 코드와 같은 식으로 다시 계산하지 않고 숫자로 적는다.
"""
from __future__ import annotations

import warnings

import numpy as np
import pytest

from src.flow.cells import TemporalInstability, reduce_to_cells


def test_cell_mean_is_average_of_pixel_velocities_in_that_cell() -> None:
    """셀 0은 (1,0)과 (3,2)의 평균 (2,1), 셀 1은 (0,-1) 하나라 (0,-1)이다."""
    cell_ids = np.array([0, 0, 1])
    vel = np.array([[1.0, 0.0], [3.0, 2.0], [0.0, -1.0]])

    out = reduce_to_cells(cell_ids, vel, n_cells=2)

    np.testing.assert_allclose(out.mean_v, [[2.0, 1.0], [0.0, -1.0]])


def test_pixels_marked_minus_one_are_ignored() -> None:
    """번호 -1(보행 불가·격자 밖) 픽셀의 큰 속도는 셀 0 평균에 섞이지 않는다."""
    cell_ids = np.array([0, -1, 0, -1])
    vel = np.array([[1.0, 1.0], [100.0, -100.0], [3.0, 1.0], [50.0, 50.0]])

    out = reduce_to_cells(cell_ids, vel, n_cells=1)

    np.testing.assert_allclose(out.mean_v, [[2.0, 1.0]])


def test_empty_cell_has_nan_mean_and_zero_count() -> None:
    """픽셀이 없는 셀 1은 평균이 NaN, Q_c가 0이다. 경고 없이 끝난다."""
    cell_ids = np.array([0, 0, 2])
    vel = np.array([[1.0, 0.0], [1.0, 0.0], [0.0, 2.0]])

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        out = reduce_to_cells(cell_ids, vel, n_cells=3)

    assert np.isnan(out.mean_v[1]).all()
    np.testing.assert_array_equal(out.count, [2, 0, 1])


def test_counterflow_is_fraction_with_negative_dot_to_cell_mean() -> None:
    """역방향 규칙: 픽셀 속도와 셀 평균 V_c의 내적이 음수면 역방향이다.

    셀 0: (2,0)×3, (-1,0)×1 → 평균 (1.25,0), 역방향 1/4 = 0.25.
    셀 1: (0,1), (0,2) → 모두 같은 방향, 역방향 0.
    """
    cell_ids = np.array([0, 0, 0, 0, 1, 1])
    vel = np.array([
        [2.0, 0.0], [2.0, 0.0], [2.0, 0.0], [-1.0, 0.0],
        [0.0, 1.0], [0.0, 2.0],
    ])

    out = reduce_to_cells(cell_ids, vel, n_cells=2)

    np.testing.assert_allclose(out.counterflow, [0.25, 0.0])


def test_slow_pixel_below_min_speed_is_not_counterflow() -> None:
    """속력 0.01 m/s 픽셀은 반대 방향이어도 잡음으로 보고 역방향에 넣지 않는다.

    min_speed = 0.05 m/s. 셀 0: (1,0)×3, (-0.01,0) → 역방향 0.
    셀 1: (1,0)×3, (-0.5,0) → 0.5 m/s는 min_speed 이상이라 역방향 1/4.
    """
    cell_ids = np.array([0, 0, 0, 0, 1, 1, 1, 1])
    vel = np.array([
        [1.0, 0.0], [1.0, 0.0], [1.0, 0.0], [-0.01, 0.0],
        [1.0, 0.0], [1.0, 0.0], [1.0, 0.0], [-0.5, 0.0],
    ])

    out = reduce_to_cells(cell_ids, vel, n_cells=2, min_speed=0.05)

    np.testing.assert_allclose(out.counterflow, [0.0, 0.25])


def test_accepts_image_shaped_cell_ids_and_velocity_field() -> None:
    """셀 번호표 (H, W)와 속도장 (H, W, 2)를 그대로 넣어도 된다.

    2×2 영상: 왼쪽 열은 셀 0, 오른쪽 위는 셀 1, 오른쪽 아래는 -1.
    """
    cell_ids = np.array([[0, 1], [0, -1]])
    vel = np.array([
        [[1.0, 0.0], [0.0, 3.0]],
        [[3.0, 2.0], [9.0, 9.0]],
    ])

    out = reduce_to_cells(cell_ids, vel, n_cells=2)

    np.testing.assert_allclose(out.mean_v, [[2.0, 1.0], [0.0, 3.0]])
    np.testing.assert_array_equal(out.count, [2, 1])


def test_empty_cell_has_nan_counterflow() -> None:
    """픽셀이 없는 셀 1의 B_c는 0이 아니라 NaN이다 (값 없음과 역방향 0을 구분)."""
    cell_ids = np.array([0, 0])
    vel = np.array([[1.0, 0.0], [1.0, 0.0]])

    out = reduce_to_cells(cell_ids, vel, n_cells=2)

    assert out.counterflow[0] == 0.0
    assert np.isnan(out.counterflow[1])


def test_cell_without_dominant_flow_has_nan_counterflow() -> None:
    """(가정) 셀 평균 속력이 min_speed보다 작으면 주 흐름이 없다고 보고 B_c = NaN이다.

    셀 0: (0.1,0), (0.2,0), (-0.3,0) → 평균 약 (0,0) (부동소수점으로 정확히 0은 아님).
    셀 1: (1,0) 하나 → 주 흐름이 있어 B_c = 0.
    """
    cell_ids = np.array([0, 0, 0, 1])
    vel = np.array([[0.1, 0.0], [0.2, 0.0], [-0.3, 0.0], [1.0, 0.0]])

    out = reduce_to_cells(cell_ids, vel, n_cells=2, min_speed=0.05)

    assert np.isnan(out.counterflow[0])
    assert out.counterflow[1] == 0.0


def test_cell_id_at_or_above_n_cells_raises() -> None:
    """n_cells=2인데 번호 5가 있으면 결과가 6칸으로 늘지 않고 ValueError가 난다."""
    cell_ids = np.array([0, 5])
    vel = np.array([[1.0, 0.0], [1.0, 0.0]])

    with pytest.raises(ValueError):
        reduce_to_cells(cell_ids, vel, n_cells=2)


def test_non_finite_velocity_pixels_are_excluded() -> None:
    """속도가 NaN·inf인 픽셀은 평균·Q_c·B_c 어디에도 들어가지 않는다.

    셀 0: (1,0), (3,0), (NaN,NaN), (-inf,0) → 평균 (2,0), Q_c 2, B_c 0.
    """
    cell_ids = np.array([0, 0, 0, 0])
    vel = np.array([[1.0, 0.0], [3.0, 0.0], [np.nan, np.nan], [-np.inf, 0.0]])

    out = reduce_to_cells(cell_ids, vel, n_cells=1)

    np.testing.assert_allclose(out.mean_v, [[2.0, 0.0]])
    np.testing.assert_array_equal(out.count, [2])
    np.testing.assert_allclose(out.counterflow, [0.0])


def test_counterflow_denominator_is_all_valid_pixels_not_only_moving() -> None:
    """B_c의 분모는 움직이는 픽셀 수가 아니라 Q_c다.

    셀 0: (2,0), (0.01,0), (0.01,0), (-1,0), min_speed 0.05 → 평균 (0.255,0).
    역방향은 (-1,0) 하나 → 1/4 = 0.25 (움직이는 픽셀만 세면 1/2 = 0.5).
    """
    cell_ids = np.array([0, 0, 0, 0])
    vel = np.array([[2.0, 0.0], [0.01, 0.0], [0.01, 0.0], [-1.0, 0.0]])

    out = reduce_to_cells(cell_ids, vel, n_cells=1, min_speed=0.05)

    np.testing.assert_allclose(out.counterflow, [0.25])


def test_pixel_exactly_at_min_speed_counts_as_counterflow() -> None:
    """경계 규칙: 속력이 min_speed와 같으면(이상) 역방향에 넣는다.

    셀 0: (1,0)×3, (-0.05,0), min_speed 0.05 → 1/4 = 0.25.
    """
    cell_ids = np.array([0, 0, 0, 0])
    vel = np.array([[1.0, 0.0], [1.0, 0.0], [1.0, 0.0], [-0.05, 0.0]])

    out = reduce_to_cells(cell_ids, vel, n_cells=1, min_speed=0.05)

    np.testing.assert_allclose(out.counterflow, [0.25])


def test_accepts_lists_and_float_typed_integer_cell_ids() -> None:
    """리스트 입력과 실수형 정수 셀 번호 [0.0, 0.0, 1.0, -1.0]도 받는다."""
    cell_ids = [0.0, 0.0, 1.0, -1.0]
    vel = [[1.0, 0.0], [3.0, 2.0], [0.0, -1.0], [9.0, 9.0]]

    out = reduce_to_cells(cell_ids, vel, n_cells=2)

    np.testing.assert_allclose(out.mean_v, [[2.0, 1.0], [0.0, -1.0]])
    np.testing.assert_array_equal(out.count, [2, 1])


# --- S5 seam: cells.TemporalInstability.update ---


def test_alternating_series_gives_variance_a_squared_when_full() -> None:
    """(+2,0),(−2,0)를 번갈아 4초 넣으면 창이 찬 뒤 S_c = 2² = 4."""
    ti = TemporalInstability(n_cells=1, window_s=4.0, rate_hz=1.0)
    for vx in [2.0, -2.0, 2.0]:
        ti.update(np.array([[vx, 0.0]]))

    s, raw = ti.update(np.array([[-2.0, 0.0]]))

    np.testing.assert_allclose(s, [4.0])
    np.testing.assert_allclose(raw, [4.0])


def test_nan_sample_is_skipped_when_enough_valid_samples_remain() -> None:
    """창 5개 중 NaN 1개: 남은 4개 (1,0),(−1,0),(1,0),(−1,0)로 S_c = 1."""
    ti = TemporalInstability(n_cells=1, window_s=5.0, rate_hz=1.0)
    for v in [[1.0, 0.0], [np.nan, np.nan], [-1.0, 0.0], [1.0, 0.0]]:
        ti.update(np.array([v]))

    s, raw = ti.update(np.array([[-1.0, 0.0]]))

    np.testing.assert_allclose(s, [1.0])
    np.testing.assert_allclose(raw, [1.0])


def test_output_is_nan_until_window_is_full() -> None:
    """창 4개 중 3개만 넣으면 S_c와 분산이 모두 NaN이다."""
    ti = TemporalInstability(n_cells=1, window_s=4.0, rate_hz=1.0)
    outs = [ti.update(np.array([[vx, 0.0]])) for vx in [2.0, -2.0, 2.0]]

    for s, raw in outs:
        assert np.isnan(s).all()
        assert np.isnan(raw).all()


def test_cell_with_too_few_valid_samples_is_nan() -> None:
    """창 5개 중 NaN 2개: 유효 3개 < ceil(0.8 × 5) = 4 이므로 NaN."""
    ti = TemporalInstability(n_cells=1, window_s=5.0, rate_hz=1.0)
    nan = [np.nan, np.nan]
    for v in [[1.0, 0.0], nan, [-1.0, 0.0], nan]:
        ti.update(np.array([v]))

    s, raw = ti.update(np.array([[1.0, 0.0]]))

    assert np.isnan(s).all()
    assert np.isnan(raw).all()


def test_vector_with_one_nan_component_is_missing_as_a_whole() -> None:
    """(5, NaN)은 x=5도 버린다. 남은 (±1, 0) 4개로 S_c = 1."""
    ti = TemporalInstability(n_cells=1, window_s=5.0, rate_hz=1.0)
    for v in [[1.0, 0.0], [5.0, np.nan], [-1.0, 0.0], [1.0, 0.0]]:
        ti.update(np.array([v]))

    s, raw = ti.update(np.array([[-1.0, 0.0]]))

    np.testing.assert_allclose(s, [1.0])
    np.testing.assert_allclose(raw, [1.0])


def test_noise_floor_is_subtracted_and_negative_clipped_to_zero() -> None:
    """셀0: 분산 4 − 잡음 1.5 = 2.5. 셀1: 분산 1 − 잡음 3 → 0으로 자름."""
    ti = TemporalInstability(
        n_cells=2, window_s=2.0, rate_hz=1.0,
        noise_var=np.array([1.5, 3.0]),
    )
    ti.update(np.array([[2.0, 0.0], [0.0, 1.0]]))

    s, raw = ti.update(np.array([[-2.0, 0.0], [0.0, -1.0]]))

    np.testing.assert_allclose(s, [2.5, 0.0])
    np.testing.assert_allclose(raw, [4.0, 1.0])


def test_nan_noise_floor_uses_median_of_finite_cells() -> None:
    """잡음 [0.5, NaN, 2.5, 1.5]: 셀1은 중앙값 1.5를 쓴다. 분산 4 → 2.5."""
    ti = TemporalInstability(
        n_cells=4, window_s=2.0, rate_hz=1.0,
        noise_var=np.array([0.5, np.nan, 2.5, 1.5]),
    )
    still = [0.0, 0.0]
    ti.update(np.array([still, [2.0, 0.0], still, still]))

    s, _ = ti.update(np.array([still, [-2.0, 0.0], still, still]))

    np.testing.assert_allclose(s, [0.0, 2.5, 0.0, 0.0])
    assert ti.noise_floor_available is True


def test_all_nan_noise_floor_falls_back_to_zero_and_sets_flag() -> None:
    """잡음이 모두 NaN이면 0을 빼고 noise_floor_available이 False다."""
    ti = TemporalInstability(
        n_cells=2, window_s=2.0, rate_hz=1.0,
        noise_var=np.array([np.nan, np.nan]),
    )
    ti.update(np.array([[2.0, 0.0], [0.0, 1.0]]))

    s, _ = ti.update(np.array([[-2.0, 0.0], [0.0, -1.0]]))

    np.testing.assert_allclose(s, [4.0, 1.0])
    assert ti.noise_floor_available is False


def test_variance_divides_by_n_and_sums_both_components() -> None:
    """(0,0),(3,0),(0,3): 평균 (1,1), 편차² 합 2+5+5 = 12, 12/3 = 4.

    n−1로 나누면 6이 된다. S6 잡음 분산과 같은 규약(n, 두 성분 합)이다.
    """
    ti = TemporalInstability(n_cells=1, window_s=3.0, rate_hz=1.0)
    ti.update(np.array([[0.0, 0.0]]))
    ti.update(np.array([[3.0, 0.0]]))

    _, raw = ti.update(np.array([[0.0, 3.0]]))

    np.testing.assert_allclose(raw, [4.0])


def test_oldest_sample_leaves_the_window() -> None:
    """창 2개에 (10,0),(0,0),(2,0): 남은 (0,0),(2,0)의 분산 1."""
    ti = TemporalInstability(n_cells=1, window_s=2.0, rate_hz=1.0)
    ti.update(np.array([[10.0, 0.0]]))
    ti.update(np.array([[0.0, 0.0]]))

    _, raw = ti.update(np.array([[2.0, 0.0]]))

    np.testing.assert_allclose(raw, [1.0])


def test_window_length_is_seconds_times_rate() -> None:
    """window_s=2, rate_hz=2: 창 4개. 3번째까지 NaN, 4번째에 분산 1."""
    ti = TemporalInstability(n_cells=1, window_s=2.0, rate_hz=2.0)
    for vx in [1.0, -1.0, 1.0]:
        _, raw = ti.update(np.array([[vx, 0.0]]))
        assert np.isnan(raw).all()

    _, raw = ti.update(np.array([[-1.0, 0.0]]))

    np.testing.assert_allclose(raw, [1.0])


def test_cells_are_independent() -> None:
    """셀0 (±1,0) → 1. 셀1은 NaN이 많아 NaN이어도 셀0에 영향 없다."""
    ti = TemporalInstability(n_cells=2, window_s=4.0, rate_hz=1.0)
    nan = [np.nan, np.nan]
    ti.update(np.array([[1.0, 0.0], [5.0, 5.0]]))
    ti.update(np.array([[-1.0, 0.0], nan]))
    ti.update(np.array([[1.0, 0.0], nan]))

    s, raw = ti.update(np.array([[-1.0, 0.0], [0.0, 0.0]]))

    np.testing.assert_allclose(s[0], 1.0)
    np.testing.assert_allclose(raw[0], 1.0)
    assert np.isnan(s[1]) and np.isnan(raw[1])


def test_cell_empty_for_whole_window_is_nan_without_warning() -> None:
    """창 내내 빈 셀(NaN)은 NaN이고 RuntimeWarning을 내지 않는다."""
    ti = TemporalInstability(n_cells=1, window_s=2.0, rate_hz=1.0)
    ti.update(np.array([[np.nan, np.nan]]))

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        s, raw = ti.update(np.array([[np.nan, np.nan]]))

    assert np.isnan(s).all() and np.isnan(raw).all()


def test_mean_v_with_wrong_shape_raises() -> None:
    """n_cells=2인데 (1, 2)를 넣으면 ValueError (창이 차기 전에도)."""
    ti = TemporalInstability(n_cells=2, window_s=2.0, rate_hz=1.0)

    with pytest.raises(ValueError):
        ti.update(np.array([[1.0, 0.0]]))


def test_noise_var_with_wrong_shape_raises() -> None:
    """n_cells=2인데 잡음 분산이 3개면 ValueError."""
    with pytest.raises(ValueError):
        TemporalInstability(
            n_cells=2, window_s=2.0, rate_hz=1.0,
            noise_var=np.array([1.0, 1.0, 1.0]),
        )


def test_window_shorter_than_two_samples_raises() -> None:
    """window_s=1, rate_hz=1이면 창 1개라 분산을 낼 수 없어 ValueError."""
    with pytest.raises(ValueError):
        TemporalInstability(n_cells=1, window_s=1.0, rate_hz=1.0)


def test_valid_threshold_rounds_up_not_down() -> None:
    """창 4개 중 NaN 1개: 유효 3개 < ceil(0.8 × 4) = ceil(3.2) = 4라 NaN.

    floor면 3이 되어 값이 나오므로 ceil인지 가른다.
    """
    ti = TemporalInstability(n_cells=1, window_s=4.0, rate_hz=1.0)
    for v in [[1.0, 0.0], [np.nan, np.nan], [-1.0, 0.0]]:
        ti.update(np.array([v]))

    s, raw = ti.update(np.array([[1.0, 0.0]]))

    assert np.isnan(s).all() and np.isnan(raw).all()


def test_no_noise_var_subtracts_nothing_and_flag_is_false() -> None:
    """noise_var=None: (±2,0) 분산 4가 그대로 S_c = 4, 플래그 False."""
    ti = TemporalInstability(n_cells=1, window_s=2.0, rate_hz=1.0)
    ti.update(np.array([[2.0, 0.0]]))

    s, raw = ti.update(np.array([[-2.0, 0.0]]))

    np.testing.assert_allclose(s, [4.0])
    np.testing.assert_allclose(raw, [4.0])
    assert ti.noise_floor_available is False
