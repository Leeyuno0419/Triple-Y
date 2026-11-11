"""timeline.json 읽기/쓰기와 예측 프레임 병합.

원본 데이터(data/raw/)는 절대 덮어쓰지 않는다 — save_timeline 이 경로를 검사해 막는다.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional, Sequence, Union

from .model import BasePredictor
from .schema import (
    KIND_OBSERVED,
    KIND_PREDICTED,
    Frame,
    Timeline,
    ZoneFrame,
    shift_iso,
    timeline_from_dict,
    timeline_to_dict,
)

PathLike = Union[str, Path]


def assert_not_raw(path: PathLike) -> None:
    """경로 어디에도 'raw' 디렉터리가 'data' 아래에 끼어 있으면 쓰기를 막는다."""
    parts = [p.lower() for p in Path(path).resolve().parts]
    for i, part in enumerate(parts[:-1]):
        if part == "data" and parts[i + 1] == "raw":
            raise PermissionError("data/raw/ 는 읽기 전용이다: {}".format(path))


def load_timeline(path: PathLike) -> Timeline:
    with open(path, "r", encoding="utf-8") as f:
        return timeline_from_dict(json.load(f))


def save_timeline(timeline: Timeline, path: PathLike) -> None:
    assert_not_raw(path)
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(timeline_to_dict(timeline), f, ensure_ascii=False, indent=2)


def append_predictions(
    timeline: Timeline,
    predictor: BasePredictor,
    horizons_s: Sequence[float],
    base_frame_index: Optional[int] = None,
) -> Timeline:
    """마지막(또는 지정한) 관측 프레임에서 예측한 프레임들을 timeline 뒤에 붙여 반환한다.

    입력 timeline 은 변경하지 않는다. 기존 predicted 프레임은 제거 후 새로 만든다.
    """
    observed = [f for f in timeline.frames if f.kind == KIND_OBSERVED]
    if not observed:
        raise ValueError("관측(observed) 프레임이 없다")
    base = observed[base_frame_index] if base_frame_index is not None else observed[-1]

    per_horizon = {}  # horizon_s -> List[ZoneFrame]
    for zf in base.zones:
        meta = timeline.zone_meta(zf.zone_id)
        for pred in predictor.predict(meta, zf, horizons_s):
            per_horizon.setdefault(pred.horizon_s, []).append(
                ZoneFrame(zone_id=pred.zone_id, density=pred.density, count=pred.count)
            )

    new_frames = [
        Frame(t=shift_iso(base.t, h), kind=KIND_PREDICTED, horizon_s=h, zones=zones)
        for h, zones in sorted(per_horizon.items())
    ]
    return Timeline(
        schema_version=timeline.schema_version,
        zones=timeline.zones,
        frames=observed + new_frames,
    )
