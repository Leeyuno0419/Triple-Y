"""화각 경계 셀의 안쪽 방향 흐름 비율(inflow_ratio)을 구한다.

(가정) [토론] 정의는 아래와 같다. 팀 결정 대기.
- 지면 좌표: x는 격자 col, y는 격자 row 방향, 단위 m.
  셀 (row, col) 중심 = ((col+0.5)·s, (row+0.5)·s), s = cell_size_m.
- 경계 셀: image_polygon의 점 하나라도 정규화 좌표 0 또는 1에서
  edge_tol(기본 0.02) 안에 있는 셀.
- 안쪽 방향: 경계 셀 중심에서 구역 중심(모든 셀 중심의 평균)으로
  가는 단위 벡터.
- inflow_ratio = 경계 셀에서 움직이는 유효 표본(머리) 중 안쪽 방향과
  내적이 양수인 표본의 비율. 반올림하지 않는다(타임라인 작성 쪽에서
  반올림).
"""
from __future__ import annotations

import numpy as np


def boundary_inward(
    cells: list[dict],
    cell_size_m: float,
    edge_tol: float = 0.02,
) -> tuple[np.ndarray, np.ndarray]:
    """셀마다 경계 여부 (n,)와 안쪽 단위 벡터 (n, 2)를 돌려준다.

    (가정) [토론] 경계 셀은 image_polygon이 화면 가장자리(0 또는 1)에서
    edge_tol 안에 닿는 셀이다. 안쪽 방향은 셀 중심에서 구역 중심으로
    가는 지면 단위 벡터다. 경계가 아닌 셀은 (0, 0)이다.
    셀 중심이 구역 중심과 같으면 안쪽 방향이 없어 경계에서 뺀다.
    셀이 없으면 ValueError다.
    [토론] 구역 중심 방향은 L자·가로로 긴 구역에서 실제 진입 방향과
    어긋난다. 대안은 화면 가장자리의 법선을 셀 호모그래피 H로 지면에
    옮기는 것이다.
    [토론] 경계 판정은 격자 해상도에 따른다. 셀 폭이 edge_tol보다 좁으면
    가장자리에서 두 열이 경계가 된다.
    """
    if not cells:
        raise ValueError("셀이 없다")
    centres = np.array(
        [[(c["col"] + 0.5) * cell_size_m, (c["row"] + 0.5) * cell_size_m]
         for c in cells],
        dtype=np.float64,
    )
    is_boundary = np.array([
        bool(((p <= edge_tol) | (p >= 1 - edge_tol)).any())
        for p in (np.asarray(c["image_polygon"], dtype=np.float64)
                  for c in cells)
    ])
    to_centre = centres.mean(axis=0) - centres
    norm = np.linalg.norm(to_centre, axis=1, keepdims=True)
    is_boundary &= norm[:, 0] > 0
    inward = np.zeros_like(centres)
    inward[is_boundary] = to_centre[is_boundary] / norm[is_boundary]
    return is_boundary, inward


def inflow_ratio(
    cell_ids: np.ndarray,
    vel: np.ndarray,
    is_boundary: np.ndarray,
    inward: np.ndarray,
    min_speed: float = 0.05,
    min_samples: int = 0,
) -> float | None:
    """경계 셀 표본 중 안쪽으로 움직이는 표본의 비율 (0~1)을 구한다.

    표본은 머리 하나다. cell_ids (N,)·vel (N, 2)는 reduce_to_cells와
    같이 표본별로 맞춘다.
    (가정) [토론] 분모는 경계 셀에서 속력 min_speed(m/s) 이상인 표본 수,
    분자는 그중 안쪽 방향과 내적이 양수인 표본 수다.
    셀 번호 -1(보행 불가·격자 밖) 표본과 속도가 NaN·inf인 표본은 버린다.
    경계에 움직임이 없어 분모가 0이면 0이 아니라 None을 돌려준다.
    (가정) [토론] 움직이는 경계 표본이 min_samples보다 적어도 None이다.
    값은 팀이 정한다. 기본 0은 이 조건을 끈다. 경계에 사람이 적으면
    몇 명만으로 값이 튀고, 정지 잡음이 분모에 들어가면 0.5 쪽으로
    끌린다.
    입력 모양이 맞지 않거나 셀 번호가 -1보다 작으면 ValueError다.
    """
    cell_ids = np.asarray(cell_ids).astype(np.int64)
    vel = np.asarray(vel, dtype=np.float64)
    is_boundary = np.asarray(is_boundary, dtype=bool)
    inward = np.asarray(inward, dtype=np.float64)
    n_cells = len(is_boundary)
    if vel.ndim != 2 or vel.shape[1] != 2:
        raise ValueError(f"vel은 (N, 2)여야 한다: {vel.shape}")
    if cell_ids.shape != (len(vel),):
        raise ValueError("cell_ids와 vel의 표본 수가 다르다")
    if inward.shape != (n_cells, 2):
        raise ValueError("inward는 (셀 수, 2)여야 한다")
    if (cell_ids >= n_cells).any() or (cell_ids < -1).any():
        raise ValueError(f"셀 번호는 -1 이상 셀 수({n_cells}) 미만이다")
    inside = cell_ids >= 0
    # 경계 셀의 유한한 표본만 먼저 골라 속력·내적을 계산한다
    keep = inside & np.isfinite(vel).all(axis=1)
    keep[keep] = is_boundary[cell_ids[keep]]
    v = vel[keep]
    moving = np.linalg.norm(v, axis=1) >= min_speed
    dot = (v[moving] * inward[cell_ids[keep][moving]]).sum(axis=1)
    n_moving = int(moving.sum())
    if n_moving == 0 or n_moving < min_samples:
        return None
    return float((dot > 0).sum() / n_moving)
