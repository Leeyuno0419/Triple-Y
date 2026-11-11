"""T1~T4 테스트 경계: ground.orient_homography·sample_head_flow·
head_ground_velocity·head_cell_ids 시험.

머리 점·흐름·행렬을 손으로 정해 넣고, 지면 위치(m)·속도(m/s)·
셀 번호를 손으로 계산한 숫자와 비교한다.
"""
from __future__ import annotations

import numpy as np
import pytest

from src.flow.ground import (
    head_cell_ids, head_ground_velocity, orient_homography,
    sample_head_flow,
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


# ---- T1 orient_homography ----

def _e04_039() -> tuple[dict, list[dict]]:
    """E04_039 구역 설정과 build_cells로 만든 실제 셀을 읽는다."""
    import json
    from pathlib import Path

    from src.counting.cells import build_cells

    cfg = json.loads(
        Path("infra/homography/E04_039.json").read_text(encoding="utf-8")
    )
    cells = build_cells(
        np.array(cfg["H_img_to_ground"]), cfg["walkable_polygon_px"],
        (1920, 1080), origin_m=cfg["cell_origin_m"],
    )
    return cfg, cells


def _w(h: np.ndarray, pts: np.ndarray) -> np.ndarray:
    """점 (M, 2) px의 동차 w (M,)를 준다."""
    return (h @ np.c_[pts, np.ones(len(pts))].T)[2]


def test_orient_keeps_positive_homography_as_copy() -> None:
    """이미 w > 0이면 같은 값의 사본을 주고 입력은 바꾸지 않는다."""
    h = np.eye(3)

    out = orient_homography(h, np.array([[1.0, 1.0]]))

    np.testing.assert_array_equal(out, np.eye(3))
    assert out is not h
    out[0, 0] = 5.0
    np.testing.assert_array_equal(h, np.eye(3))


def test_orient_flips_negative_homography() -> None:
    """−I는 w = −1 < 0이라 부호를 뒤집어 I를 준다."""
    h = -np.eye(3)

    out = orient_homography(h, np.array([[1.0, 1.0]]))

    np.testing.assert_array_equal(out, np.eye(3))
    np.testing.assert_array_equal(h, -np.eye(3))


def test_orient_real_e04_039_head_plane_is_positive_at_cells() -> None:
    """E04_039 머리 평면은 보행 영역 w < 0이다. 맞춘 뒤 모든 셀 중심 w > 0."""
    cfg, cells = _e04_039()
    h = np.array(cfg["head_plane"]["H_head_img_to_ground"])
    ref = np.array(
        [np.mean(c["image_polygon"], axis=0) for c in cells]
    ) * [1920, 1080]
    assert (_w(h, ref) < 0).all()

    out = orient_homography(h, ref)

    assert (_w(out, ref) > 0).all()
    np.testing.assert_allclose(out, -h)


def test_orient_rejects_mixed_sign_reference_points() -> None:
    """w = 1 − 0.1·y라 y = 5 (w 0.5)와 y = 15 (w −0.5)는 부호가 섞인다."""
    h = np.array([[1.0, 0, 0], [0, 1.0, 0], [0, -0.1, 1.0]])

    with pytest.raises(ValueError):
        orient_homography(h, np.array([[0.0, 5.0], [0.0, 15.0]]))


def test_orient_rejects_reference_point_on_horizon() -> None:
    """w = 1 − 0.1·y라 y = 10이면 w = 0, 지평선 위라 ValueError다."""
    h = np.array([[1.0, 0, 0], [0, 1.0, 0], [0, -0.1, 1.0]])

    with pytest.raises(ValueError):
        orient_homography(h, np.array([[0.0, 10.0]]))


@pytest.mark.parametrize("h, ref", [
    (np.zeros((2, 3)), np.array([[1.0, 1.0]])),
    (np.full((3, 3), np.nan), np.array([[1.0, 1.0]])),
    (np.eye(3), np.empty((0, 2))),
    (np.eye(3), np.array([[1.0, 1.0, 1.0]])),
])
def test_orient_rejects_bad_shapes(h: np.ndarray, ref: np.ndarray) -> None:
    """(3, 3) 유한 행렬과 (M ≥ 1, 2) 기준점이 아니면 ValueError다."""
    with pytest.raises(ValueError):
        orient_homography(h, ref)


# ---- T2 sample_head_flow ----

def _flow(hw: tuple[int, int], dx: float, dy: float) -> np.ndarray:
    """모든 화소가 (dx, dy) px인 흐름 (H, W, 2) float32."""
    flow = np.zeros((*hw, 2), dtype=np.float32)
    flow[..., 0], flow[..., 1] = dx, dy
    return flow


def test_sample_uniform_flow_gives_that_flow() -> None:
    """균일 흐름 (2, −1)이면 머리 (10, 10), r = 2 패치 중앙값도 (2, −1)."""
    disp = sample_head_flow(
        _flow((20, 20), 2.0, -1.0), np.array([[10.0, 10.0]]), 2,
    )

    np.testing.assert_array_equal(disp, [[2.0, -1.0]])


@pytest.mark.parametrize("n_fast, expected", [(4, 0.0), (5, 10.0)])
def test_sample_uses_componentwise_median(
    n_fast: int, expected: float,
) -> None:
    """r = 1 패치 9칸 중 n칸 dx = 10, 나머지 0: 4칸이면 0, 5칸이면 10."""
    flow = _flow((10, 10), 0.0, 0.0)
    cells = [(y, x) for y in (4, 5, 6) for x in (4, 5, 6)]
    for y, x in cells[:n_fast]:
        flow[y, x, 0] = 10.0

    disp = sample_head_flow(flow, np.array([[5.0, 5.0]]), 1)

    np.testing.assert_array_equal(disp, [[expected, 0.0]])


def test_sample_at_corner_uses_pixels_inside_frame() -> None:
    """머리 (0, 0), r = 2: 화면 안 3×3 = 9칸만 쓴다.

    9칸 중 x = 0 열 3칸은 dx 0, x = 1, 2 열 6칸은 dx 2라 중앙값 2다.
    화면 밖 칸을 가장자리 값으로 채우면(clip) 25칸 중 15칸이 x = 0
    열 값 0이라 중앙값 0이 되어 이 오류를 잡는다.
    """
    flow = _flow((10, 10), 0.0, 0.0)
    flow[:3, 1:3, 0] = 2.0

    disp = sample_head_flow(flow, np.array([[0.0, 0.0]]), 2)

    np.testing.assert_array_equal(disp, [[2.0, 0.0]])


@pytest.mark.parametrize("x, alive", [
    (-0.4, True), (-0.6, False), (19.4, True), (19.6, False),
])
def test_sample_centre_outside_frame_is_nan(x: float, alive: bool) -> None:
    """중심 np.rint(x)가 0~19 밖이면 NaN이다 (W = 20, x = W − 0.4는 밖)."""
    disp = sample_head_flow(
        _flow((20, 20), 1.0, 1.0), np.array([[x, 10.0]]), 2,
    )

    assert np.isfinite(disp).all() == alive
    if not alive:
        assert np.isnan(disp).all()


def test_sample_skips_nan_pixels_without_warning() -> None:
    """NaN 화소는 빼고 중앙값, 전부 NaN이면 NaN이다. 경고는 없다."""
    import warnings

    flow = _flow((10, 10), 3.0, 0.0)
    flow[4:7, 4:6] = np.nan      # 패치 9칸 중 6칸 NaN, 3칸 (3, 0)
    flow[0:3, 7:10] = np.nan     # 두 번째 머리 패치 전부 NaN
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        disp = sample_head_flow(
            flow, np.array([[5.0, 5.0], [8.0, 1.0]]), 1,
        )

    np.testing.assert_array_equal(disp[0], [3.0, 0.0])
    assert np.isnan(disp[1]).all()


def test_sample_empty_heads_gives_zero_by_two() -> None:
    """머리가 0개면 (0, 2)다."""
    disp = sample_head_flow(_flow((5, 5), 1.0, 0.0), np.empty((0, 2)), 2)

    assert disp.shape == (0, 2)


def test_sample_handles_many_heads_per_row() -> None:
    """머리마다 자기 패치를 쓴다: 왼쪽 절반 dx 1, 오른쪽 절반 dx 5."""
    flow = _flow((10, 20), 1.0, 0.0)
    flow[:, 10:, 0] = 5.0

    disp = sample_head_flow(
        flow, np.array([[3.0, 3.0], [15.0, 6.0], [4.0, 8.0]]), 1,
    )

    np.testing.assert_array_equal(disp[:, 0], [1.0, 5.0, 1.0])


@pytest.mark.parametrize("flow, heads, r", [
    (_flow((5, 5), 0, 0), np.array([[np.nan, 1.0]]), 1),
    (_flow((5, 5), 0, 0), np.array([[1.0, 1.0, 1.0]]), 1),
    (_flow((5, 5), 0, 0), np.array([[1.0, 1.0]]), -1),
    (_flow((5, 5), 0, 0), np.array([[1.0, 1.0]]), True),
    (_flow((5, 5), 0, 0), np.array([[1.0, 1.0]]), 1.5),
    (np.zeros((5, 5)), np.array([[1.0, 1.0]]), 1),
])
def test_sample_rejects_bad_input(
    flow: np.ndarray, heads: np.ndarray, r: object,
) -> None:
    """흐름 (H, W, 2), 유한한 (N, 2) 머리, 0 이상 정수 반경만 받는다."""
    with pytest.raises(ValueError):
        sample_head_flow(flow, heads, r)


# ---- T3 head_ground_velocity ----

_HORIZON = np.array([[1.0, 0, 0], [0, 1.0, 0], [0, -0.1, 1.0]])


def test_velocity_pure_scale() -> None:
    """H = diag(0.05, 0.05, 1), p (10, 20), d (2, 0), dt 0.1.

    g = (0.5, 1.0) m, g' = (0.6, 1.0) m → v = (1.0, 0.0) m/s.
    """
    g, v = head_ground_velocity(
        np.array([[10.0, 20.0]]), np.array([[2.0, 0.0]]),
        np.diag([0.05, 0.05, 1.0]), 0.1,
    )

    np.testing.assert_allclose(g, [[0.5, 1.0]], atol=1e-9)
    np.testing.assert_allclose(v, [[1.0, 0.0]], atol=1e-9)


def test_velocity_uses_projective_end_point() -> None:
    """H = [[1,0,0],[0,1,0],[0,0.01,1]], p (0, 0), d (0, 10), dt 1.

    g = (0, 0), g' = (0, 10) / (1 + 0.1) = (0, 9.0909…) → v = (0, 9.0909).
    p에서의 선형 근사(야코비안)면 (0, 10)이라 구분된다.
    """
    g, v = head_ground_velocity(
        np.array([[0.0, 0.0]]), np.array([[0.0, 10.0]]),
        np.array([[1.0, 0, 0], [0, 1.0, 0], [0, 0.01, 1.0]]), 1.0,
    )

    np.testing.assert_allclose(g, [[0.0, 0.0]], atol=1e-9)
    np.testing.assert_allclose(v, [[0.0, 10 / 1.1]], atol=1e-9)


def test_velocity_end_point_beyond_horizon_is_nan() -> None:
    """w = 1 − 0.1·y: p (5, 5) w 0.5 → g (10, 10), 끝점 y 15 w −0.5 → v NaN."""
    g, v = head_ground_velocity(
        np.array([[5.0, 5.0]]), np.array([[0.0, 10.0]]), _HORIZON, 1.0,
    )

    np.testing.assert_allclose(g, [[10.0, 10.0]], atol=1e-9)
    assert np.isnan(v).all()


def test_velocity_start_point_beyond_horizon_is_nan() -> None:
    """p (5, 12)는 w = −0.2라 g·v 모두 NaN이다."""
    g, v = head_ground_velocity(
        np.array([[5.0, 12.0]]), np.array([[0.0, -10.0]]), _HORIZON, 1.0,
    )

    assert np.isnan(g).all()
    assert np.isnan(v).all()


def test_velocity_nan_displacement_keeps_ground_point() -> None:
    """d가 NaN인 머리는 g는 유한하고 v만 NaN이다. 다른 머리는 영향 없다."""
    g, v = head_ground_velocity(
        np.array([[10.0, 20.0], [20.0, 20.0]]),
        np.array([[np.nan, np.nan], [2.0, 0.0]]),
        np.diag([0.05, 0.05, 1.0]), 0.1,
    )

    np.testing.assert_allclose(g, [[0.5, 1.0], [1.0, 1.0]], atol=1e-9)
    assert np.isnan(v[0]).all()
    np.testing.assert_allclose(v[1], [1.0, 0.0], atol=1e-9)


def test_velocity_empty_input() -> None:
    """머리가 0개면 g·v 모두 (0, 2)다."""
    g, v = head_ground_velocity(
        np.empty((0, 2)), np.empty((0, 2)), np.eye(3), 1.0,
    )

    assert g.shape == (0, 2) and v.shape == (0, 2)


@pytest.mark.parametrize("heads, disp, h, dt", [
    (np.zeros((1, 2)), np.zeros((1, 2)), np.eye(3), 0.0),
    (np.zeros((1, 2)), np.zeros((1, 2)), np.eye(3), -1.0),
    (np.zeros((2, 2)), np.zeros((1, 2)), np.eye(3), 1.0),
    (np.zeros((1, 3)), np.zeros((1, 3)), np.eye(3), 1.0),
    (np.zeros((1, 2)), np.zeros((1, 2)), np.zeros((2, 3)), 1.0),
])
def test_velocity_rejects_bad_input(
    heads: np.ndarray, disp: np.ndarray, h: np.ndarray, dt: float,
) -> None:
    """dt ≤ 0, 머리·변위 모양 불일치, H가 (3, 3)이 아니면 ValueError다."""
    with pytest.raises(ValueError):
        head_ground_velocity(heads, disp, h, dt)


# ---- T4 head_cell_ids ----

_GRID = [_cell(0, 0, []), _cell(0, 1, []), _cell(1, 0, [])]
_ORIGIN = (-0.5, -1.34)


@pytest.mark.parametrize("g, expected", [
    ((-0.5, -1.34), 0),
    ((1.5, -1.34), 1),
    ((1.49, 0.65), 0),
    ((-0.5, 0.66), 2),
    ((1.6, 0.7), -1),          # row 1, col 1 없음
    ((-0.6, 0.0), -1),         # col −1
    ((np.nan, 0.0), -1),
    ((np.inf, 0.0), -1),
])
def test_cell_ids_follow_floor_rule(
    g: tuple[float, float], expected: int,
) -> None:
    """(col, row) = floor((g − (−0.5, −1.34)) / 2), 없는 칸·NaN은 −1."""
    ids = head_cell_ids(np.array([g]), _GRID, _ORIGIN, 2.0)

    assert ids.dtype == np.int64
    assert ids.tolist() == [expected]


def test_cell_ids_empty_input() -> None:
    """머리가 0개면 (0,)이다."""
    ids = head_cell_ids(np.empty((0, 2)), _GRID, _ORIGIN, 2.0)

    assert ids.shape == (0,) and ids.dtype == np.int64


def test_cell_ids_reject_duplicate_row_col() -> None:
    """두 셀이 같은 (row, col)이면 지면 칸이 겹치므로 ValueError다."""
    with pytest.raises(ValueError):
        head_cell_ids(
            np.zeros((1, 2)), [_cell(2, 3, []), _cell(2, 3, [])],
            _ORIGIN, 2.0,
        )


def _count_cells_reference(
    ground_pts: np.ndarray, cells: list[dict],
    origin_m: tuple[float, float], cell_m: float,
) -> np.ndarray:
    """src/counting/run_density.py count_cells 본문을 그대로 옮긴 것.

    run_density는 torch·scipy를 import해 crowdsight 환경에서 불러올 수
    없다 (scipy 없음). 그래서 2026-11-11 본문을 옮겨 두고 비교한다.
    count_cells가 바뀌면 이 함수도 고친다.
    """
    index = {(c["row"], c["col"]): i for i, c in enumerate(cells)}
    counts = np.zeros(len(cells), int)
    rc = np.floor((ground_pts - origin_m) / cell_m).astype(int)
    for col, row in rc:
        i = index.get((row, col))
        if i is not None:
            counts[i] += 1
    return counts


def test_cell_ids_match_counting_count_cells_on_e04_039() -> None:
    """E04_039 실제 셀·원점에서 무작위 200점(시드 0)의 셀별 수가
    인원 세기 count_cells와 같다 (셀에서 센 머리 = 셀 속도에 든 머리).
    """
    cfg, cells = _e04_039()
    origin = tuple(cfg["cell_origin_m"])
    rows = max(c["row"] for c in cells) + 2
    cols = max(c["col"] for c in cells) + 2
    rng = np.random.default_rng(0)
    pts = np.array(origin) - 2.0 + rng.uniform(
        0, 1, (200, 2),
    ) * [cols * 2.0 + 2.0, rows * 2.0 + 2.0]

    ids = head_cell_ids(pts, cells, origin, 2.0)

    expected = _count_cells_reference(pts, cells, origin, 2.0)
    assert expected.sum() > 0 and (ids < 0).any()
    np.testing.assert_array_equal(
        np.bincount(ids[ids >= 0], minlength=len(cells)), expected,
    )
