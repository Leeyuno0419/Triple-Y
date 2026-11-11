"""T3 테스트 경계: timeline_flow.fill_flow_fields 시험.

인원 추정 모듈이 만든 프레임 셀 레코드(cell_id·density 등)에
흐름 필드(vx, vy, speed_var, pressure)를 채우는지 확인한다.
기준은 docs/timeline-spec.md v0.1의 4절(필드·소수 자릿수)과
5절(값 규칙)이다. 기대값은 모두 손으로 계산한 숫자다.
"""
from __future__ import annotations

import json
import math

import numpy as np
import pytest

from src.flow.timeline_flow import fill_flow_fields


def _fill_one(cell: dict, **over: object) -> dict:
    """셀 1개짜리 기본 입력으로 채운 결과 레코드를 돌려준다."""
    args: dict = {
        "frame_cells": [cell],
        "mean_v": np.array([[0.2134, -0.0471]]),
        "speed_var": np.array([0.006012]),
        "quality": np.array([1834]),
        "min_quality": 200,
    }
    args.update(over)
    return fill_flow_fields(**args)[0]


def test_valid_cell_gets_rounded_flow_fields_and_keeps_other_keys() -> None:
    """사람이 있는 셀은 vx·vy 2자리, speed_var·pressure 4자리로 채운다.

    pressure는 저장값으로 계산한다: 4.3 × 0.006 = 0.0258 (규격 3절 예시).
    cell_id·density·density_pred_60s와 모르는 키는 그대로 남는다.
    """
    cell = {
        "cell_id": "c-0412",
        "density": 4.3,
        "vx": None,
        "vy": None,
        "speed_var": None,
        "pressure": None,
        "density_pred_60s": 4.6,
        "extra": "keep",
    }
    out = _fill_one(cell)
    assert out == {
        "cell_id": "c-0412",
        "density": 4.3,
        "vx": 0.21,
        "vy": -0.05,
        "speed_var": 0.006,
        "pressure": 0.0258,
        "density_pred_60s": 4.6,
        "extra": "keep",
    }


def test_pressure_uses_stored_rounded_values() -> None:
    """pressure는 파일에 저장된 density·speed_var로 계산한다.

    speed_var 0.01236 → 0.0124로 저장하고 pressure는 10 × 0.0124 = 0.124다.
    파일을 읽는 쪽이 ρ×Var를 다시 계산해도 같은 값이 나온다.
    """
    out = _fill_one(
        {"cell_id": "c-0000", "density": 10},
        speed_var=np.array([0.01236]),
    )
    assert out["speed_var"] == 0.0124
    assert out["pressure"] == 0.124


def test_empty_cell_has_zero_pressure_and_null_flow() -> None:
    """사람이 없는 셀(density 0)은 흐름 값이 있어도 비운다 (규격 5절).

    vx·vy·speed_var는 null, pressure는 실제로 잰 0이다.
    """
    out = _fill_one({"cell_id": "c-0413", "density": 0})
    assert out["vx"] is None
    assert out["vy"] is None
    assert out["speed_var"] is None
    assert out["pressure"] == 0


@pytest.mark.parametrize("density", [None, -0.1, np.nan, np.inf])
def test_invalid_density_raises(density: object) -> None:
    """density는 0 이상 유한한 숫자여야 한다 (규격 4절). 아니면 오류다."""
    with pytest.raises(ValueError):
        _fill_one({"cell_id": "c-0412", "density": density})


def test_low_quality_cell_blanks_flow_and_pressure() -> None:
    """유효 픽셀 150개 < 기준 200개면 흐름 값과 pressure가 null이다.

    신뢰도 값 자체는 파일에 쓰지 않는다.
    """
    out = _fill_one(
        {"cell_id": "c-0412", "density": 4.3},
        quality=np.array([150]),
    )
    assert out == {
        "cell_id": "c-0412",
        "density": 4.3,
        "vx": None,
        "vy": None,
        "speed_var": None,
        "pressure": None,
    }


@pytest.mark.parametrize("over, expected", [
    (
        {"mean_v": np.array([[np.nan, -0.0471]])},
        {"vx": None, "vy": None, "speed_var": 0.006, "pressure": 0.0258},
    ),
    (
        {"mean_v": np.array([[0.2134, np.nan]])},
        {"vx": None, "vy": None, "speed_var": 0.006, "pressure": 0.0258},
    ),
    (
        {"speed_var": np.array([np.inf])},
        {"vx": 0.21, "vy": -0.05, "speed_var": None, "pressure": None},
    ),
])
def test_non_finite_flow_value_nulls_only_its_own_fields(
    over: dict, expected: dict,
) -> None:
    """NaN·무한대인 값의 필드만 null이다 (규격 5절, 필드별 처리).

    속도는 (vx, vy) 한 벡터라 한 성분이라도 NaN이면 둘 다 null이다.
    speed_var가 없으면 pressure도 계산할 수 없어 null이다.
    allow_nan=False로 직렬화돼도 오류가 나지 않는다.
    """
    out = _fill_one({"cell_id": "c-0412", "density": 4.3}, **over)
    cell = json.loads(json.dumps(out, allow_nan=False))
    assert {k: cell[k] for k in expected} == expected


@pytest.mark.parametrize("over", [
    {"mean_v": np.array([[0.1, 0.2], [0.3, 0.4]])},
    {"mean_v": np.array([[0.1, 0.2, 0.3]])},
    {"speed_var": np.array([])},
    {"quality": np.array([300, 300])},
    {"speed_var": np.array([[0.006]])},
    {"quality": np.array([[1834]])},
])
def test_array_length_not_matching_cells_raises(over: dict) -> None:
    """셀 1개인데 배열 모양이 (1, 2)·(1,)·(1,)이 아니면 오류다."""
    with pytest.raises(ValueError):
        _fill_one({"cell_id": "c-0412", "density": 4.3}, **over)


def test_cells_pair_with_arrays_by_index_and_input_is_unchanged() -> None:
    """i번째 셀 레코드는 배열의 i번째 값으로 채우고 입력은 바꾸지 않는다.

    가운데 셀은 사람이 없어 비우고, 품질 기준과 같은 200개는 남긴다.
    """
    cells = [
        {"cell_id": "c-0000", "density": 1.0},
        {"cell_id": "c-0001", "density": 0},
        {"cell_id": "c-0002", "density": 2.0},
    ]
    out = fill_flow_fields(
        frame_cells=cells,
        mean_v=np.array([[1.0, 0.0], [9.0, 9.0], [0.0, -0.5]]),
        speed_var=np.array([0.1, 9.0, 0.03]),
        quality=np.array([300, 300, 200]),
        min_quality=200,
    )
    assert [c["cell_id"] for c in out] == ["c-0000", "c-0001", "c-0002"]
    assert (out[0]["vx"], out[0]["pressure"]) == (1.0, 0.1)
    assert (out[1]["vx"], out[1]["pressure"]) == (None, 0)
    assert (out[2]["vy"], out[2]["pressure"]) == (-0.5, 0.06)
    assert cells[0] == {"cell_id": "c-0000", "density": 1.0}
    json.dumps(out, allow_nan=False)


def test_rounding_is_python_round_half_to_even() -> None:
    """반올림은 파이썬 round()라 정확히 반인 0.125는 짝수 쪽 0.12다."""
    out = _fill_one(
        {"cell_id": "c-0412", "density": 4.3},
        mean_v=np.array([[0.125, 0.0]]),
    )
    assert out["vx"] == 0.12


def test_empty_cell_with_low_quality_still_has_zero_pressure() -> None:
    """사람이 없는 셀은 품질이 낮아도 pressure가 실제 측정값 0이다."""
    out = _fill_one(
        {"cell_id": "c-0413", "density": 0},
        quality=np.array([10]),
    )
    assert out["pressure"] == 0
    assert out["vx"] is None


@pytest.mark.parametrize("density", [np.float32(4.3), np.int64(4)])
def test_numpy_density_gives_json_safe_python_float_pressure(
    density: object,
) -> None:
    """density가 numpy 숫자여도 pressure는 파이썬 float라 JSON으로 쓴다.

    density 키 자체는 받은 그대로 둔다 (인원 추정 모듈 값).
    """
    out = _fill_one({"cell_id": "c-0412", "density": density})
    assert type(out["pressure"]) is float
    flow = {k: out[k] for k in ("vx", "vy", "speed_var", "pressure")}
    json.dumps(flow, allow_nan=False)


def test_density_rounding_to_zero_is_treated_as_empty_cell() -> None:
    """density 0.004는 저장하면 0.00이라 사람이 없는 셀로 다룬다."""
    out = _fill_one({"cell_id": "c-0413", "density": 0.004})
    assert out["vx"] is None
    assert out["speed_var"] is None
    assert out["pressure"] == 0


def test_tiny_negative_values_are_written_as_plain_zero() -> None:
    """-0.001 m/s나 수치 오차로 생긴 음수 분산은 -0.0이 아니라 0.0이다.

    분산은 음수일 수 없으므로 0으로 자른다. 부호는 copysign으로 본다.
    """
    out = _fill_one(
        {"cell_id": "c-0412", "density": 4.3},
        mean_v=np.array([[-0.001, -0.004]]),
        speed_var=np.array([-1e-6]),
    )
    for key in ("vx", "vy", "speed_var", "pressure"):
        assert out[key] == 0.0
        assert math.copysign(1.0, out[key]) == 1.0, key


def test_plain_lists_are_accepted_as_arrays() -> None:
    """배열 대신 파이썬 리스트를 넣어도 같은 결과다."""
    out = _fill_one(
        {"cell_id": "c-0412", "density": 4.3},
        mean_v=[[0.2134, -0.0471]],
        speed_var=[0.006012],
        quality=[1834],
    )
    assert (out["vx"], out["vy"]) == (0.21, -0.05)
    assert (out["speed_var"], out["pressure"]) == (0.006, 0.0258)


def test_nan_speed_var_keeps_velocity_and_nulls_speed_var_pressure() -> None:
    """불안정 창이 덜 찬 첫 30초는 speed_var가 NaN이다.

    값이 없는 필드만 null이다 (규격 5절). 속도는 유효하니 그대로 쓰고
    speed_var·pressure만 null이다.
    """
    out = _fill_one(
        {"cell_id": "c-0412", "density": 4.3},
        speed_var=np.array([np.nan]),
    )
    assert (out["vx"], out["vy"]) == (0.21, -0.05)
    assert out["speed_var"] is None
    assert out["pressure"] is None
