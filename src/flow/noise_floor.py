"""정지 구간의 셀 평균 속도 시계열로 셀별 잡음 분산을 잰다 (중간 1, 난류 조사 V2)."""
from __future__ import annotations

import warnings

import numpy as np


def measure_noise_floor(
    mean_v_series: np.ndarray,
    static_mask: np.ndarray,
    min_samples: int = 30,
) -> np.ndarray:
    """정지 표시 표본만으로 셀별 잡음 분산 Var_noise_c [m²/s²]를 낸다.

    mean_v_series는 (T, n_cells, 2) V_c 시계열 [m/s], static_mask는
    (T, n_cells) 정지 표시다. 분산은 두 성분 합 <|V_c − U_c|²>이다.
    두 성분이 모두 유한한 정지 표본만 쓰고, 그 수가 min_samples(가정)보다
    적은 셀은 NaN이다.

    (가정) U_c는 정지 구간 전체 평균이다. S5는 T초 이동 창 평균을 쓰므로
    백색 잡음이면 S5의 잡음 항은 σ²(T−1)/T이다. 그래서 이 값을 빼면
    T=30에서 약 3% 과보정된다. MVP에서는 받아들인다.
    """
    if mean_v_series.ndim != 3 or mean_v_series.shape[2] != 2:
        raise ValueError("mean_v_series는 (T, n_cells, 2)여야 한다")
    if static_mask.shape != mean_v_series.shape[:2]:
        raise ValueError("static_mask는 (T, n_cells)여야 한다")
    ok = static_mask & np.isfinite(mean_v_series).all(axis=2)
    v = np.where(ok[..., None], mean_v_series, np.nan)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=RuntimeWarning)  # 빈 셀
        u = np.nanmean(v, axis=0)
        var = np.nanmean(((v - u) ** 2).sum(axis=2), axis=0)
    n = ok.sum(axis=0)
    var[n < min_samples] = np.nan
    return var
