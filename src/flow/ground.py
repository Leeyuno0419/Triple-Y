"""머리 점 변위를 머리 높이 평면으로 지면 속도로 바꾼다.

orient_homography·sample_head_flow·head_ground_velocity·head_cell_ids
(테스트 경계 T1~T4). 셀 배정은 인원 세기 count_cells와 같은 지면
좌표 규칙을 쓴다 (규격 v0.2 8절).
"""
from __future__ import annotations

import warnings

import numpy as np


# 동차 좌표 w가 이 값 이하면 지평선 위·카메라 뒤 점으로 보고 버린다
_MIN_W = 1e-9


def orient_homography(
    h: np.ndarray, ref_px: np.ndarray,
) -> np.ndarray:
    """ref_px 점들에서 동차 w가 양수가 되도록 부호를 맞춘 H 사본을 준다.

    H와 −H는 같은 사상이라 부호는 임의다. E04_039 행렬은 보행
    영역에서 w < 0이다. 그래서 w ≤ 1e-9 버림 규칙을 쓰기 전에
    부호를 맞춘다. ref_px는 (M, 2) px이며 보통 셀 다각형 중심이다.
    h가 (3, 3) 유한 행렬이 아니거나 ref_px가 (M ≥ 1, 2)가 아니면
    ValueError다. ref_px의 w가 0 근처(|w| ≤ 1e-9)이거나 부호가
    섞이면(지평선이 셀을 지남) 설정 오류라 ValueError다.
    """
    h = np.array(h, dtype=np.float64)
    ref = np.asarray(ref_px, dtype=np.float64)
    if h.shape != (3, 3) or not np.isfinite(h).all():
        raise ValueError(f"h는 유한한 (3, 3) 행렬이어야 한다: {h.shape}")
    if ref.ndim != 2 or ref.shape[1] != 2 or len(ref) == 0:
        raise ValueError(f"ref_px는 (M ≥ 1, 2)여야 한다: {ref.shape}")
    w = ref @ h[2, :2] + h[2, 2]
    if (np.abs(w) <= _MIN_W).any() or not (
        (w > 0).all() or (w < 0).all()
    ):
        raise ValueError("기준점 w가 0 근처이거나 부호가 섞여 있다")
    return h if w[0] > 0 else -h


def sample_head_flow(
    flow: np.ndarray, heads_px: np.ndarray, radius_px: int,
) -> np.ndarray:
    """머리 점마다 주변 패치 흐름의 성분별 중앙값 (N, 2) px를 준다.

    패치 중심은 np.rint(heads_px) (x, y)이고 크기는 (2r+1)²다.
    화면 밖 패치 픽셀과 NaN 픽셀은 빼고 중앙값을 낸다. 중심이 화면
    밖이거나 남는 픽셀이 없으면 그 머리는 NaN이다. 머리가 0개면
    (0, 2)를 준다. flow가 (H, W, 2)가 아니거나, heads_px가 유한한
    (N, 2)가 아니거나, radius_px가 0 이상 정수(bool 제외)가 아니면
    ValueError다.
    """
    flow = np.asarray(flow)
    heads = np.asarray(heads_px, dtype=np.float64)
    if flow.ndim != 3 or flow.shape[2] != 2:
        raise ValueError(f"flow는 (H, W, 2)여야 한다: {flow.shape}")
    if heads.ndim != 2 or heads.shape[1] != 2:
        raise ValueError(f"heads_px는 (N, 2)여야 한다: {heads.shape}")
    if not np.isfinite(heads).all():
        raise ValueError("heads_px에 NaN·inf가 있다")
    if (
        isinstance(radius_px, bool)
        or not isinstance(radius_px, (int, np.integer))
        or radius_px < 0
    ):
        raise ValueError(f"radius_px는 0 이상 정수여야 한다: {radius_px!r}")
    h, w = flow.shape[:2]
    c = np.rint(heads).astype(np.int64)              # (N, 2) x, y
    off = np.arange(-radius_px, radius_px + 1)
    ox, oy = np.meshgrid(off, off)
    xs = c[:, :1] + ox.ravel()                       # (N, K)
    ys = c[:, 1:] + oy.ravel()
    inside = (xs >= 0) & (xs < w) & (ys >= 0) & (ys < h)
    patch = flow[ys.clip(0, h - 1), xs.clip(0, w - 1)]
    patch = patch.astype(np.float64)                 # (N, K, 2)
    patch[~inside] = np.nan
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)  # 빈 패치
        disp = np.nanmedian(patch, axis=1)
    disp[~inside[:, off.size ** 2 // 2]] = np.nan    # 중심이 화면 밖
    return disp.reshape(-1, 2)


def head_ground_velocity(
    heads_px: np.ndarray,
    disp_px: np.ndarray,
    h_head: np.ndarray,
    dt_s: float,
) -> tuple[np.ndarray, np.ndarray]:
    """머리 점의 지면 위치 g (N, 2) m와 지면 속도 v (N, 2) m/s를 준다.

    g = H(p), g' = H(p + d), v = (g' − g) / dt (규격 v0.2 8절).
    두 끝점 모두 투영 변환을 그대로 쓴다 (p에서의 선형 근사 아님).
    h_head는 orient_homography를 거친 머리 높이 평면 행렬이다.
    시작점 w ≤ 1e-9면 g·v가 모두 NaN이고, 끝점만 그러면 v만 NaN이다.
    d가 NaN인 머리는 v가 NaN이다. 모양이 맞지 않거나 dt_s ≤ 0이면
    ValueError다.
    """
    p = np.asarray(heads_px, dtype=np.float64)
    d = np.asarray(disp_px, dtype=np.float64)
    h = np.asarray(h_head, dtype=np.float64)
    if p.ndim != 2 or p.shape[1] != 2 or d.shape != p.shape:
        raise ValueError(
            f"heads_px·disp_px는 같은 (N, 2)여야 한다: {p.shape}, {d.shape}"
        )
    if h.shape != (3, 3):
        raise ValueError(f"h_head는 (3, 3)이어야 한다: {h.shape}")
    if not dt_s > 0:
        raise ValueError(f"dt_s는 양수여야 한다: {dt_s}")
    g = _dehomog(h[:, :2] @ p.T + h[:, 2:])
    g1 = _dehomog(h[:, :2] @ (p + d).T + h[:, 2:])
    return g.T, ((g1 - g) / dt_s).T


def head_cell_ids(
    ground_m: np.ndarray,
    cells: list[dict],
    origin_m: tuple[float, float],
    cell_m: float,
) -> np.ndarray:
    """지면 점 (N, 2) m마다 meta.cells 순서의 셀 번호 (N,) int64를 준다.

    인원 세기(src/counting/run_density.py count_cells)와 같은 규칙:
    (col, row) = floor((g − origin_m) / cell_m). 그 (row, col)이
    cells에 없거나 g가 유한하지 않으면 −1이다. 같은 (row, col)이
    두 번 나오면 ValueError다.
    """
    index = {(c["row"], c["col"]): i for i, c in enumerate(cells)}
    if len(index) != len(cells):
        raise ValueError("cells에 같은 (row, col)이 두 번 이상 있다")
    g = np.asarray(ground_m, dtype=np.float64).reshape(-1, 2)
    ids = np.full(len(g), -1, dtype=np.int64)
    ok = np.isfinite(g).all(axis=1)
    rc = np.floor((g[ok] - origin_m) / cell_m).astype(np.int64)
    ids[ok] = [index.get((row, col), -1) for col, row in rc]
    return ids


def _dehomog(q: np.ndarray) -> np.ndarray:
    """동차 좌표 (3, N)를 (2, N)으로 나눈다.

    w ≤ _MIN_W인 점(지평선 위·카메라 뒤)은 NaN이다. 0 나눗셈 경고는 없다.
    """
    w = q[2]
    inv = np.divide(1.0, w, out=np.full_like(w, np.nan), where=w > _MIN_W)
    return q[:2] * inv
