"""S10 seam: timeline_flow.build_flow_cells 시험.

셀 통계 배열을 손으로 정해 넣고, timeline.json 흐름 필드가
단위 변환 없이(m/s, m²/s², 1/s², 0~1, 개) 들어가는지 숫자로 확인한다.
필드 이름은 팀 합의 전이라 FIELDS 상수로 참조한다.
"""
from __future__ import annotations

import json

import numpy as np
import pytest

from src.flow.timeline_flow import FIELDS, build_flow_cells


def _one_cell(**over: object) -> list[dict[str, object]]:
    """셀 1개짜리 기본 입력. over로 일부만 바꾼다."""
    args: dict = {
        "cell_ids": ["r03c05"],
        "mean_v": np.array([[0.412, -0.051]]),
        "instability": np.array([0.00731]),
        "pressure": np.array([0.02193]),
        "counterflow": np.array([0.042]),
        "quality": np.array([1834]),
        "min_quality": 200,
    }
    args.update(over)
    return build_flow_cells(**args)


def test_valid_cell_keeps_values_in_original_units() -> None:
    """신뢰도가 충분한 셀은 m/s·m²/s²·1/s²·비율·개 값을 그대로 담는다."""
    out = _one_cell()
    cell = out[0]
    assert cell[FIELDS["cell_id"]] == "r03c05"
    assert cell[FIELDS["vx"]] == 0.412
    assert cell[FIELDS["vy"]] == -0.051
    assert cell[FIELDS["instability"]] == 0.00731
    assert cell[FIELDS["pressure"]] == 0.02193
    assert cell[FIELDS["counterflow"]] == 0.042
    assert cell[FIELDS["quality"]] == 1834


def test_nan_in_every_flow_input_becomes_json_null() -> None:
    """신뢰도가 충분해도 NaN인 흐름 값 5개는 모두 null로 쓰인다.

    allow_nan=False로도 직렬화되고, 신뢰도(1834)는 그대로다.
    """
    nan = np.nan
    out = _one_cell(
        mean_v=np.array([[nan, nan]]),
        instability=np.array([nan]),
        pressure=np.array([nan]),
        counterflow=np.array([nan]),
    )
    cell = json.loads(json.dumps(out, allow_nan=False))[0]
    assert cell[FIELDS["vx"]] is None
    assert cell[FIELDS["vy"]] is None
    assert cell[FIELDS["instability"]] is None
    assert cell[FIELDS["pressure"]] is None
    assert cell[FIELDS["counterflow"]] is None
    assert cell[FIELDS["quality"]] == 1834


def test_infinite_value_becomes_json_null() -> None:
    """무한대 압력도 null로 쓰이고 다른 값은 남는다."""
    out = _one_cell(pressure=np.array([np.inf]))
    cell = json.loads(json.dumps(out, allow_nan=False))[0]
    assert cell[FIELDS["pressure"]] is None
    assert cell[FIELDS["instability"]] == 0.00731


def test_low_quality_cell_blanks_flow_values_but_keeps_quality() -> None:
    """유효 픽셀 150개 < 기준 200개인 셀은 흐름 값이 모두 null이다.

    셀 ID와 신뢰도(150)는 남겨 왜 비었는지 알 수 있게 한다.
    """
    out = _one_cell(quality=np.array([150]))
    cell = out[0]
    assert cell[FIELDS["cell_id"]] == "r03c05"
    assert cell[FIELDS["vx"]] is None
    assert cell[FIELDS["vy"]] is None
    assert cell[FIELDS["instability"]] is None
    assert cell[FIELDS["pressure"]] is None
    assert cell[FIELDS["counterflow"]] is None
    assert cell[FIELDS["quality"]] == 150


def test_quality_equal_to_threshold_is_kept() -> None:
    """유효 픽셀이 기준과 같은 200개면 값을 비우지 않는다."""
    out = _one_cell(quality=np.array([200]))
    assert out[0][FIELDS["vx"]] == 0.412


def test_fractional_quality_below_threshold_is_blanked() -> None:
    """신뢰도 199.9는 기준 200보다 작으므로 잘라서 비교하지 않고 비운다."""
    out = _one_cell(quality=np.array([199.9]))
    assert out[0][FIELDS["vx"]] is None


def test_output_has_one_scalar_record_per_cell_and_no_arrays() -> None:
    """셀 3개면 레코드 3개이고, 각 레코드는 스칼라 값만 담는다.

    픽셀 흐름장·좌표 같은 배열이 timeline에 새지 않는다는 뜻이다.
    """
    out = build_flow_cells(
        cell_ids=["r00c00", "r00c01", "r00c02"],
        mean_v=np.array([[1.0, 0.0], [0.0, 2.0], [0.5, 0.5]]),
        instability=np.array([0.1, 0.2, 0.3]),
        pressure=np.array([0.01, 0.02, 0.03]),
        counterflow=np.array([0.0, 0.5, 1.0]),
        quality=np.array([300, 400, 500]),
        min_quality=200,
    )
    cells = out
    assert [c[FIELDS["cell_id"]] for c in cells] == [
        "r00c00", "r00c01", "r00c02",
    ]
    assert cells[1][FIELDS["vy"]] == 2.0
    assert cells[2][FIELDS["counterflow"]] == 1.0
    for c in cells:
        assert set(c) == set(FIELDS.values())
        for v in c.values():
            assert v is None or type(v) in (str, int, float)
    json.dumps(out, allow_nan=False)



@pytest.mark.parametrize("over", [
    {"instability": np.array([0.1, 0.2])},
    {"pressure": np.array([])},
    {"counterflow": np.array([0.1, 0.2])},
    {"quality": np.array([300, 300])},
    {"mean_v": np.array([[0.1, 0.2], [0.3, 0.4]])},
    {"mean_v": np.array([[0.1, 0.2, 0.3]])},
])
def test_array_length_not_matching_cell_ids_raises(over: dict) -> None:
    """셀 1개인데 배열 길이가 다르거나 mean_v가 (1, 2)가 아니면 오류다."""
    with pytest.raises(ValueError):
        _one_cell(**over)
