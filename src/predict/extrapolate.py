"""흐름 이류 핵심 수치 로직 (순수 numpy, I/O 없음).

- advect_density : 질량 보존 이류(기본 2차 TVD, 선택 1차 upwind)로 값을 흐름 방향으로 이동시킨다.
                   model.FlowAdvectionPredictor 가 셀별 인원수(밀도 × 보행 가능 면적)를 이동시키는 데 쓴다.

단위: 속도 = 셀/초. 모든 셀 면적이 같다고 보고 격자 값의 합을 보존한다.
"""
from __future__ import annotations

from typing import Tuple

import numpy as np

def _antidiffusive_flux(d: np.ndarray, uf: np.ndarray, h: float) -> np.ndarray:
    """x 방향 내부 면의 2차 보정 플럭스 (van Leer 제한자, flux-limited Lax-Wendroff).

    1차 upwind 플럭스에 더하면 TVD(새 극값을 만들지 않음) 2차 정밀도가 된다.
    모양이 뾰족한 구간에서는 제한자 φ 가 0 에 가까워져 자동으로 1차로 돌아간다.
    """
    dq = np.diff(d, axis=1)                      # 면 k 를 가로지르는 밀도 차 (rows, cols-1)
    prev = np.zeros_like(dq); prev[:, 1:] = dq[:, :-1]
    nxt = np.zeros_like(dq); nxt[:, :-1] = dq[:, 1:]
    upwind_jump = np.where(uf > 0, prev, nxt)    # 흐름 상류쪽 면의 밀도 차
    with np.errstate(divide="ignore", invalid="ignore"):
        theta = np.where(dq != 0, upwind_jump / dq, 0.0)
    phi = (theta + np.abs(theta)) / (1.0 + np.abs(theta))   # van Leer, θ<=0 이면 0
    courant = np.minimum(np.abs(uf) * h, 1.0)
    return 0.5 * np.abs(uf) * (1.0 - courant) * phi * dq


def _flux_x(d: np.ndarray, u: np.ndarray, h: float, scheme: str) -> np.ndarray:
    """x 방향 면 플럭스 (rows, cols+1). 양수 = +col(동쪽). 격자 경계는 유출만 허용(유입 0)."""
    rows, cols = d.shape
    fx = np.zeros((rows, cols + 1))
    if cols > 1:
        uf = 0.5 * (u[:, :-1] + u[:, 1:])
        flux = uf * np.where(uf > 0, d[:, :-1], d[:, 1:])          # 1차 upwind
        if scheme == "tvd" and cols > 2:
            flux = flux + _antidiffusive_flux(d, uf, h)
        fx[:, 1:-1] = flux
    fx[:, 0] = np.minimum(u[:, 0], 0.0) * d[:, 0]
    fx[:, -1] = np.maximum(u[:, -1], 0.0) * d[:, -1]
    return fx


def _clip_conserve(d: np.ndarray, target_mass: float) -> np.ndarray:
    """부동소수점/제한자 오차로 생긴 미세 음수를 0 으로 자르고, 총량을 target 에 맞춘다."""
    d = np.clip(d, 0.0, None)
    total = float(d.sum())
    if total > 0.0 and target_mass > 0.0 and abs(total - target_mass) > 1e-12:
        d = d * (target_mass / total)
    return d


SCHEMES = ("tvd", "upwind")


def advect_density(
    density: np.ndarray,
    u: np.ndarray,
    v: np.ndarray,
    dt: float,
    cfl_max: float = 0.5,
    scheme: str = "tvd",
) -> Tuple[np.ndarray, float]:
    """밀도를 dt 초 동안 (u, v) 흐름으로 이류시킨다 (질량 보존, 방향 분할 x→y).

    - scheme="tvd"   : 2차 정밀도 + van Leer 제한자. 수치 확산(번짐)이 적다. (기본)
    - scheme="upwind": 1차 upwind. 안정적이지만 덩어리가 빠르게 퍼진다. (비교/롤백용)
    - 격자 바깥으로는 유출만 허용(유입 0). 두 번째 반환값은 유출된 밀도 합(셀 단위).
    - CFL 안정성을 위해 필요하면 dt 를 내부적으로 서브스텝으로 쪼갠다.
    """
    if scheme not in SCHEMES:
        raise ValueError("scheme 은 {} 중 하나여야 한다: {!r}".format(SCHEMES, scheme))
    d = np.array(density, dtype=float, copy=True)
    u = np.asarray(u, dtype=float)
    v = np.asarray(v, dtype=float)

    max_rate = float(np.max(np.abs(u) + np.abs(v))) if d.size else 0.0
    n_sub = max(1, int(np.ceil(max_rate * dt / cfl_max))) if max_rate > 0 else 1
    h = dt / n_sub
    outflow = 0.0

    for _ in range(n_sub):
        before = float(d.sum())

        fx = _flux_x(d, u, h, scheme)
        d = d - h * (fx[:, 1:] - fx[:, :-1])
        lost = h * float(-fx[:, 0].sum() + fx[:, -1].sum())

        fy = _flux_x(d.T, v.T, h, scheme).T       # y 방향은 전치해서 같은 코드를 재사용
        d = d - h * (fy[1:, :] - fy[:-1, :])
        lost += h * float(-fy[0, :].sum() + fy[-1, :].sum())

        d = _clip_conserve(d, before - lost)
        outflow += lost

    return d, outflow
