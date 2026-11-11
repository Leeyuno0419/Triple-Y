"""T1·T2 테스트 경계: ground.build_cell_index·cell_homographies·
cell_velocity 시험.

셀 다각형(0~1 정규화 좌표)과 흐름을 손으로 정해 넣고,
픽셀별 셀 번호와 지면 속도(m/s)를 손으로 계산한 숫자와 비교한다.
"""
from __future__ import annotations

import numpy as np
import pytest

from src.flow.ground import (
    build_cell_index, cell_homographies, cell_velocity,
    prepare_cell_velocity,
)


def _cell(row: int, col: int, poly: list[list[float]]) -> dict:
    """timeline-spec meta.cells[] 모양의 셀 하나를 만든다."""
    return {
        "cell_id": f"c-{row:02d}{col:02d}",
        "row": row,
        "col": col,
        "walkable_area_m2": 4.0,
        "image_polygon": poly,
    }


def test_two_side_by_side_cells_split_frame_and_later_cell_wins_edge(
) -> None:
    """10×20 프레임을 좌우 반씩 나눈 두 셀은 각각 100 픽셀이다.

    공유 경계 열 x=10은 뒤 셀(1)이 가져간다.
    """
    cells = [
        _cell(0, 0, [[0, 0], [0.5, 0], [0.5, 1], [0, 1]]),
        _cell(0, 1, [[0.5, 0], [1, 0], [1, 1], [0.5, 1]]),
    ]

    idx = build_cell_index(cells, (10, 20))

    assert idx.shape == (10, 20)
    assert idx.dtype == np.int64
    assert (idx == 0).sum() == 100
    assert (idx == 1).sum() == 100
    assert idx[0, 9] == 0
    assert idx[0, 10] == 1
    assert idx[9, 19] == 1


def test_pixels_outside_all_polygons_are_minus_one() -> None:
    """10×20 프레임 왼쪽 위 셀 (0,0)~(5,5) px는 경계 포함 6×6=36 픽셀이다.

    나머지 200 − 36 = 164 픽셀은 -1이다.
    """
    cells = [_cell(0, 0, [[0, 0], [0.25, 0], [0.25, 0.5], [0, 0.5]])]

    idx = build_cell_index(cells, (10, 20))

    assert (idx == 0).sum() == 36
    assert (idx == -1).sum() == 164
    assert idx[5, 5] == 0
    assert idx[5, 6] == -1
    assert idx[6, 5] == -1


@pytest.mark.parametrize(
    "poly",
    [
        [[0, 0], [0.5, 0], [0.5, 1]],
        [[0, 0], [0.5, 0], [0.5, 1], [0, 1], [0, 0.5]],
        [[0, 0], [1.1, 0], [1.1, 1], [0, 1]],
        [[-0.1, 0], [0.5, 0], [0.5, 1], [-0.1, 1]],
    ],
    ids=["3pts", "5pts", "x_over_1", "x_below_0"],
)
def test_polygon_without_4_points_in_0_1_is_rejected(
    poly: list[list[float]],
) -> None:
    """꼭짓점이 4개가 아니거나 좌표가 [0, 1] 밖이면 ValueError다."""
    with pytest.raises(ValueError):
        build_cell_index([_cell(0, 0, poly)], (10, 20))


def test_coordinates_just_outside_0_1_within_tolerance_are_accepted(
) -> None:
    """1e-9만큼 벗어난 좌표(부동소수 오차)는 받아들인다."""
    poly = [[-1e-9, 0], [1 + 1e-9, 0], [1, 1], [0, 1]]

    idx = build_cell_index([_cell(0, 0, poly)], (10, 20))

    assert (idx == 0).sum() == 200


def _uniform_flow(hw: tuple[int, int], dx: float, dy: float) -> np.ndarray:
    """모든 픽셀이 (dx, dy) px 움직인 흐름 (H, W, 2)를 만든다."""
    flow = np.zeros((*hw, 2), dtype=np.float32)
    flow[..., 0] = dx
    flow[..., 1] = dy
    return flow


def test_square_cell_of_10px_on_2m_gives_0_2_m_per_px() -> None:
    """10×10 px 셀을 2 m 정사각형으로 보면 0.2 m/px이다.

    +5 px 흐름, dt 0.5 s → vx = 5 × 0.2 / 0.5 = 2.0 m/s, vy = 0.
    셀은 경계 포함 열 0~10 × 행 0~9 = 110 픽셀이다.
    """
    hw = (10, 20)
    cells = [_cell(0, 0, [[0, 0], [0.5, 0], [0.5, 1], [0, 1]])]
    idx = build_cell_index(cells, hw)

    vel = cell_velocity(
        _uniform_flow(hw, 5.0, 0.0),
        prepare_cell_velocity(
            idx, cell_homographies(cells, hw, 2.0),
        ),
        dt_s=0.5,
    )

    assert vel.shape == (110, 2)
    np.testing.assert_allclose(vel[:, 0], 2.0, atol=1e-9)
    np.testing.assert_allclose(vel[:, 1], 0.0, atol=1e-9)


def test_each_cell_uses_its_own_scale_and_outside_pixels_are_excluded(
) -> None:
    """셀 0은 10 px → 2 m (0.2 m/px), 셀 1은 가로 5 px → 2 m (0.4 m/px)이다.

    +5 px, dt 0.5 s → 셀 0 vx = 2.0, 셀 1 vx = 5 × 0.4 / 0.5 = 4.0 m/s.
    셀 0은 열 0~9 × 10행 = 100 px(열 10은 뒤 셀 1), 셀 1은 열 10~15 ×
    10행 = 60 px, 열 16~19 (40 px)는 셀 밖이라 빠져 N = 160이다.
    출력 순서는 cell_index[cell_index >= 0]의 행 우선 순서다.
    """
    hw = (10, 20)
    cells = [
        _cell(0, 0, [[0, 0], [0.5, 0], [0.5, 1], [0, 1]]),
        _cell(0, 1, [[0.5, 0], [0.75, 0], [0.75, 1], [0.5, 1]]),
    ]
    idx = build_cell_index(cells, hw)
    ids = idx[idx >= 0]

    vel = cell_velocity(
        _uniform_flow(hw, 5.0, 0.0),
        prepare_cell_velocity(
            idx, cell_homographies(cells, hw, 2.0),
        ),
        dt_s=0.5,
    )

    assert vel.shape == (160, 2)
    assert (ids == 0).sum() == 100
    assert (ids == 1).sum() == 60
    np.testing.assert_allclose(vel[ids == 0, 0], 2.0, atol=1e-9)
    np.testing.assert_allclose(vel[ids == 1, 0], 4.0, atol=1e-9)
    np.testing.assert_allclose(vel[:, 1], 0.0, atol=1e-9)
    # 첫 행: 열 0~9는 셀 0, 열 10~15는 셀 1 순서로 나온다
    np.testing.assert_allclose(vel[:16, 0], [2.0] * 10 + [4.0] * 6)


def test_vertical_flow_uses_cell_row_axis() -> None:
    """셀 1(가로 5 px, 세로 10 px)에서 +5 px 세로 흐름은 0.2 m/px이다.

    vy = 5 × 0.2 / 0.5 = 2.0 m/s, vx = 0 (지면 y는 row 방향).
    """
    hw = (10, 20)
    cells = [_cell(3, 7, [[0.5, 0], [0.75, 0], [0.75, 1], [0.5, 1]])]
    idx = build_cell_index(cells, hw)

    vel = cell_velocity(
        _uniform_flow(hw, 0.0, 5.0),
        prepare_cell_velocity(
            idx, cell_homographies(cells, hw, 2.0),
        ),
        dt_s=0.5,
    )

    np.testing.assert_allclose(vel[:, 0], 0.0, atol=1e-9)
    np.testing.assert_allclose(vel[:, 1], 2.0, atol=1e-9)


def test_trapezoid_cell_scale_depends_on_image_row() -> None:
    """원근 사다리꼴 셀: 위 변 6 px, 아래 변 10 px가 모두 2 m다.

    20×10 프레임에서 꼭짓점 px는 TL(2,0), TR(8,0), BR(10,10), BL(0,10).
    양 옆 변의 소실점이 (5,−15)이고 위·아래 변이 수평이라 지평선은
    y = −15 수평선이다. 그래서 같은 영상 행 안에서는 배율이 일정하고
    지면 y가 바뀌지 않는다. 행 y의 셀 폭은 6 + 0.4·y px이다.
    +3 px 흐름, dt 0.5 s:
    - y=0:  2/6 m/px → vx = 3 × (1/3) / 0.5 = 2.0 m/s
    - y=5:  2/8 m/px → vx = 3 × 0.25 / 0.5 = 1.5 m/s
    - y=10: 2/10 m/px → vx = 3 × 0.2 / 0.5 = 1.2 m/s
    vy는 모두 0이다.
    """
    hw = (20, 10)
    cells = [_cell(0, 0, [[0.2, 0], [0.8, 0], [1.0, 0.5], [0, 0.5]])]
    idx = build_cell_index(cells, hw)

    vel = cell_velocity(
        _uniform_flow(hw, 3.0, 0.0),
        prepare_cell_velocity(
            idx, cell_homographies(cells, hw, 2.0),
        ),
        dt_s=0.5,
    )
    field = np.full((*hw, 2), np.nan)
    field[idx >= 0] = vel

    np.testing.assert_allclose(field[0, 5], [2.0, 0.0], atol=1e-6)
    np.testing.assert_allclose(field[5, 5], [1.5, 0.0], atol=1e-6)
    np.testing.assert_allclose(field[10, 5], [1.2, 0.0], atol=1e-6)


@pytest.mark.parametrize(
    "flow_hw, index_hw",
    [((10, 21), (10, 20)), ((10, 20), (10, 21))],
    ids=["flow_wider", "index_wider"],
)
def test_mismatched_shapes_are_rejected(
    flow_hw: tuple[int, int], index_hw: tuple[int, int],
) -> None:
    """flow (H, W, 2)와 cell_index (H, W)의 H, W가 다르면 ValueError다."""
    cells = [_cell(0, 0, [[0, 0], [0.5, 0], [0.5, 1], [0, 1]])]
    idx = np.zeros(index_hw, dtype=np.int64)

    with pytest.raises(ValueError):
        cell_velocity(
            _uniform_flow(flow_hw, 1.0, 0.0),
            prepare_cell_velocity(
                idx, cell_homographies(cells, (10, 20), 2.0),
            ),
            dt_s=0.5,
        )


def test_flow_without_two_channels_is_rejected() -> None:
    """flow 마지막 축이 2가 아니면 ValueError다."""
    hw = (10, 20)
    cells = [_cell(0, 0, [[0, 0], [0.5, 0], [0.5, 1], [0, 1]])]
    idx = build_cell_index(cells, hw)

    with pytest.raises(ValueError):
        cell_velocity(
            np.zeros((10, 20, 3), dtype=np.float32),
            prepare_cell_velocity(
                idx, cell_homographies(cells, hw, 2.0),
            ),
            dt_s=0.5,
        )


def test_cell_index_beyond_homographies_is_rejected() -> None:
    """셀 번호 1이 있는데 호모그래피가 1개(번호 0)뿐이면 ValueError다."""
    hw = (10, 20)
    cells = [_cell(0, 0, [[0, 0], [0.5, 0], [0.5, 1], [0, 1]])]
    idx = np.ones(hw, dtype=np.int64)

    with pytest.raises(ValueError):
        cell_velocity(
            _uniform_flow(hw, 1.0, 0.0),
            prepare_cell_velocity(
                idx, cell_homographies(cells, hw, 2.0),
            ),
            dt_s=0.5,
        )


def test_homography_uses_unrounded_fractional_pixel_corners() -> None:
    """x = 0.33인 꼭짓점은 10 px 프레임에서 3.3 px이다 (3으로 반올림 안 함).

    가로 3.3 px → 2 m라 2/3.3 = 20/33 m/px. +1 px, dt 1 s →
    vx = 20/33 ≈ 0.60606 m/s (반올림했다면 2/3 ≈ 0.66667).
    """
    hw = (10, 10)
    cells = [_cell(0, 0, [[0, 0], [0.33, 0], [0.33, 1], [0, 1]])]
    idx = build_cell_index(cells, hw)

    vel = cell_velocity(
        _uniform_flow(hw, 1.0, 0.0),
        prepare_cell_velocity(
            idx, cell_homographies(cells, hw, 2.0),
        ),
        dt_s=1.0,
    )

    np.testing.assert_allclose(vel[:, 0], 0.6060606, atol=1e-6)
    np.testing.assert_allclose(vel[:, 1], 0.0, atol=1e-6)


_BAD_ORDER_POLYS = {
    # 꼭짓점 순서가 TL, TR, BL, BR이라 변이 꼬인다
    "bowtie": [[0, 0], [0.5, 0], [0, 1], [0.5, 1]],
    # TL과 TR이 같아 넓이가 있는 사각형이 아니다
    "duplicate": [[0, 0], [0, 0], [0.5, 1], [0, 1]],
}


@pytest.mark.parametrize("name", list(_BAD_ORDER_POLYS))
def test_non_convex_or_wrongly_ordered_polygon_is_rejected_by_index(
    name: str,
) -> None:
    """꼬였거나 넓이가 없는 사각형이면 build_cell_index가 ValueError를
    낸다."""
    cells = [_cell(0, 0, _BAD_ORDER_POLYS[name])]

    with pytest.raises(ValueError):
        build_cell_index(cells, (10, 20))


@pytest.mark.parametrize("name", list(_BAD_ORDER_POLYS))
def test_non_convex_or_wrongly_ordered_polygon_is_rejected_by_homographies(
    name: str,
) -> None:
    """같은 다각형을 cell_homographies도 ValueError로 거부한다."""
    cells = [_cell(0, 0, _BAD_ORDER_POLYS[name])]

    with pytest.raises(ValueError):
        cell_homographies(cells, (10, 20), 2.0)


def test_counter_clockwise_polygon_maps_corners_in_ground_order() -> None:
    """바닥 y축이 영상 위쪽을 향하면 꼭짓점이 화면에서 반시계가 된다.

    src/counting/cells.py는 꼭짓점을 바닥 순서 (0,0)→(s,0)→(s,s)→(0,s)로
    내므로 영상에서 BL, BR, TR, TL이다. 이 순서도 받아야 하며 첫 꼭짓점이
    지면 (col·s, row·s)로 간다.
    """
    poly = [[0, 1], [0.5, 1], [0.5, 0], [0, 0]]
    cells = [_cell(1, 2, poly)]

    idx = build_cell_index(cells, (10, 20))
    hs = cell_homographies(cells, (10, 20), 2.0)

    assert (idx == 0).sum() == 11 * 10  # 열 x=0~10, 행 y=0~9
    for (x, y), g in zip(poly, [[4, 2], [6, 2], [6, 4], [4, 4]]):
        q = hs[0] @ np.array([x * 20, y * 10, 1.0])
        np.testing.assert_allclose(q[:2] / q[2], g, atol=1e-9)


def test_real_e04_039_cells_are_accepted() -> None:
    """이유노 님 셀 생성기(build_cells)로 만든 E04_039 실제 셀을
    번호표와 호모그래피가 모두 받고, 번호표는 cell_index_map과 같다."""
    import json
    from pathlib import Path

    from src.counting.cells import build_cells, cell_index_map

    cfg = json.loads(
        Path("infra/homography/E04_039.json").read_text(encoding="utf-8")
    )
    cells = build_cells(
        np.array(cfg["H_img_to_ground"]), cfg["walkable_polygon_px"],
        (1920, 1080), origin_m=cfg["cell_origin_m"],
    )

    idx = build_cell_index(cells, (1080, 1920))
    hs = cell_homographies(cells, (1080, 1920), 2.0)

    assert len(cells) > 0 and hs.shape == (len(cells), 3, 3)
    np.testing.assert_array_equal(idx, cell_index_map(cells, (1920, 1080)))


def test_duplicate_row_col_is_rejected() -> None:
    """두 셀이 같은 (row, col)이면 지면 칸이 겹치므로 ValueError다."""
    cells = [
        _cell(2, 3, [[0, 0], [0.5, 0], [0.5, 1], [0, 1]]),
        _cell(2, 3, [[0.5, 0], [1, 0], [1, 1], [0.5, 1]]),
    ]

    with pytest.raises(ValueError):
        cell_homographies(cells, (10, 20), 2.0)


def test_pixels_at_or_beyond_horizon_are_nan() -> None:
    """H = [[1,0,0],[0,1,0],[0,−1,5]]이면 w = 5 − y라 y ≥ 5 픽셀은 NaN이다.

    흐름이 0이면 y = 0~4 픽셀 속도는 (0, 0)이다.
    """
    hs = np.array([[[1.0, 0, 0], [0, 1.0, 0], [0, -1.0, 5.0]]])
    idx = np.zeros((8, 1), dtype=np.int64)

    vel = cell_velocity(
        _uniform_flow((8, 1), 0.0, 0.0), prepare_cell_velocity(idx, hs),
        dt_s=1.0,
    )

    np.testing.assert_array_equal(
        vel[:, 0], [0, 0, 0, 0, 0, np.nan, np.nan, np.nan],
    )
