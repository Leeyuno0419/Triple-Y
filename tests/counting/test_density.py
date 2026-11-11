"""머리 평면 행렬과 셀 세기 테스트."""
import cv2
import numpy as np

from src.counting.homography import head_plane_homography
from src.counting.run_density import count_cells


def _camera(height: float, f: float = 1000.0) -> np.ndarray:
    """높이 height(m)에서 아래로 40도, 옆으로 20도 돌아 내려다보는 가상 카메라 3×4 행렬."""
    pitch, yaw = np.deg2rad(40), np.deg2rad(20)
    rz = np.array([[np.cos(yaw), -np.sin(yaw), 0], [np.sin(yaw), np.cos(yaw), 0], [0, 0, 1]])
    # 지면 좌표 (x, y, z=위) → 카메라 좌표 (x 오른쪽, y 아래, z 앞)
    base = np.array([[1, 0, 0], [0, 0, -1], [0, 1, 0]], float)
    rx = np.array([[1, 0, 0], [0, np.cos(pitch), -np.sin(pitch)], [0, np.sin(pitch), np.cos(pitch)]])
    r = rx @ base @ rz
    c = np.array([0, -8.0, height])
    k = np.array([[f, 0, 960], [0, f, 540], [0, 0, 1]])
    return k @ np.column_stack([r, -r @ c])


def _project(p: np.ndarray, pts3: np.ndarray) -> np.ndarray:
    q = (p @ np.column_stack([pts3, np.ones(len(pts3))]).T).T
    return q[:, :2] / q[:, 2:]


def test_head_plane_maps_head_to_feet() -> None:
    """머리 평면 행렬은 머리 픽셀을 그 사람의 발 위치(지면)로 보낸다."""
    p = _camera(6.0)
    ground = np.array([[x, y, 0] for x in (-3, 0, 3) for y in (0, 4, 8)], float)
    h_ground = cv2.findHomography(_project(p, ground), ground[:, :2])[0]
    feet = np.array([[1.0, 2.0], [-2.0, 6.0], [2.5, 5.0]])
    heads_px = _project(p, np.column_stack([feet, np.full(3, 1.6)]))
    h_head = head_plane_homography(h_ground, (1920, 1080), 1.6)
    got = cv2.perspectiveTransform(heads_px.reshape(-1, 1, 2), h_head).reshape(-1, 2)
    assert np.allclose(got, feet, atol=1e-3)
    # 바닥 행렬을 그대로 쓰면 머리가 먼 쪽으로 밀린다
    naive = cv2.perspectiveTransform(heads_px.reshape(-1, 1, 2), h_ground).reshape(-1, 2)
    assert np.all(np.linalg.norm(naive - feet, axis=1) > 0.5)


def test_count_cells_drops_points_outside() -> None:
    """점은 해당 셀에 1명씩 들어가고, 셀 목록에 없는 칸이나 격자 밖 점은 버린다."""
    cells = [{"row": 0, "col": 0}, {"row": 0, "col": 1}, {"row": 1, "col": 0}]
    pts = np.array([[0.5, 0.5], [1.9, 1.9], [2.5, 0.1], [2.5, 2.5], [-0.1, 0.5], [0.3, 3.0]])
    counts = count_cells(pts, cells, (0.0, 0.0), 2.0)
    assert counts.tolist() == [2, 1, 1]
