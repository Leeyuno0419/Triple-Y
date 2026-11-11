"""timeline.json 읽기/쓰기.

원본 데이터(data/raw/)는 절대 덮어쓰지 않는다 — save_timeline 이 경로를 검사해 막는다.
저장 전에 validate_timeline 으로 규격 v0.2 를 지키는지 확인한다 (읽을 때는 v0.1 파일도 받아 v0.2 로 올려 담는다).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Union

from .schema import Timeline, timeline_from_dict, timeline_to_dict, validate_timeline

PathLike = Union[str, Path]


def assert_not_raw(path: PathLike) -> None:
    """경로 어디에도 'raw' 디렉터리가 'data' 아래에 끼어 있으면 쓰기를 막는다."""
    parts = [p.lower() for p in Path(path).resolve().parts]
    for i, part in enumerate(parts[:-1]):
        if part == "data" and parts[i + 1] == "raw":
            raise PermissionError("data/raw/ 는 읽기 전용이다: {}".format(path))


def load_timeline(path: PathLike) -> Timeline:
    """timeline.json 을 읽어 검증한 뒤 Timeline 으로 반환한다. 규격에 어긋나면 ValueError."""
    with open(path, "r", encoding="utf-8") as f:
        return timeline_from_dict(json.load(f))


def save_timeline(timeline: Timeline, path: PathLike) -> None:
    """Timeline 을 검증한 뒤 JSON 으로 저장한다. data/raw/ 는 PermissionError, 규격 위반은 ValueError."""
    assert_not_raw(path)
    data = timeline_to_dict(timeline)
    validate_timeline(data)
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
