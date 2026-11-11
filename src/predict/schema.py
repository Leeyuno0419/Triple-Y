"""timeline.json 규격 v0.2의 파이썬 표현.

기준 문서: docs/timeline-spec.md (확정 v0.2, 11-11).
규격이 바뀌면 이 파일과 web/src/types/timeline.ts, web/src/lib/validate.ts 를 함께 수정한다.

파일 구조::

    {
      "schema_version": "0.2",
      "meta":   {zone_id, camera_id, video_id, duration_s, interval_s, cell_size_m,
                 models, prediction, cells: [{cell_id, row, col, walkable_area_m2, image_polygon}]},
      "frames": [{t, inflow_ratio, count, cells: [{cell_id, density, vx, vy, speed_var, pressure,
                                                    counterflow, density_pred_60s}]}]
    }

- 파일 1개 = 영상 1개 = 구역 1개 = 카메라 1대. 분석 간격은 1초.
- 값이 없으면 ``None``(JSON ``null``)이다. 0은 실제로 측정한 0일 때만 쓴다.
- 셀·구역 집계값만 담는다. 머리 좌표·픽셀별 흐름·등급·알림은 담지 않는다.

v0.1 → v0.2: ``frames[].count``(구역 인원, 명)와 ``frames[].cells[].counterflow``(역방향 비율, 0~1) 추가.
추가만 했으므로 v0.1 파일도 읽는다. 읽을 때 없는 두 필드는 ``None`` 으로 채우고 버전은 v0.2 로 올려 담는다
(아직 만들지 않은 값은 null 이라는 규격 5절과 같다). v0.2 파일은 두 필드를 반드시 담아야 하고, 값만 null 이어도 된다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

SCHEMA_VERSION: str = "0.2"
SCHEMA_MAJOR: str = SCHEMA_VERSION.split(".")[0]
# count, counterflow 필드가 들어온 버전. 이 버전부터 두 필드는 필수(값은 null 가능)이고, 그 전(v0.1)에는 없어도 된다.
_V02_MINOR: int = 2

# 저장 시 소수 자리수 (spec 4절 표)
_DIGITS: Dict[str, int] = {
    "density": 2,
    "vx": 2,
    "vy": 2,
    "speed_var": 4,
    "pressure": 4,
    "counterflow": 4,
    "density_pred_60s": 2,
    "count": 2,
}

_CELL_ID_RE = re.compile(r"^c-(\d{2})(\d{2})$")

Point = Tuple[float, float]


# --------------------------------------------------------------------------- #
# meta
# --------------------------------------------------------------------------- #
@dataclass
class Models:
    """사용한 모델·방법 이름."""

    counter: str  # 예: "p2pnet-vgg16"
    flow: str  # 예: "farneback"
    predictor: str  # 예: "persistence"


@dataclass
class Prediction:
    """예측 입력 기간과 예측 시점(초)."""

    history_s: int  # 30
    horizon_s: int  # 60


@dataclass
class CellMeta:
    """셀 고정 정보."""

    cell_id: str  # "c-{행 2자리}{열 2자리}"
    row: int  # 0부터
    col: int  # 0부터
    walkable_area_m2: float  # 보행 가능 면적(㎡). 0인 셀은 목록에서 뺀다
    image_polygon: List[Point]  # 영상 가로·세로로 나눈 0~1 좌표 4개


@dataclass
class Meta:
    """파일당 1번 나오는 고정 정보."""

    zone_id: str
    camera_id: str
    video_id: str
    duration_s: int  # frames 개수와 같다
    interval_s: int  # MVP 에서는 1
    cell_size_m: float  # 기본 2
    models: Models
    prediction: Prediction
    cells: List[CellMeta] = field(default_factory=list)


# --------------------------------------------------------------------------- #
# frames
# --------------------------------------------------------------------------- #
@dataclass
class CellState:
    """1초 시점의 셀 상태."""

    cell_id: str
    density: float  # ρ, 명/㎡  [이유노]
    vx: Optional[float] = None  # V, m/s  [조영준]
    vy: Optional[float] = None
    speed_var: Optional[float] = None  # Var(v), m²/s²  [조영준]
    pressure: Optional[float] = None  # P = ρ × Var(v), 1/s²  [조영준]
    density_pred_60s: Optional[float] = None  # ρ(t+60), 명/㎡  [나예린]
    # v0.2. 위치 인자로 CellState(...)를 만드는 기존 코드가 깨지지 않게 맨 뒤에 둔다 (JSON 순서는 timeline_to_dict 가 규격대로 정한다)
    counterflow: Optional[float] = None  # B, 0~1. 셀 평균 흐름과 반대로 움직이는 픽셀 비율  [조영준]


@dataclass
class Frame:
    """1초에 1개."""

    t: int  # 영상 시작 뒤 경과 시간(초). 0부터 빠짐없이 증가
    cells: List[CellState]  # meta.cells 와 같은 순서, 모든 셀
    inflow_ratio: Optional[float] = None  # 0~1, 구역 전체 값  [조영준]
    count: Optional[float] = None  # v0.2. 구역 인원(명) = 셀 인원의 합. 5장 평균이라 소수  [이유노]


@dataclass
class Timeline:
    """timeline.json 최상위."""

    meta: Meta
    frames: List[Frame] = field(default_factory=list)
    schema_version: str = SCHEMA_VERSION


# --------------------------------------------------------------------------- #
# dict -> dataclass
# --------------------------------------------------------------------------- #
def _num(v: Any) -> Optional[float]:
    """숫자 또는 None 을 float/None 으로 바꾼다."""
    return None if v is None else float(v)


def timeline_from_dict(data: Dict[str, Any]) -> Timeline:
    """JSON 에서 읽은 dict 를 검증한 뒤 Timeline 으로 바꾼다. 어긋나면 ValueError."""
    validate_timeline(data)
    m = data["meta"]
    meta = Meta(
        zone_id=m["zone_id"],
        camera_id=m["camera_id"],
        video_id=m["video_id"],
        duration_s=int(m["duration_s"]),
        interval_s=int(m["interval_s"]),
        cell_size_m=float(m["cell_size_m"]),
        models=Models(**m["models"]),
        prediction=Prediction(**m["prediction"]),
        cells=[
            CellMeta(
                cell_id=c["cell_id"],
                row=int(c["row"]),
                col=int(c["col"]),
                walkable_area_m2=float(c["walkable_area_m2"]),
                image_polygon=[(float(x), float(y)) for x, y in c["image_polygon"]],
            )
            for c in m["cells"]
        ],
    )
    frames = [
        Frame(
            t=int(fr["t"]),
            inflow_ratio=_num(fr.get("inflow_ratio")),
            count=_num(fr.get("count")),  # v0.1 파일에는 없다 -> None
            cells=[
                CellState(
                    cell_id=c["cell_id"],
                    density=float(c["density"]),
                    vx=_num(c.get("vx")),
                    vy=_num(c.get("vy")),
                    speed_var=_num(c.get("speed_var")),
                    pressure=_num(c.get("pressure")),
                    density_pred_60s=_num(c.get("density_pred_60s")),
                    counterflow=_num(c.get("counterflow")),  # v0.1 파일에는 없다 -> None
                )
                for c in fr["cells"]
            ],
        )
        for fr in data["frames"]
    ]
    # v0.1 파일은 빠진 두 필드를 None 으로 채웠으므로 현재 버전(v0.2)으로 올려 담는다. 저장하면 규격을 지킨 v0.2 파일이 된다.
    return Timeline(meta=meta, frames=frames, schema_version=SCHEMA_VERSION)


# --------------------------------------------------------------------------- #
# dataclass -> dict
# --------------------------------------------------------------------------- #
def _round(name: str, v: Optional[float]) -> Optional[float]:
    """필드별 소수 자리수로 반올림한다 (None 은 그대로)."""
    return None if v is None else round(float(v), _DIGITS[name])


def timeline_to_dict(tl: Timeline) -> Dict[str, Any]:
    """Timeline 을 JSON 으로 저장할 dict 로 바꾼다."""
    m = tl.meta
    return {
        "schema_version": tl.schema_version,
        "meta": {
            "zone_id": m.zone_id,
            "camera_id": m.camera_id,
            "video_id": m.video_id,
            "duration_s": m.duration_s,
            "interval_s": m.interval_s,
            "cell_size_m": m.cell_size_m,
            "models": {"counter": m.models.counter, "flow": m.models.flow,
                       "predictor": m.models.predictor},
            "prediction": {"history_s": m.prediction.history_s,
                           "horizon_s": m.prediction.horizon_s},
            "cells": [
                {
                    "cell_id": c.cell_id,
                    "row": c.row,
                    "col": c.col,
                    "walkable_area_m2": c.walkable_area_m2,
                    "image_polygon": [[x, y] for x, y in c.image_polygon],
                }
                for c in m.cells
            ],
        },
        "frames": [
            {
                "t": fr.t,
                "inflow_ratio": fr.inflow_ratio,
                "count": _round("count", fr.count),
                "cells": [
                    {
                        "cell_id": c.cell_id,
                        "density": _round("density", c.density),
                        "vx": _round("vx", c.vx),
                        "vy": _round("vy", c.vy),
                        "speed_var": _round("speed_var", c.speed_var),
                        "pressure": _round("pressure", c.pressure),
                        "counterflow": _round("counterflow", c.counterflow),
                        "density_pred_60s": _round("density_pred_60s", c.density_pred_60s),
                    }
                    for c in fr.cells
                ],
            }
            for fr in tl.frames
        ],
    }


# --------------------------------------------------------------------------- #
# 검증
# --------------------------------------------------------------------------- #
_META_KEYS = ("zone_id", "camera_id", "video_id", "duration_s", "interval_s",
              "cell_size_m", "models", "prediction", "cells")
# v0.1 부터 있던 셀 필드. v0.2 의 counterflow 는 버전에 따라 필수 여부가 달라 따로 검사한다.
_CELL_KEYS = ("cell_id", "density", "vx", "vy", "speed_var", "pressure", "density_pred_60s")


def _is_num(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _schema_minor(version: Any) -> int:
    """\"0.2\" 같은 버전 문자열에서 두 번째 숫자(2)를 꺼낸다. 없거나 숫자가 아니면 0."""
    parts = str(version).split(".")
    return int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0


def validate_timeline(data: Any) -> Dict[str, Any]:
    """timeline dict 가 규격(v0.2, v0.1 파일도 허용)을 지키는지 확인한다. 어긋나면 ValueError.

    - v0.2 이상: frames[].count 와 cells[].counterflow 필드가 반드시 있어야 한다(값은 null 가능).
    - v0.1: 두 필드가 없어도 된다. 있으면 v0.2 와 같은 형식이어야 한다.
    """
    if not isinstance(data, dict) or not isinstance(data.get("meta"), dict) \
            or not isinstance(data.get("frames"), list):
        raise ValueError("timeline 형식 오류: meta(객체)와 frames(배열)가 필요합니다.")
    if str(data.get("schema_version", "")).split(".")[0] != SCHEMA_MAJOR:
        raise ValueError("지원하지 않는 schema_version: {!r}".format(data.get("schema_version")))
    require_v02 = _schema_minor(data["schema_version"]) >= _V02_MINOR

    meta = data["meta"]
    for key in _META_KEYS:
        if key not in meta:
            raise ValueError("meta.{} 가 없습니다.".format(key))
    if not isinstance(meta["cells"], list):
        raise ValueError("meta.cells 는 배열이어야 합니다.")
    if meta["duration_s"] != len(data["frames"]):
        raise ValueError("meta.duration_s({}) 와 frames 개수({}) 가 다릅니다."
                         .format(meta["duration_s"], len(data["frames"])))

    hist = meta["prediction"].get("history_s") if isinstance(meta["prediction"], dict) else None
    if not isinstance(hist, int) or isinstance(hist, bool) or hist < 1:
        raise ValueError("meta.prediction.history_s 는 1 이상의 정수여야 합니다.")
    pred_min_t = hist - 1

    ids: List[str] = []
    for c in meta["cells"]:
        cid = c.get("cell_id", "")
        mt = _CELL_ID_RE.match(cid) if isinstance(cid, str) else None
        if mt is None:
            raise ValueError("cell_id 형식 오류: {!r} (c-행2자리열2자리)".format(cid))
        if (int(mt.group(1)), int(mt.group(2))) != (c.get("row"), c.get("col")):
            raise ValueError("cell_id {} 와 row/col 이 다릅니다.".format(cid))
        if not _is_num(c.get("walkable_area_m2")) or c["walkable_area_m2"] <= 0:
            raise ValueError("{}: walkable_area_m2 는 0보다 커야 합니다 (0인 셀은 목록에서 뺌).".format(cid))
        poly = c.get("image_polygon")
        if not (isinstance(poly, list) and len(poly) == 4 and all(
                isinstance(p, list) and len(p) == 2 and all(_is_num(x) and 0 <= x <= 1 for x in p)
                for p in poly)):
            raise ValueError("{}: image_polygon 은 0~1 좌표 4개여야 합니다.".format(cid))
        ids.append(cid)
    if len(set(ids)) != len(ids):
        raise ValueError("meta.cells 에 중복 cell_id 가 있습니다.")

    for i, fr in enumerate(data["frames"]):
        if fr.get("t") != i:
            raise ValueError("frames[{}].t 는 {} 이어야 합니다 (0부터 빠짐없이 증가).".format(i, i))
        ratio = fr.get("inflow_ratio")
        if ratio is not None and not (_is_num(ratio) and 0 <= ratio <= 1):
            raise ValueError("t={}: inflow_ratio 는 0~1 또는 null 입니다.".format(i))
        if require_v02 and "count" not in fr:
            raise ValueError("t={}: count 필드가 없습니다 (v0.2 부터 필수, 아직 없으면 null).".format(i))
        count = fr.get("count")
        if count is not None and not (_is_num(count) and count >= 0):
            raise ValueError("t={}: count 는 0 이상의 숫자 또는 null 입니다.".format(i))
        cells = fr.get("cells")
        if not isinstance(cells, list) or [c.get("cell_id") for c in cells] != ids:
            raise ValueError("t={}: cells 는 meta.cells 와 같은 순서로 모든 셀을 담아야 합니다.".format(i))
        for c in cells:
            for key in _CELL_KEYS:
                if key not in c:
                    raise ValueError("t={} {}: {} 필드가 없습니다 (아직 없으면 null).".format(i, c["cell_id"], key))
            if not _is_num(c["density"]):
                raise ValueError("t={} {}: density 는 숫자여야 합니다.".format(i, c["cell_id"]))
            for key in _CELL_KEYS[2:]:
                if c[key] is not None and not _is_num(c[key]):
                    raise ValueError("t={} {}: {} 는 숫자 또는 null 입니다.".format(i, c["cell_id"], key))
            if require_v02 and "counterflow" not in c:
                raise ValueError("t={} {}: counterflow 필드가 없습니다 (v0.2 부터 필수, 아직 없으면 null)."
                                 .format(i, c["cell_id"]))
            flow_b = c.get("counterflow")
            if flow_b is not None and not (_is_num(flow_b) and 0 <= flow_b <= 1):
                raise ValueError("t={} {}: counterflow 는 0~1 또는 null 입니다.".format(i, c["cell_id"]))
            # 예측 입력이 history_s 초 미만이면(t < history_s - 1) null (spec 5절: 30초 → t < 29)
            if i < pred_min_t and c["density_pred_60s"] is not None:
                raise ValueError("t={} {}: t < {} 이면 density_pred_60s 는 null 입니다."
                                 .format(i, c["cell_id"], pred_min_t))
    return data
