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
