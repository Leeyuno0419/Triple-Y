"""60초 예측의 단순 기준선과 오차 (중간 2).

정답은 흐름과 독립인 셀 밀도 rho*_c(t+T)다 (기획 2.3).
"""
from __future__ import annotations

import math

import numpy as np


def persistence_forecast(rho_now: np.ndarray) -> np.ndarray:
    """현재값 유지: T초 뒤 밀도 = 지금 밀도."""
    return rho_now.copy()


def advect_density(
    rho: np.ndarray,
    vel: np.ndarray,
    walkable: np.ndarray,
    cell_m: float,
    horizon_s: float,
    dt_s: float = 1.0,
) -> np.ndarray:
    """셀 밀도 (ny, nx)를 셀 속도 (ny, nx, 2)로 horizon_s초 옮긴다.

    흐름 외삽(가정)이다. 1차 상류(upwind) 유한체적이며, 예측 동안 속도는
    고정한다. vel[..., 0]은 열(x), vel[..., 1]은 행(y) 방향 속도
    [m/s]다. 보행 불가 셀과의 면은 막는다.

    - 바깥 경계 (가정) 팀 결정 대기: 격자 밖 유령 셀 밀도를 끝 셀 밀도로
      둔다 (0 기울기). 끝 셀 속도가 안쪽이면 끝 셀 밀도 × 속도만큼
      들어오고, 바깥쪽이면 그만큼 나간다. 나가는 흐름만 허용하면 일정한
      관통 흐름도 비워져 속도를 작게 잡을수록 유리해지기 때문이다.
    - 밀도 NaN (가정) 팀 결정 대기: 계산에선 0명으로 보고, 출력에선 입력이
      NaN이던 칸을 NaN으로 되돌린다. 현재값 유지와 같은 칸에서 채점하려는
      것이다.
    - 속도 NaN·±inf는 0(정지)으로 본다. 보행 불가 셀의 밀도·속도도 0이다.
    - (확인 필요) 보행 불가 셀에 있던 밀도는 경고 없이 버려진다.

    horizon_s / dt_s가 양의 정수가 아니거나, walkable 모양이 rho와 다르거나,
    vel 모양이 rho 모양 + (2,)가 아니거나, cell_m ≤ 0이면 ValueError다.
    """
    if walkable.shape != rho.shape:
        raise ValueError(
            f"walkable 모양 {walkable.shape} ≠ rho 모양 {rho.shape}"
        )
    if vel.shape != rho.shape + (2,):
        raise ValueError(
            f"vel 모양 {vel.shape} ≠ rho 모양 + (2,) {rho.shape + (2,)}"
        )
    if not cell_m > 0:
        raise ValueError(f"cell_m은 양수여야 한다: {cell_m}")
    steps = horizon_s / dt_s
    n_steps = int(round(steps))
    if n_steps < 1 or abs(steps - n_steps) > 1e-9:
        raise ValueError(
            f"horizon_s / dt_s는 양의 정수여야 한다: {steps}"
        )
    missing = np.isnan(rho)
    rho = np.where(walkable, np.nan_to_num(rho), 0.0)
    vel = np.nan_to_num(vel, nan=0.0, posinf=0.0, neginf=0.0)
    u = np.where(walkable, vel[..., 0], 0.0)
    v = np.where(walkable, vel[..., 1], 0.0)
    open_x = walkable[:, :-1] & walkable[:, 1:]
    open_y = walkable[:-1, :] & walkable[1:, :]
    ux = 0.5 * (u[:, :-1] + u[:, 1:]) * open_x
    vy = 0.5 * (v[:-1, :] + v[1:, :]) * open_y

    vmax = max(np.abs(u).max(initial=0.0), np.abs(v).max(initial=0.0))
    n_sub = max(1, math.ceil(vmax * dt_s / cell_m / 0.5))  # 축당 CFL <= 0.5
    h = dt_s / n_sub
    for _ in range(n_steps * n_sub):
        fx = np.where(ux > 0, rho[:, :-1], rho[:, 1:]) * ux  # 면 유량
        fy = np.where(vy > 0, rho[:-1, :], rho[1:, :]) * vy
        out = np.zeros_like(rho)  # 셀 순유출
        out[:, :-1] += fx
        out[:, 1:] -= fx
        out[:-1, :] += fy
        out[1:, :] -= fy
        # 바깥 경계: 유령 셀 = 끝 셀 (0 기울기). 부호 있는 유출.
        out[:, 0] -= rho[:, 0] * u[:, 0]
        out[:, -1] += rho[:, -1] * u[:, -1]
        out[0, :] -= rho[0, :] * v[0, :]
        out[-1, :] += rho[-1, :] * v[-1, :]
        rho = rho - h / cell_m * out
    return np.where(missing, np.nan, rho)


def mae(pred: np.ndarray, true: np.ndarray, mask: np.ndarray) -> float:
    """마스크 안에서 예측·정답이 모두 유한한 칸의 평균 절대 오차.

    마스크는 참·거짓으로 읽는다. 세 배열의 모양이 다르면 ValueError다.
    """
    mask = np.asarray(mask, dtype=bool)
    if not pred.shape == true.shape == mask.shape:
        raise ValueError(
            f"모양 불일치: pred {pred.shape}, true {true.shape}, "
            f"mask {mask.shape}"
        )
    ok = mask & np.isfinite(pred) & np.isfinite(true)
    if not ok.any():
        return float("nan")
    return float(np.abs(pred[ok] - true[ok]).mean())
