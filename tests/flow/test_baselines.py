"""S7 테스트 경계: baselines.persistence_forecast·advect_density·mae 시험.

밀도·속도 격자를 손으로 정해 넣고, 동작(질량 이동, 벽에서 질량 보존,
음수 밀도 없음)만 확인한다. CFL 분할 같은 내부 구현은 시험하지 않는다.
기대값은 코드와 같은 식으로 다시 계산하지 않고 숫자로 적는다.
"""
from __future__ import annotations

import warnings

import numpy as np
import pytest

from src.flow.baselines import advect_density, mae, persistence_forecast


def test_persistence_returns_current_density() -> None:
    """현재값 유지: T초 뒤 예측은 지금 밀도 [[0.5, 1.0], [2.0, 0.0]]이다."""
    rho_now = np.array([[0.5, 1.0], [2.0, 0.0]])
    pred = persistence_forecast(rho_now)
    np.testing.assert_array_equal(pred, [[0.5, 1.0], [2.0, 0.0]])


def _centre(rho: np.ndarray, axis: int) -> float:
    """밀도 가중 셀 번호 평균(질량 중심)을 낸다."""
    idx = np.arange(rho.shape[axis], dtype=float)
    profile = rho.sum(axis=1 - axis)
    return float((idx * profile).sum() / profile.sum())


def test_uniform_x_velocity_moves_mass_by_two_cells() -> None:
    """u = 1 m/s, 셀 2 m, 4초: 1 × 4 / 2 = 2칸. 열 1의 질량 중심이 열 3이 된다.

    격자 안에서만 움직이므로 전체 질량 4.0은 그대로다.
    """
    rho = np.zeros((1, 10))
    rho[0, 1] = 4.0
    vel = np.zeros((1, 10, 2))
    vel[..., 0] = 1.0
    walkable = np.ones((1, 10), dtype=bool)
    out = advect_density(rho, vel, walkable, cell_m=2.0, horizon_s=4.0)
    assert _centre(out, axis=1) == pytest.approx(3.0)
    assert out.sum() == pytest.approx(4.0)


def test_negative_y_velocity_moves_mass_up_two_rows() -> None:
    """v = -1 m/s(행 번호가 줄어드는 쪽), 셀 1 m, 2초: 행 7 -> 행 5."""
    rho = np.zeros((10, 1))
    rho[7, 0] = 1.0
    vel = np.zeros((10, 1, 2))
    vel[..., 1] = -1.0
    walkable = np.ones((10, 1), dtype=bool)
    out = advect_density(rho, vel, walkable, cell_m=1.0, horizon_s=2.0)
    assert _centre(out, axis=0) == pytest.approx(5.0)
    assert out.sum() == pytest.approx(1.0)


def test_walls_conserve_mass_when_pushed_against() -> None:
    """양 끝 열이 보행 불가(벽)이면 10초 동안 오른쪽으로 밀어도 질량 3.0이 남는다.

    벽 셀의 밀도는 0이다.
    """
    rho = np.array([[0.0, 0.0, 3.0, 0.0, 0.0, 0.0]])
    vel = np.zeros((1, 6, 2))
    vel[..., 0] = 1.0
    walkable = np.array([[False, True, True, True, True, False]])
    out = advect_density(rho, vel, walkable, cell_m=1.0, horizon_s=10.0)
    assert out.sum() == pytest.approx(3.0)
    assert out[0, 0] == 0.0
    assert out[0, 5] == 0.0


def test_no_negative_density_with_large_varied_velocity() -> None:
    """셀 크기(1 m)의 수십 배인 ±30 m/s 속도장에서도 음수 밀도가 없다."""
    rng = np.random.default_rng(0)
    rho = rng.uniform(0.0, 3.0, size=(6, 7))
    vel = rng.uniform(-30.0, 30.0, size=(6, 7, 2))
    walkable = np.ones((6, 7), dtype=bool)
    walkable[2, 3] = False
    out = advect_density(rho, vel, walkable, cell_m=1.0, horizon_s=5.0)
    assert out.min() >= 0.0


def test_nan_velocity_is_zero_and_nan_density_stays_nan() -> None:
    """속도 NaN은 정지로 본다. 보행 불가 셀 밀도는 0이 된다.

    밀도 NaN은 계산에선 0명이지만 출력 칸은 NaN으로 남긴다. 그래야
    현재값 유지와 같은 칸에서 오차를 잰다.
    [[NaN, 2.0, 5.0]], 속도 전부 NaN, 열 2 보행 불가 -> [[NaN, 2, 0]].
    """
    rho = np.array([[np.nan, 2.0, 5.0]])
    vel = np.full((1, 3, 2), np.nan)
    walkable = np.array([[True, True, False]])
    out = advect_density(rho, vel, walkable, cell_m=1.0, horizon_s=3.0)
    np.testing.assert_array_equal(out, [[np.nan, 2.0, 0.0]])


def test_mae_ignores_nan_pairs_and_masked_cells() -> None:
    """NaN이 낀 칸(3번)과 마스크 밖 칸(4번)을 빼면 (1 + 0 + 2) / 3 = 1.0이다."""
    pred = np.array([1.0, 2.0, 3.0, np.nan, 10.0])
    true = np.array([2.0, 2.0, 5.0, 1.0, 0.0])
    mask = np.array([True, True, True, True, False])
    assert mae(pred, true, mask) == pytest.approx(1.0)


def test_mae_without_valid_cells_is_nan() -> None:
    """유효한 칸이 없으면(빈 배열, 전부 NaN·마스크 밖) 경고 없이 NaN이다."""
    empty = np.array([])
    pred = np.array([np.nan, 1.0])
    true = np.array([1.0, 1.0])
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        assert np.isnan(mae(empty, empty, np.array([], dtype=bool)))
        assert np.isnan(mae(pred, true, np.array([True, False])))


def test_steady_x_through_flow_keeps_density() -> None:
    """양 끝이 열린 복도에서 rho = 1, u = 1 m/s가 60초 뒤에도 전부 1이다.

    들어오는 양(왼쪽 끝 1 × 1)과 나가는 양(오른쪽 끝 1 × 1)이 같다.
    """
    rho = np.ones((1, 5))
    vel = np.zeros((1, 5, 2))
    vel[..., 0] = 1.0
    walkable = np.ones((1, 5), dtype=bool)
    out = advect_density(rho, vel, walkable, cell_m=1.0, horizon_s=60.0)
    np.testing.assert_allclose(out, [[1.0, 1.0, 1.0, 1.0, 1.0]])


def test_steady_y_through_flow_keeps_density() -> None:
    """위아래가 열린 복도에서 rho = 1, v = -1 m/s가 60초 뒤에도 전부 1이다."""
    rho = np.ones((5, 1))
    vel = np.zeros((5, 1, 2))
    vel[..., 1] = -1.0
    walkable = np.ones((5, 1), dtype=bool)
    out = advect_density(rho, vel, walkable, cell_m=1.0, horizon_s=60.0)
    np.testing.assert_allclose(out, [[1.0], [1.0], [1.0], [1.0], [1.0]])


def test_mass_leaves_through_edge_and_empty_inlet_adds_nothing() -> None:
    """[[0, 0, 2]], u = 1 m/s, 셀 1 m, 60초: 3 m 복도를 60 m 지나므로
    질량 2가 오른쪽 끝으로 모두 나간다. 왼쪽 끝 밀도가 0이라 들어오는 양도
    0이다. 그래서 전부 0이 된다.
    """
    rho = np.array([[0.0, 0.0, 2.0]])
    vel = np.zeros((1, 3, 2))
    vel[..., 0] = 1.0
    walkable = np.ones((1, 3), dtype=bool)
    out = advect_density(rho, vel, walkable, cell_m=1.0, horizon_s=60.0)
    np.testing.assert_allclose(out, [[0.0, 0.0, 0.0]], atol=1e-9)


def test_y_walls_conserve_mass_when_pushed_against() -> None:
    """위·아래 끝 행이 벽이면 10초 동안 아래로 밀어도 질량 3.0이 남는다.

    벽 셀의 밀도는 0이다.
    """
    rho = np.array([[0.0], [0.0], [3.0], [0.0], [0.0], [0.0]])
    vel = np.zeros((6, 1, 2))
    vel[..., 1] = 1.0
    walkable = np.array([[False], [True], [True], [True], [True], [False]])
    out = advect_density(rho, vel, walkable, cell_m=1.0, horizon_s=10.0)
    assert out.sum() == pytest.approx(3.0)
    assert out[0, 0] == 0.0
    assert out[5, 0] == 0.0


def test_no_negative_density_at_saddle() -> None:
    """가운데 셀은 정지, 상하좌우 이웃은 바깥쪽으로 20 m/s: 가운데 셀이
    네 면으로 동시에 비어도 밀도는 0 아래로 내려가지 않는다.
    """
    rho = np.ones((3, 3))
    vel = np.zeros((3, 3, 2))
    vel[1, 0, 0] = -20.0
    vel[1, 2, 0] = 20.0
    vel[0, 1, 1] = -20.0
    vel[2, 1, 1] = 20.0
    walkable = np.ones((3, 3), dtype=bool)
    out = advect_density(rho, vel, walkable, cell_m=1.0, horizon_s=1.0)
    assert out.min() >= 0.0


def test_mae_ignores_nan_in_truth() -> None:
    """정답 NaN 칸(0번)을 빼면 |2 - 4| = 2.0이다."""
    pred = np.array([1.0, 2.0])
    true = np.array([np.nan, 4.0])
    mask = np.array([True, True])
    assert mae(pred, true, mask) == pytest.approx(2.0)


def test_mae_accepts_int_mask_as_boolean() -> None:
    """정수 마스크 [1, 0]은 참·거짓으로 읽는다: 0번 칸만 써서 |1 - 2| = 1.0."""
    pred = np.array([1.0, 5.0])
    true = np.array([2.0, 0.0])
    assert mae(pred, true, np.array([1, 0])) == pytest.approx(1.0)


def test_mae_rejects_shape_mismatch() -> None:
    """마스크가 (1,)이고 예측이 (2,)이면 퍼뜨리지(broadcast) 않고 거부한다."""
    pred = np.array([1.0, 5.0])
    true = np.array([2.0, 0.0])
    with pytest.raises(ValueError):
        mae(pred, true, np.array([True]))


def test_horizon_must_be_positive_whole_number_of_steps() -> None:
    """horizon_s / dt_s가 2.5이거나 0이면 ValueError다. 3.0은 받는다."""
    rho = np.ones((1, 2))
    vel = np.zeros((1, 2, 2))
    walkable = np.ones((1, 2), dtype=bool)
    with pytest.raises(ValueError):
        advect_density(rho, vel, walkable, cell_m=1.0, horizon_s=2.5)
    with pytest.raises(ValueError):
        advect_density(rho, vel, walkable, cell_m=1.0, horizon_s=0.0)
    out = advect_density(
        rho, vel, walkable, cell_m=1.0, horizon_s=1.5, dt_s=0.5,
    )
    np.testing.assert_array_equal(out, [[1.0, 1.0]])


def test_infinite_velocity_is_treated_as_zero() -> None:
    """속도 +inf·-inf는 정지로 본다: [[1, 2]]가 3초 뒤에도 [[1, 2]]이다."""
    rho = np.array([[1.0, 2.0]])
    vel = np.zeros((1, 2, 2))
    vel[0, 0, 0] = np.inf
    vel[0, 1, 1] = -np.inf
    walkable = np.ones((1, 2), dtype=bool)
    out = advect_density(rho, vel, walkable, cell_m=1.0, horizon_s=3.0)
    np.testing.assert_array_equal(out, [[1.0, 2.0]])


def test_advect_rejects_bad_shapes_and_cell_size() -> None:
    """walkable 모양 ≠ rho 모양, vel 모양 ≠ rho 모양 + (2,), cell_m ≤ 0은
    모두 ValueError다.
    """
    rho = np.ones((1, 3))
    vel = np.zeros((1, 3, 2))
    walkable = np.ones((1, 3), dtype=bool)
    with pytest.raises(ValueError):
        advect_density(
            rho, vel, np.ones((2, 3), dtype=bool), cell_m=1.0, horizon_s=1.0,
        )
    with pytest.raises(ValueError):
        advect_density(
            rho, np.zeros((1, 3, 3)), walkable, cell_m=1.0, horizon_s=1.0,
        )
    with pytest.raises(ValueError):
        advect_density(rho, vel, walkable, cell_m=0.0, horizon_s=1.0)
