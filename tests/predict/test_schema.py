import copy
import json

import numpy as np
import pytest

from src.predict.sample import make_sample_timeline
from src.predict.schema import timeline_from_dict, timeline_to_dict, validate_timeline


@pytest.fixture
def valid_dict(make_timeline):
    dens = np.full((40, 1, 2), 1.0)
    return json.loads(json.dumps(timeline_to_dict(make_timeline(dens))))


def test_roundtrip_keeps_values_and_rounds_density(make_timeline):
    dens = np.full((3, 1, 2), 1.23456)
    d = timeline_to_dict(make_timeline(dens, vx=0.2, vy=0.0))
    validate_timeline(d)
    assert d["frames"][0]["cells"][0]["density"] == 1.23            # 밀도는 소수 2자리
    tl = timeline_from_dict(json.loads(json.dumps(d)))
    assert tl.meta.cells[1].col == 1 and tl.frames[2].cells[0].vx == 0.2
    assert tl.meta.cells[0].image_polygon[0] == (0.0, 0.0)


@pytest.mark.parametrize("label, mutate", [
    ("schema_version", lambda d: d.update(schema_version="1.0")),
    ("duration_s", lambda d: d["meta"].update(duration_s=39)),
    ("t 공백", lambda d: d["frames"][3].update(t=9)),
    ("셀 순서", lambda d: d["frames"][2]["cells"].reverse()),
    ("이른 예측", lambda d: d["frames"][10]["cells"][0].update(density_pred_60s=1.0)),
    ("필드 누락", lambda d: d["frames"][0]["cells"][0].pop("vx")),
    ("유입 범위", lambda d: d["frames"][0].update(inflow_ratio=1.5)),
    ("cell_id/row", lambda d: d["meta"]["cells"][0].update(row=5)),
    ("면적 0", lambda d: d["meta"]["cells"][0].update(walkable_area_m2=0)),
    ("polygon 범위", lambda d: d["meta"]["cells"][0]["image_polygon"][0].__setitem__(0, 1.5)),
])
def test_violations_are_rejected(valid_dict, label, mutate):
    bad = copy.deepcopy(valid_dict)
    mutate(bad)
    with pytest.raises(ValueError):
        validate_timeline(bad)


def test_prediction_allowed_from_history_boundary(valid_dict):
    ok = copy.deepcopy(valid_dict)
    ok["frames"][29]["cells"][0]["density_pred_60s"] = 1.0           # t = history_s - 1 부터 허용
    validate_timeline(ok)


def test_sample_timeline_follows_spec_rules():
    tl = make_sample_timeline(duration_s=40)
    d = timeline_to_dict(tl)
    validate_timeline(d)
    empty = [c for c in d["frames"][0]["cells"] if c["density"] == 0]
    assert empty                                                      # 첫 프레임에는 빈 셀이 있다
    assert all(c["vx"] is None and c["vy"] is None and c["speed_var"] is None and c["pressure"] == 0
               for c in empty)


# --------------------------------------------------------------------------- #
# v0.2: frames[].count, cells[].counterflow (v0.1 파일은 그대로 읽는다)
# --------------------------------------------------------------------------- #
def _as_v01(d):
    """v0.2 dict 에서 새 필드를 빼고 버전을 0.1 로 되돌려 v0.1 파일을 흉내 낸다."""
    old = copy.deepcopy(d)
    old["schema_version"] = "0.1"
    for fr in old["frames"]:
        fr.pop("count", None)
        for c in fr["cells"]:
            c.pop("counterflow", None)
    return old


def test_current_version_is_v02_and_new_fields_are_written(valid_dict):
    assert valid_dict["schema_version"] == "0.2"
    assert "count" in valid_dict["frames"][0]
    assert "counterflow" in valid_dict["frames"][0]["cells"][0]
    validate_timeline(valid_dict)


def test_v01_file_is_still_readable_and_upgraded(valid_dict):
    old = _as_v01(valid_dict)
    validate_timeline(old)                                  # v0.1: 새 필드가 없어도 통과
    tl = timeline_from_dict(old)
    assert tl.schema_version == "0.2"                       # 읽으면서 v0.2 로 올려 담는다
    assert tl.frames[0].count is None and tl.frames[0].cells[0].counterflow is None
    again = timeline_to_dict(tl)
    validate_timeline(again)                                # 다시 저장해도 v0.2 규격을 지킨다
    assert "count" in again["frames"][0] and "counterflow" in again["frames"][0]["cells"][0]


@pytest.mark.parametrize("label, mutate", [
    ("count 누락", lambda d: d["frames"][0].pop("count")),
    ("counterflow 누락", lambda d: d["frames"][0]["cells"][0].pop("counterflow")),
    ("count 음수", lambda d: d["frames"][0].update(count=-1)),
    ("count 문자열", lambda d: d["frames"][0].update(count="3")),
    ("counterflow 범위", lambda d: d["frames"][0]["cells"][0].update(counterflow=1.2)),
])
def test_v02_new_fields_are_required_and_checked(valid_dict, label, mutate):
    bad = copy.deepcopy(valid_dict)
    mutate(bad)
    with pytest.raises(ValueError):
        validate_timeline(bad)


def test_v01_file_with_bad_new_field_value_is_still_rejected(valid_dict):
    old = _as_v01(valid_dict)
    old["frames"][0]["cells"][0]["counterflow"] = -0.1      # 없어도 되지만, 있으면 형식을 지켜야 한다
    with pytest.raises(ValueError):
        validate_timeline(old)


def test_count_and_counterflow_roundtrip_with_spec_digits(make_timeline):
    tl = make_timeline(np.full((3, 1, 2), 1.0))
    tl.frames[1].count = 13.8461
    tl.frames[1].cells[0].counterflow = 0.123456
    d = json.loads(json.dumps(timeline_to_dict(tl)))
    assert d["frames"][1]["count"] == 13.85                 # 구역 인원은 소수 2자리
    assert d["frames"][1]["cells"][0]["counterflow"] == 0.1235   # 역방향 비율은 소수 4자리
    back = timeline_from_dict(d)
    assert back.frames[1].count == 13.85 and back.frames[1].cells[0].counterflow == 0.1235


def test_fill_predictions_keeps_count_and_counterflow(make_timeline):
    from src.predict.config import PredictConfig
    from src.predict.model import fill_predictions, make_predictor

    tl = make_timeline(np.full((40, 1, 2), 1.0))
    tl.frames[5].count = 7.25
    tl.frames[5].cells[1].counterflow = 0.2
    out = fill_predictions(tl, make_predictor(PredictConfig(predictor="persistence")))
    assert out.frames[5].count == 7.25                      # 예측을 채워도 이유노·조영준 값은 그대로
    assert out.frames[5].cells[1].counterflow == 0.2
