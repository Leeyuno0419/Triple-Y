"""픽셀 속도를 셀 통계로 줄인다. 흐름장은 저장하지 않는다."""
from __future__ import annotations

import warnings
from dataclasses import dataclass

import numpy as np


@dataclass
class CellFlow:
    """한 시점의 셀 통계. 흐름장은 담지 않는다."""

    mean_v: np.ndarray  # (n_cells, 2) 셀 평균 지면 속도 V_c [m/s], 빈 셀은 NaN
    count: np.ndarray   # (n_cells,) 유효 픽셀 수 Q_c
    counterflow: np.ndarray  # (n_cells,) 역방향 픽셀 비율 B_c [0~1], 빈 셀은 NaN


def reduce_to_cells(
    cell_ids: np.ndarray,
    vel: np.ndarray,
    n_cells: int,
    min_speed: float = 0.05,
) -> CellFlow:
    """픽셀 속도 (N, 2) 또는 (H, W, 2)를 셀 번호 (N,) 또는 (H, W)별로 모아 셀 통계를 만든다.

    셀 번호 -1(보행 불가·격자 밖) 픽셀은 버린다.
    역방향 비율은 셀 평균과 내적이 음수이고 속력이 min_speed(m/s, 가정) 이상인
    픽셀의 비율이다. 분모는 유효 픽셀 수 Q_c다.
    (가정) 주 흐름이 없는 셀은 NaN. 팀 결정 대기.
    셀 평균 속력이 min_speed보다 작으면 주 흐름이 없다고 본다.
    속도가 NaN·inf인 픽셀도 버린다.
    """
    cell_ids = np.asarray(cell_ids).astype(np.int64)
    vel = np.asarray(vel, dtype=np.float64)
    if (cell_ids >= n_cells).any():
        raise ValueError(f"셀 번호는 n_cells({n_cells})보다 작아야 한다")
    keep = (cell_ids >= 0) & np.isfinite(vel).all(axis=-1)
    cell_ids = cell_ids[keep]
    vel = vel[keep]
    count = np.bincount(cell_ids, minlength=n_cells).astype(np.float64)
    sx = np.bincount(cell_ids, weights=vel[:, 0], minlength=n_cells)
    sy = np.bincount(cell_ids, weights=vel[:, 1], minlength=n_cells)
    with np.errstate(invalid="ignore", divide="ignore"):
        mean_v = np.stack([sx, sy], axis=1) / count[:, None]
        dot = (vel * mean_v[cell_ids]).sum(axis=1)
        moving = np.linalg.norm(vel, axis=1) >= min_speed
        opp = np.bincount(
            cell_ids, weights=((dot < 0) & moving).astype(np.float64),
            minlength=n_cells,
        )
        counterflow = opp / count
        counterflow[np.linalg.norm(mean_v, axis=1) < min_speed] = np.nan
    return CellFlow(
        mean_v=mean_v, count=count.astype(np.int64), counterflow=counterflow,
    )


class TemporalInstability:
    """S_c(t) = max(<|V_c − U_c|²>_T − Var_noise_c, 0)를 갱신한다.

    난류 조사 6.4 (C1, C2). U_c는 최근 T초 창의 평균으로 둔다 (가정).
    분산은 두 성분 합을 유효 표본 수 n으로 나눈다. S6 잡음 분산과 같은
    규약이다. 셀 평균 시계열만 메모리에 두며 흐름장은 보관하지 않는다.
    (가정) S5는 창 평균, S6은 정지 구간 전체 평균을 기준으로 분산을 잰다.
    백색 잡음이면 T=30초에서 잡음을 약 3% 더 뺀다. MVP에서는 받아들인다.
    """

    def __init__(
        self,
        n_cells: int,
        window_s: float = 30.0,
        rate_hz: float = 1.0,
        noise_var: np.ndarray | None = None,
        min_valid_ratio: float = 0.8,
    ) -> None:
        """창 길이 window_s(가정: 30초) × rate_hz 표본으로 초기화한다.

        창 표본 수는 round(window_s × rate_hz)다. 파이썬 round라서 .5는
        짝수 쪽으로 간다 (2.5 → 2). 2개보다 적으면 ValueError다.

        창 안 유효 표본이 ceil(min_valid_ratio × 창 길이)(가정: 0.8)보다
        적은 셀은 NaN이다.
        noise_var(셀별 Var_noise_c)의 NaN은 유한 값들의 중앙값으로 바꾼다
        (가정). 유한 값이 없거나 None이면 0을 빼고
        noise_floor_available을 False로 둔다.
        """
        self._len = int(round(window_s * rate_hz))
        if self._len < 2:
            raise ValueError(f"창은 표본 2개 이상이어야 한다: {self._len}")
        self._n_cells = n_cells
        self._buf = np.full((self._len, n_cells, 2), np.nan)
        self._pos = 0
        self._filled = 0
        noise = (
            np.full(n_cells, np.nan) if noise_var is None
            else np.array(noise_var, dtype=np.float64)
        )
        if noise.shape != (n_cells,):
            raise ValueError(
                f"noise_var 모양은 ({n_cells},)여야 한다: {noise.shape}"
            )
        finite = np.isfinite(noise)
        self.noise_floor_available = bool(finite.any())
        fill = np.median(noise[finite]) if finite.any() else 0.0
        noise[~finite] = fill
        self._noise = noise
        self._min_valid = int(np.ceil(min_valid_ratio * self._len))

    def update(self, mean_v: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """새 V_c (n_cells, 2)를 넣고 (S_c, 잡음 빼기 전 분산)을 낸다.

        단위는 m²/s²다. 한 성분이라도 NaN·inf인 V_c는 빠진 표본이다.
        창이 다 차기 전이거나 유효 표본이 부족한 셀은 NaN이다.
        """
        mean_v = np.asarray(mean_v, dtype=np.float64)
        if mean_v.shape != (self._n_cells, 2):
            raise ValueError(
                f"mean_v 모양은 ({self._n_cells}, 2)여야 한다: {mean_v.shape}"
            )
        ok = np.isfinite(mean_v).all(axis=1)  # 두 성분 모두 유한해야 표본
        self._buf[self._pos] = np.where(ok[:, None], mean_v, np.nan)
        self._pos = (self._pos + 1) % self._len
        self._filled = min(self._filled + 1, self._len)
        if self._filled < self._len:
            empty = np.full(mean_v.shape[0], np.nan)
            return empty, empty.copy()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", category=RuntimeWarning)  # 빈 셀
            u = np.nanmean(self._buf, axis=0)  # U_c
            raw = np.nanmean(((self._buf - u) ** 2).sum(axis=2), axis=0)
        valid = np.isfinite(self._buf[..., 0]).sum(axis=0) >= self._min_valid
        raw[~valid] = np.nan
        s = np.maximum(raw - self._noise, 0.0)
        return s, raw
