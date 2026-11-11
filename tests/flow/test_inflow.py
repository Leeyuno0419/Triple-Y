"""T4 테스트 경계: inflow.boundary_inward, inflow.inflow_ratio 시험.

3×3 격자(셀 크기 2 m)를 손으로 만들고, 경계 셀과 안쪽 방향,
경계 유입 비율을 손으로 계산한 숫자와 비교한다.
"""
from __future__ import annotations

import numpy as np
import pytest

from src.flow.inflow import boundary_inward, inflow_ratio

R2 = 1 / np.sqrt(2)
R10 = 1 / np.sqrt(10)


def grid_cells(n: int = 3) -> list[dict]:
    """화면을 n×n으로 나눈 셀 n²개. 셀 번호 = row·n + col."""
    cells = []
    for row in range(n):
        for col in range(n):
            x0, x1 = col / n, (col + 1) / n
            y0, y1 = row / n, (row + 1) / n
            cells.append({
                "row": row,
                "col": col,
                "image_polygon": [[x0, y0], [x1, y0], [x1, y1], [x0, y1]],
            })
    return cells


def test_outer_cells_are_boundary_and_point_to_zone_centre() -> None:
    """바깥 8칸은 경계, 가운데는 아니다. 모서리는 대각선, 변은 축 방향."""
    is_b, inward = boundary_inward(grid_cells(), cell_size_m=2.0)
    assert is_b.tolist() == [
        True, True, True, True, False, True, True, True, True,
    ]
    expected = np.array([
        [R2, R2], [0.0, 1.0], [-R2, R2],
        [1.0, 0.0], [0.0, 0.0], [-1.0, 0.0],
        [R2, -R2], [0.0, -1.0], [-R2, -R2],
    ])
    np.testing.assert_allclose(inward, expected, atol=1e-12)


def test_interior_cells_off_centroid_get_zero_inward() -> None:
    """4×4 격자(2 m): 구역 중심 (4, 4). 안쪽 4칸은 중심에서 벗어나도 (0, 0).

    셀 (0, 1) 중심 (3, 1) → (1, 3)/√10, 셀 (1, 0) 중심 (1, 3) → (3, 1)/√10.
    """
    is_b, inward = boundary_inward(grid_cells(4), cell_size_m=2.0)
    assert is_b.tolist() == [
        True, True, True, True,
        True, False, False, True,
        True, False, False, True,
        True, True, True, True,
    ]
    expected_top = np.array([
        [R2, R2], [R10, 3 * R10], [-R10, 3 * R10], [-R2, R2],
        [3 * R10, R10], [0.0, 0.0], [0.0, 0.0], [-3 * R10, R10],
    ])
    np.testing.assert_allclose(inward[:8], expected_top, atol=1e-12)
    np.testing.assert_allclose(inward[9:11], np.zeros((2, 2)), atol=0)


def strip_cell(col: int, x0: float, x1: float) -> dict:
    """row 0의 세로 띠 셀. 위아래는 화면 가장자리에서 떨어져 있다."""
    return {
        "row": 0,
        "col": col,
        "image_polygon": [[x0, 0.3], [x1, 0.3], [x1, 0.6], [x0, 0.6]],
    }


def test_edge_tolerance_is_inclusive_at_two_percent() -> None:
    """x 0.015는 경계, 0.03~0.97은 경계 아님.

    정확히 0.02와 1 − 0.02 = 0.98도 경계다 (<=, >=).
    """
    cells = [
        strip_cell(0, 0.015, 0.3),
        strip_cell(1, 0.03, 0.97),
        strip_cell(2, 0.7, 0.98),
        strip_cell(3, 0.02, 0.3),
    ]
    is_b, _ = boundary_inward(cells, cell_size_m=2.0)
    assert is_b.tolist() == [True, False, True, True]


def test_one_cell_zone_has_no_boundary_and_gives_none() -> None:
    """셀 1개 구역은 셀 중심 = 구역 중심이라 안쪽 방향이 없어 경계가 아니다.

    그래서 그 셀이 화면 가장자리에 닿아도 유입 비율은 None이다.
    """
    cells = [strip_cell(0, 0.0, 0.5)]
    is_b, inward = boundary_inward(cells, cell_size_m=2.0)
    assert is_b.tolist() == [False]
    vel = np.array([[0.5, 0.0], [0.0, 0.5]])
    assert inflow_ratio(np.array([0, 0]), vel, is_b, inward) is None


def test_empty_cell_list_raises_value_error() -> None:
    """셀이 없으면 ValueError다."""
    with pytest.raises(ValueError):
        boundary_inward([], cell_size_m=2.0)


def border_setup() -> tuple[np.ndarray, np.ndarray]:
    """셀 0(경계, 안쪽 (1,0)), 셀 1(경계, 안쪽 (0,1)), 셀 2(안쪽 셀)."""
    is_b = np.array([True, True, False])
    inward = np.array([[1.0, 0.0], [0.0, 1.0], [0.0, 0.0]])
    return is_b, inward


def test_all_border_pixels_moving_inward_gives_one() -> None:
    """경계 픽셀 3개가 모두 안쪽으로 움직이면 1.0이다."""
    is_b, inward = border_setup()
    cell_ids = np.array([0, 0, 1])
    vel = np.array([[0.5, 0.0], [0.2, 0.3], [-0.1, 0.4]])
    assert inflow_ratio(cell_ids, vel, is_b, inward) == 1.0


def test_tangential_border_pixel_counts_only_in_denominator() -> None:
    """셀 0에서 안쪽 (0.5, 0) 1개, 경계를 따라 가는 (0, 0.3) 1개.

    접선 픽셀은 안쪽 방향과 내적이 0이라 분모에만 들어가 1/2 = 0.5.
    """
    is_b, inward = border_setup()
    cell_ids = np.array([0, 0])
    vel = np.array([[0.5, 0.0], [0.0, 0.3]])
    assert inflow_ratio(cell_ids, vel, is_b, inward) == 0.5


def test_half_inward_half_outward_gives_half() -> None:
    """셀 0에서 안쪽 2개, 바깥쪽 1개, 셀 1에서 바깥쪽 1개면 2/4 = 0.5."""
    is_b, inward = border_setup()
    cell_ids = np.array([0, 0, 0, 1])
    vel = np.array([[0.5, 0.0], [0.3, 0.1], [-0.4, 0.0], [0.0, -0.2]])
    assert inflow_ratio(cell_ids, vel, is_b, inward) == 0.5


def test_interior_cell_pixels_are_ignored() -> None:
    """안쪽 셀 2의 픽셀 3개는 빠지고 경계 픽셀 1개(안쪽)만 남아 1.0."""
    is_b, inward = border_setup()
    cell_ids = np.array([0, 2, 2, 2])
    vel = np.array([[0.5, 0.0], [-1.0, 0.0], [-1.0, 0.0], [0.0, -1.0]])
    assert inflow_ratio(cell_ids, vel, is_b, inward) == 1.0


def test_slow_pixels_are_ignored() -> None:
    """속력 0.04 < 0.05 픽셀 2개(바깥쪽)는 빠진다.

    속력 0.05 정확히는 움직임으로 센다 (>=). 셀 1의 (0, -0.05)는
    바깥쪽이라 분모에만 들어가 1/2 = 0.5.
    """
    is_b, inward = border_setup()
    cell_ids = np.array([0, 0, 0, 1])
    vel = np.array(
        [[0.5, 0.0], [-0.04, 0.0], [0.0, -0.04], [0.0, -0.05]],
    )
    assert inflow_ratio(cell_ids, vel, is_b, inward) == 0.5


def test_no_movement_at_border_gives_none() -> None:
    """경계 픽셀이 모두 멈춰 있으면 분모가 0이라 0이 아닌 None이다."""
    is_b, inward = border_setup()
    cell_ids = np.array([0, 1, 2])
    vel = np.array([[0.0, 0.0], [0.01, 0.0], [1.0, 0.0]])
    assert inflow_ratio(cell_ids, vel, is_b, inward) is None


def test_non_finite_pixels_are_excluded() -> None:
    """NaN·inf 픽셀 2개는 빠지고 안쪽 1개, 바깥쪽 1개가 남아 0.5."""
    is_b, inward = border_setup()
    cell_ids = np.array([0, 0, 0, 0])
    vel = np.array(
        [[0.5, 0.0], [-0.5, 0.0], [np.nan, 0.0], [np.inf, 0.0]],
    )
    assert inflow_ratio(cell_ids, vel, is_b, inward) == 0.5


def test_pixels_with_cell_id_minus_one_are_excluded() -> None:
    """셀 번호 -1 픽셀 2개(접선 방향)는 빠져 1/1 = 1.0.

    두 셀 모두 경계라서 -1을 아무 셀로 잘못 읽어도 분모에 들어가 1/3이
    된다.
    """
    is_b = np.array([True, True])
    inward = np.array([[1.0, 0.0], [-1.0, 0.0]])
    cell_ids = np.array([0, -1, -1])
    vel = np.array([[0.5, 0.0], [0.0, 0.5], [0.0, 0.5]])
    assert inflow_ratio(cell_ids, vel, is_b, inward) == 1.0


@pytest.mark.parametrize(
    ("cell_ids", "vel", "is_b", "inward"),
    [
        # 셀 번호 2개, 속도 3개
        ([0, 1], [[0.5, 0.0]] * 3, [True, True], [[1.0, 0.0]] * 2),
        # 속도가 (N, 2)가 아니다
        ([0, 1], [0.5, 0.0], [True, True], [[1.0, 0.0]] * 2),
        # 경계 표시 2개, 안쪽 벡터 3개
        ([0, 1], [[0.5, 0.0]] * 2, [True, True], [[1.0, 0.0]] * 3),
        # 셀 번호가 셀 수(2) 이상
        ([0, 2], [[0.5, 0.0]] * 2, [True, True], [[1.0, 0.0]] * 2),
    ],
)
def test_mismatched_shapes_raise_value_error(
    cell_ids: list, vel: list, is_b: list, inward: list,
) -> None:
    """입력 모양이 맞지 않으면 ValueError다."""
    with pytest.raises(ValueError):
        inflow_ratio(
            np.array(cell_ids), np.array(vel),
            np.array(is_b), np.array(inward),
        )


def test_fewer_moving_border_pixels_than_min_pixels_gives_none() -> None:
    """움직이는 경계 픽셀 2개: min_pixels 3이면 None, 2이면 1/2 = 0.5."""
    is_b, inward = border_setup()
    cell_ids = np.array([0, 0, 2])
    vel = np.array([[0.5, 0.0], [-0.5, 0.0], [1.0, 0.0]])
    assert inflow_ratio(cell_ids, vel, is_b, inward, min_pixels=3) is None
    assert inflow_ratio(cell_ids, vel, is_b, inward, min_pixels=2) == 0.5


def test_cell_id_below_minus_one_raises_value_error() -> None:
    """셀 번호 -2는 -1(제외)과 달리 잘못된 값이라 ValueError다."""
    is_b, inward = border_setup()
    with pytest.raises(ValueError):
        inflow_ratio(
            np.array([0, -2]), np.array([[0.5, 0.0]] * 2), is_b, inward,
        )
