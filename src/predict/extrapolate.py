"""흐름 외삽 핵심 수치 로직 (순수 numpy, I/O 없음).

- fill_flow_outside_view : 화각 밖 셀의 흐름을 화각 경계에서 바깥으로 번져 채운다.
- extend_density_outside_view : 화각 밖 셀의 초기 밀도를 화각 경계 밀도로부터 감쇠시키며 연장한다.
- advect_density         : 질량 보존 이류(기본 2차 TVD, 선택 1차 upwind)로 밀도를 흐름 방향으로 이동시킨다.

단위: 밀도 = 명/m², 속도 = 셀/초. 모든 셀 면적이 같으므로 밀도 합 = 질량(인원) 비례.
"""
from __future__ import annotations

from typing import Tuple

import numpy as np


def _shifted_sums(field: np.ndarray, known: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """상하좌우 4-이웃 중 known 인 셀의 값 합과 개수."""
    f = np.where(known, field, 0.0)
    k = known.astype(float)
    fp = np.pad(f, 1)
    kp = np.pad(k, 1)
    total = fp[:-2, 1:-1] + fp[2:, 1:-1] + fp[1:-1, :-2] + fp[1:-1, 2:]
    count = kp[:-2, 1:-1] + kp[2:, 1:-1] + kp[1:-1, :-2] + kp[1:-1, 2:]
    return total, count


def fill_flow_outside_view(
    u: np.ndarray,
    v: np.ndarray,
    visible: np.ndarray,
    decay: float = 0.9,
    max_iters: int = 50,
) -> Tuple[np.ndarray, np.ndarray]:
    """화각 밖(또는 흐름이 NaN 인) 셀의 흐름을 이웃 평균 × decay 로 바깥쪽으로 채운다.

    흐름이 전혀 없는 입력(known 이 하나도 없음)이면 0 흐름을 반환한다.
    """
    known = visible & np.isfinite(u) & np.isfinite(v)
    uf = np.where(known, u, 0.0).astype(float)
    vf = np.where(known, v, 0.0).astype(float)
    if not known.any():
        return uf, vf

    for _ in range(max_iters):
        if known.all():
            break
        su, cnt = _shifted_sums(uf, known)
        sv, _ = _shifted_sums(vf, known)
        newly = (~known) & (cnt > 0)
        if not newly.any():
            break
        safe = np.where(cnt > 0, cnt, 1.0)
        uf = np.where(newly, su / safe * decay, uf)
        vf = np.where(newly, sv / safe * decay, vf)
        known = known | newly
    return uf, vf


def extend_density_outside_view(
    density: np.ndarray,
    visible: np.ndarray,
    decay: float = 0.8,
    max_cells: int = 3,
    floor: float = 0.0,
) -> np.ndarray:
    """화각 밖 초기 밀도를 화각 경계 밀도로부터 바깥으로 연장한다.

    군중은 화각 경계에서 갑자기 끊기지 않고 이어진다는 가정이다.
    경계에 인접한 화각 밖 셀부터 한 겹씩 "이웃(이미 값이 있는 셀) 평균 × decay" 로 채우므로,
    경계에서 k 칸 떨어진 셀의 밀도는 대략 경계값 × decay^k 이다.
    max_cells 칸보다 먼 셀은 floor(사전값)로 둔다. 화각 안(visible) 셀은 그대로 둔다.
    visible 이 하나도 없으면 전부 floor 이다.
    """
    known = visible & np.isfinite(density)
    out = np.where(known, density, floor).astype(float)
    if not known.any():
        return out

    for _ in range(max(0, int(max_cells))):
        if known.all():
            break
        s, cnt = _shifted_sums(out, known)
        newly = (~known) & (cnt > 0)
        if not newly.any():
            break
        safe = np.where(cnt > 0, cnt, 1.0)
        out = np.where(newly, np.maximum(s / safe * decay, floor), out)
        known = known | newly
    return out


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
