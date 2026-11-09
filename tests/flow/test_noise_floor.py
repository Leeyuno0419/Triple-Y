"""S6 seam: noise_floor.measure_noise_floor 시험.

셀 평균 속도 V_c 시계열과 정지 표시를 손으로 정해 넣고,
셀별 잡음 분산 Var_noise_c = <|V_c − U_c|²> [m²/s²]를 손으로 계산한 값과
비교한다. 기대값은 코드와 같은 식으로 다시 계산하지 않고 숫자로 적는다.
"""
from __future__ import annotations

import warnings

import numpy as np
import pytest

from src.flow.noise_floor import measure_noise_floor


def test_uses_only_samples_marked_static() -> None:
    """정지 표본 (1,0)·(3,0)만 쓰면 평균 (2,0), 분산 (1+1)/2 = 1이다.

    정지가 아닌 (100,0)이 섞이면 분산이 커지므로 빠졌는지 드러난다.
    """
    series = np.array([[[1.0, 0.0]], [[100.0, 0.0]], [[3.0, 0.0]]])
    static = np.array([[True], [False], [True]])
    var = measure_noise_floor(series, static, min_samples=2)
    np.testing.assert_allclose(var, [1.0])


def test_cell_with_fewer_than_min_samples_is_nan() -> None:
    """min_samples=3에서 정지 표본 3개인 셀 0만 값을 갖는다.

    셀 0: (0,0)·(3,0)·(0,0) → 평균 (1,0), 분산 (1+4+1)/3 = 2.
    셀 1은 정지 표본 2개, 셀 2는 0개라 둘 다 NaN이다.
    정지 표본이 없는 셀에서 RuntimeWarning이 나오면 안 된다.
    """
    series = np.array([
        [[0.0, 0.0], [1.0, 1.0], [7.0, 7.0]],
        [[3.0, 0.0], [2.0, 2.0], [7.0, 7.0]],
        [[0.0, 0.0], [9.0, 9.0], [7.0, 7.0]],
    ])
    static = np.array([
        [True, True, False],
        [True, True, False],
        [True, False, False],
    ])
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        var = measure_noise_floor(series, static, min_samples=3)
    np.testing.assert_allclose(var, [2.0, np.nan, np.nan])


def test_nan_samples_are_ignored_and_not_counted() -> None:
    """정지 표시라도 NaN(빈 셀) 표본은 평균·분산·표본 수에서 빠진다.

    유효 표본 (0,0)·(0,2) → 평균 (0,1), y 성분만으로 분산 (1+1)/2 = 1.
    유효 표본이 2개뿐이라 min_samples=3이면 NaN이다.
    """
    series = np.array([
        [[0.0, 0.0]], [[np.nan, np.nan]], [[0.0, 2.0]], [[np.nan, np.nan]],
    ])
    static = np.ones((4, 1), dtype=bool)
    np.testing.assert_allclose(
        measure_noise_floor(series, static, min_samples=2), [1.0],
    )
    np.testing.assert_allclose(
        measure_noise_floor(series, static, min_samples=3), [np.nan],
    )


def test_mismatched_shapes_raise_value_error() -> None:
    """series는 (T, n, 2), mask는 (T, n)이어야 한다. 아니면 ValueError.

    (n,)·(T, 1) mask는 그대로 두면 조용히 브로드캐스트되므로 막는다.
    """
    series = np.zeros((4, 3, 2))
    for bad_mask in (np.ones(3, bool), np.ones((4, 1), bool)):
        with pytest.raises(ValueError):
            measure_noise_floor(series, bad_mask, min_samples=1)
    with pytest.raises(ValueError):
        measure_noise_floor(
            np.zeros((4, 3)), np.ones((4, 3), bool), min_samples=1,
        )


def test_sample_with_one_nan_component_is_dropped_whole() -> None:
    """두 성분이 모두 유한한 표본만 쓴다.

    표본 (0,0)·(NaN,4)·(0,2)·(5,NaN) 중 온전한 것은 (0,0)·(0,2) 2개다.
    평균 (0,1), 분산 (1+1)/2 = 1. (NaN,4)의 y를 쓰면 평균 y가 2가 되어
    분산이 2로 틀어진다. 온전한 표본이 2개라 min_samples=3이면 NaN이다.
    """
    series = np.array([
        [[0.0, 0.0]], [[np.nan, 4.0]], [[0.0, 2.0]], [[5.0, np.nan]],
    ])
    static = np.ones((4, 1), dtype=bool)
    np.testing.assert_allclose(
        measure_noise_floor(series, static, min_samples=2), [1.0],
    )
    np.testing.assert_allclose(
        measure_noise_floor(series, static, min_samples=3), [np.nan],
    )
