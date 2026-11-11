"""픽셀 변위를 지면 속도(m/s)로 바꾼다.

build_cell_index·prepare_cell_velocity·cell_velocity는 timeline-spec
v0.1의 meta.cells (image_polygon, row, col)와 cell_size_m으로 셀마다
호모그래피를 만든다 (테스트 경계 T1·T2).
"""
from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np


# 동차 좌표 w가 이 값 이하면 지평선 위·카메라 뒤 픽셀로 보고 버린다
_MIN_W = 1e-9
# 정규화 좌표가 [0, 1]을 이만큼 벗어나도 부동소수 오차로 보고 받는다
_COORD_TOL = 1e-6


def build_cell_index(
    cells: list[dict], frame_hw: tuple[int, int],
) -> np.ndarray:
    """meta.cells의 영상 다각형으로 픽셀별 셀 번호표 (H, W) int64를 만든다.

    값은 cells 목록 안의 순서(0부터)이며 cell_id를 해석하지 않는다.
    어느 다각형에도 들지 않는 픽셀은 -1이다.
    정규화 좌표 (x, y)는 (x·W, y·H)로 바꾸고 np.rint로 반올림해
    cv2.fillPoly로 칠한다. 경계 픽셀도 칠해진다.
    다각형이 겹치면(공유 경계 포함) 목록에서 뒤에 오는 셀이 가져간다.
    그래서 원근 격자에서 셀 픽셀 수 Q_c가 셀마다 약 ±3% 치우친다(리뷰
    측정). 번호표는 반올림한 꼭짓점을, cell_homographies는 반올림 없는
    꼭짓점을 써서 둘은 최대 0.5 px 어긋난다. MVP에서는 이 규칙을 쓴다.
    꼭짓점이 4개가 아니거나 좌표가 [0, 1]을 1e-6 넘게 벗어나면
    ValueError다.
    """
    h, w = frame_hw
    idx = np.full((h, w), -1, dtype=np.int32)  # fillPoly는 int64를 못 쓴다
    for i, cell in enumerate(cells):
        pts = _polygon_points(cell)
        px = np.rint(pts * [w, h]).astype(np.int32)
        cv2.fillPoly(idx, [px], int(i))
    return idx.astype(np.int64)


def _polygon_points(cell: dict) -> np.ndarray:
    """셀의 image_polygon을 검사해 (4, 2) 정규화 좌표로 돌려준다.

    꼭짓점 4개, 좌표 0~1(허용 1e-6), 그리고 이웃 변의 외적이 모두 같은
    부호(볼록 사각형)여야 한다. 꼬인 사각형·겹친 꼭짓점은 ValueError다.
    회전 방향은 따지지 않는다. 꼭짓점은 바닥 순서로 오므로 바닥 y축이
    영상 위쪽을 향하는 카메라(E04_039)에서는 화면 반시계가 된다.
    W, H > 0 배율은 외적 부호를 바꾸지 않아 정규화 좌표로 검사한다.
    """
    pts = np.asarray(cell["image_polygon"], dtype=np.float64)
    if pts.shape != (4, 2):
        raise ValueError(
            f"{cell.get('cell_id')} image_polygon은 꼭짓점 4개여야 한다: "
            f"{pts.shape}"
        )
    if not (
        np.all(pts >= -_COORD_TOL) and np.all(pts <= 1 + _COORD_TOL)
    ):
        raise ValueError(
            f"{cell.get('cell_id')} image_polygon 좌표는 0~1이어야 한다"
        )
    e = np.roll(pts, -1, axis=0) - pts  # 변 벡터 TL→TR, TR→BR, ...
    turn = e[:, 0] * np.roll(e, -1, axis=0)[:, 1] - (
        e[:, 1] * np.roll(e, -1, axis=0)[:, 0]
    )
    if not (np.all(turn > 0) or np.all(turn < 0)):
        raise ValueError(
            f"{cell.get('cell_id')} image_polygon은 꼭짓점 순서가 맞는 "
            "볼록 사각형이어야 한다"
        )
    return pts


def cell_homographies(
    cells: list[dict], frame_hw: tuple[int, int], cell_size_m: float,
) -> np.ndarray:
    """셀마다 영상 px → 지면 m 호모그래피 (n, 3, 3)를 만든다 (영상당 한 번).

    셀 다각형 꼭짓점 4개는 차례로 지면 정사각형
    (col·s, row·s), ((col+1)·s, row·s), ((col+1)·s, (row+1)·s),
    (col·s, (row+1)·s)에 대응한다 (s = cell_size_m). src/counting/cells.py
    build_cells가 이 순서로 만든다. 그래서 지면 x는 col, y는 row 방향이며
    셀끼리 축이 같다. 영상에서의 회전 방향은 카메라에 따라 다르다.
    다각형 픽셀 좌표는 반올림 없이 (x·W, y·H)를 쓴다.
    같은 (row, col)이 두 번 나오면 ValueError다.
    """
    rc = [(cell["row"], cell["col"]) for cell in cells]
    if len(set(rc)) != len(rc):
        raise ValueError("cells에 같은 (row, col)이 두 번 이상 있다")
    h, w = frame_hw
    s = float(cell_size_m)
    hs = np.empty((len(cells), 3, 3), dtype=np.float64)
    for i, cell in enumerate(cells):
        src = (_polygon_points(cell) * [w, h]).astype(np.float32)
        r, c = cell["row"], cell["col"]
        dst = np.array(
            [[c, r], [c + 1, r], [c + 1, r + 1], [c, r + 1]],
            dtype=np.float32,
        ) * s
        hs[i] = cv2.getPerspectiveTransform(src, dst)
    return hs


@dataclass
class CellVelocityPlan:
    """cell_velocity가 영상마다 한 번 계산해 두는 픽셀별 값.

    셀 픽셀 N개를 cell_index[cell_index >= 0]의 행 우선 순서로 둔다.
    성분마다 연속 1차원 배열이라 프레임 계산이 빠르다.
    hw: 번호표 (H, W). mask: 셀 픽셀 (H, W) bool.
    q0: 픽셀 p의 H_c·(p, 1) (3, N). a: H_c의 앞 두 열 (3, 2, N).
    g0: 시작점 지면 좌표 (2, N) m, w ≤ 1e-9면 NaN.
    """

    hw: tuple[int, int]
    mask: np.ndarray
    q0: np.ndarray
    a: np.ndarray
    g0: np.ndarray


def prepare_cell_velocity(
    cell_index: np.ndarray, homographies: np.ndarray,
) -> CellVelocityPlan:
    """셀 픽셀마다 자기 셀 호모그래피와 시작점 지면 좌표를 미리 계산한다.

    homographies는 cell_homographies 출력 (n, 3, 3)이다. 영상당 한 번
    부른다. cell_index에 호모그래피가 없는 셀 번호가 있으면 ValueError다.
    메모리는 셀 픽셀당 약 90 B다 (1080p 전체 ≈ 190 MB).
    """
    if cell_index.size and cell_index.max() >= len(homographies):
        raise ValueError(
            f"cell_index 최대값 {cell_index.max()}이 호모그래피 "
            f"{len(homographies)}개를 넘는다"
        )
    mask = cell_index >= 0
    ys, xs = np.nonzero(mask)
    hp = homographies[cell_index[ys, xs]].transpose(1, 2, 0)  # (3, 3, N)
    a = np.ascontiguousarray(hp[:, :2])
    q0 = a[:, 0] * xs + a[:, 1] * ys + hp[:, 2]
    return CellVelocityPlan(
        hw=cell_index.shape, mask=mask, q0=q0, a=a, g0=_dehomog(q0),
    )


def cell_velocity(
    flow: np.ndarray, plan: CellVelocityPlan, dt_s: float,
) -> np.ndarray:
    """픽셀마다 자기 셀 호모그래피로 흐름 px를 지면 속도 (N, 2) m/s로 바꾼다.

    plan은 prepare_cell_velocity 출력이다.
    v = (H_c·(p + f) − H_c·p) / dt (proposal-detail 3.4(2)).
    H_c·(p + f) = H_c·p + H_c[:, :2]·f라서 프레임마다 뒤 항만 계산한다.
    픽셀 순서는 cell_index[cell_index >= 0]의 행 우선 순서라
    reduce_to_cells(ids, vel, n)과 맞는다. 시작점이나 끝점의
    w ≤ 1e-9인 픽셀(지평선 위·카메라 뒤)은 NaN이다.
    flow가 (H, W, 2)가 아니거나 H, W가 번호표와 다르면 ValueError다.
    """
    if flow.shape != (*plan.hw, 2):
        raise ValueError(
            f"모양이 맞지 않는다: flow {flow.shape}, "
            f"cell_index {plan.hw}"
        )
    dx = flow[..., 0][plan.mask].astype(np.float64)
    dy = flow[..., 1][plan.mask].astype(np.float64)
    q1 = plan.q0 + plan.a[:, 0] * dx + plan.a[:, 1] * dy
    return ((_dehomog(q1) - plan.g0) / dt_s).T


def _dehomog(q: np.ndarray) -> np.ndarray:
    """동차 좌표 (3, N)를 (2, N)으로 나눈다.

    w ≤ _MIN_W인 점(지평선 위·카메라 뒤)은 NaN이다. 0 나눗셈 경고는 없다.
    """
    w = q[2]
    inv = np.divide(1.0, w, out=np.full_like(w, np.nan), where=w > _MIN_W)
    return q[:2] * inv
