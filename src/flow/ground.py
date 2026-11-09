"""픽셀 변위를 지면 속도(m/s)로 바꾼다.

(가정) 임시 최소 구현이다. 호모그래피·셀 격자 형식은 이유노 님과 합의
전이라(D14) 셀 번호표(build_cell_index)는 아직 두지 않는다. 단독 시험(S2)도
합의 뒤에 붙이고, 지금은 S11 통합 시험에서 알려진 배율 H로만 확인한다.
"""
from __future__ import annotations

import numpy as np


# 동차 좌표 w가 이 값 이하면 지평선 위·카메라 뒤 픽셀로 보고 버린다
_MIN_W = 1e-9


def _apply_homography(h: np.ndarray, pts: np.ndarray) -> np.ndarray:
    """(N, 2) 영상 좌표에 3×3 호모그래피를 적용해 (N, 2) 지면 좌표를 낸다.

    w ≤ _MIN_W인 점(지평선 위·카메라 뒤)은 NaN이다. 0 나눗셈 경고는 없다.
    """
    ones = np.ones((pts.shape[0], 1), dtype=np.float64)
    p = np.hstack([pts.astype(np.float64), ones]) @ h.T
    w = p[:, 2:3]
    out = np.full((pts.shape[0], 2), np.nan)
    np.divide(p[:, :2], w, out=out, where=w > _MIN_W)
    return out


def ground_velocity(
    flow: np.ndarray, h: np.ndarray, dt_s: float, mask: np.ndarray,
) -> np.ndarray:
    """마스크 픽셀의 흐름 (H, W, 2) px를 지면 속도 (N, 2) m/s로 바꾼다.

    v = (H·(p + f) − H·p) / dt (proposal-detail 3.4(2)).
    픽셀 순서는 np.nonzero(mask)의 행 우선 순서이며 cell_index[mask]와 같다.
    시작점 p나 끝점 p + f의 w가 1e-9 이하(지평선 위·카메라 뒤)인 픽셀은
    NaN이며 reduce_to_cells가 버린다. S2에서 build_cell_index를 만들 때도
    이런 픽셀은 셀에서 빼야 한다 (-1).
    """
    ys, xs = np.nonzero(mask)
    p = np.stack([xs, ys], axis=1).astype(np.float64)
    d = flow[ys, xs].astype(np.float64)
    return (_apply_homography(h, p + d) - _apply_homography(h, p)) / dt_s
