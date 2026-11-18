"""camera_fit: 알려진 카메라로 만든 머리·발 쌍과 노면 표시에서 카메라를 되찾는지 확인한다."""
from __future__ import annotations

import numpy as np

from src.counting.camera_fit import _project, fit_camera, head_heights, plane_homography

SIZE = (1920, 1080)
TRUE = np.array([1300.0, np.radians(35), np.radians(2), 9.0])


def _inputs() -> dict[str, object]:
    """참 카메라로 사람 9명(머리 1.55m)과 같은 크기 글자 2개, 길 방향 직선을 투영한다."""
    rng = np.random.default_rng(0)
    feet = np.c_[rng.uniform(-3, 3, 9), rng.uniform(8, 25, 9)]
    pairs = [list(_project(TRUE, SIZE, np.array([[x, y, 1.55]]))[0]) + list(_project(TRUE, SIZE, np.array([[x, y, 0.0]]))[0])
             for x, y in feet]
    glyphs = [_project(TRUE, SIZE, np.array([[x, y, 0], [x + 0.9, y, 0], [x + 0.9, y - 2.4, 0], [x, y - 2.4, 0]],
                                            float)).tolist() for x, y in ((-1.0, 18.0), (-1.0, 14.0))]
    line = _project(TRUE, SIZE, np.array([[0.0, y, 0.0] for y in (7, 9, 12, 15)])).tolist()
    return {"head_h_m": 1.55, "head_feet_pairs_px": pairs, "same_size_glyphs_px": glyphs, "road_line_px": line}


def test_fit_recovers_camera() -> None:
    """잡음 없는 입력이면 카메라 높이·각도·초점거리를 거의 그대로 되찾는다."""
    inputs = _inputs()
    p = fit_camera(inputs, SIZE)
    assert abs(p[0] - TRUE[0]) < 20
    assert abs(np.degrees(p[1] - TRUE[1])) < 0.5
    assert abs(p[3] - TRUE[3]) < 0.1
    assert np.allclose(head_heights(p, inputs, SIZE), 1.55, atol=0.02)


def test_plane_homography_maps_ground_and_head() -> None:
    """바닥 행렬은 발 픽셀을, 머리 평면 행렬은 머리 픽셀을 같은 바닥 위치로 보낸다."""
    pt = np.array([[1.0, 12.0]])
    for z in (0.0, 1.55):
        px = _project(TRUE, SIZE, np.c_[pt, [[z]]])
        g = np.c_[px, [[1.0]]] @ plane_homography(TRUE, SIZE, z).T
        assert np.allclose(g[:, :2] / g[:, 2:], pt, atol=1e-6)
