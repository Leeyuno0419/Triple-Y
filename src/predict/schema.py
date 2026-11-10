"""timeline.json 규격의 파이썬 표현.

!! 가정(ASSUMPTION) !!
기획서 3.4 입출력 / timeline.json 정식 규격을 확인하지 못해 아래 구조를 임시로 가정했다.
규격이 확정되면 **이 파일과 web/src/types/timeline.ts 두 곳만** 수정하면 된다.

    {
      "schema_version": "0.1",
      "zones": [{"zone_id", "name", "bounds": {south,west,north,east},
                 "rows", "cols", "cell_size_m"}],
      "frames": [{
        "t": "2026-11-10T09:00:00+09:00",     # ISO8601
        "kind": "observed" | "predicted",
        "horizon_s": 60,                       # predicted 일 때만
        "zones": [{
          "zone_id": "Z01",
          "count": 123.0,                      # 구역 집계값(명)
          "density": [[...rows x cols...]],    # 셀 밀도(명/m²), null = 화각 밖(미관측)
          "flow": {"u": [[...]], "v": [[...]]} # 셀 흐름(셀/초), 선택
        }]
      }]
    }

좌표 규약: row 0 = 북쪽(위), col 0 = 서쪽(왼쪽).
          u > 0 → col 증가(동쪽), v > 0 → row 증가(남쪽).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import numpy as np

SCHEMA_VERSION = "0.1"
KIND_OBSERVED = "observed"
KIND_PREDICTED = "predicted"


@dataclass(frozen=True)
class Bounds:
    south: float
    west: float
    north: float
    east: float


@dataclass(frozen=True)
class ZoneMeta:
    zone_id: str
    name: str
    bounds: Bounds
    rows: int
    cols: int
    cell_size_m: float

    @property
    def cell_area_m2(self) -> float:
        return self.cell_size_m ** 2


@dataclass
class ZoneFrame:
    zone_id: str
    density: np.ndarray                   # (rows, cols) 명/m², NaN = 화각 밖
    flow_u: Optional[np.ndarray] = None   # (rows, cols) 셀/초
    flow_v: Optional[np.ndarray] = None
    count: Optional[float] = None


@dataclass
class Frame:
    t: str
    kind: str
    zones: List[ZoneFrame]
    horizon_s: Optional[float] = None


@dataclass
class Timeline:
    schema_version: str
    zones: List[ZoneMeta]
    frames: List[Frame] = field(default_factory=list)

    def zone_meta(self, zone_id: str) -> ZoneMeta:
        for z in self.zones:
            if z.zone_id == zone_id:
                return z
        raise KeyError("알 수 없는 zone_id: {}".format(zone_id))


# --------------------------------------------------------------------------- #
# 시간 유틸
# --------------------------------------------------------------------------- #
def parse_iso(t: str) -> datetime:
    # Python 3.8 의 fromisoformat 은 'Z' 접미사를 지원하지 않는다.
    return datetime.fromisoformat(t.replace("Z", "+00:00"))


def shift_iso(t: str, seconds: float) -> str:
    return (parse_iso(t) + timedelta(seconds=seconds)).isoformat()


# --------------------------------------------------------------------------- #
# dict <-> dataclass
# --------------------------------------------------------------------------- #
def _grid_from_json(grid: Any, rows: int, cols: int, name: str) -> np.ndarray:
    arr = np.array(
        [[np.nan if v is None else v for v in row] for row in grid], dtype=float
    )
    if arr.shape != (rows, cols):
        raise ValueError("{} 격자 크기 불일치: {} != {}".format(name, arr.shape, (rows, cols)))
    return arr


def _grid_to_json(arr: np.ndarray, digits: int = 4) -> List[List[Optional[float]]]:
    return [
        [None if not np.isfinite(v) else round(float(v), digits) for v in row]
        for row in arr
    ]


def timeline_from_dict(data: Dict[str, Any]) -> Timeline:
    version = str(data.get("schema_version", ""))
    if version.split(".")[0] != SCHEMA_VERSION.split(".")[0]:
        raise ValueError(
            "지원하지 않는 schema_version: {!r} (기대: {})".format(version, SCHEMA_VERSION)
        )
    zones = [
        ZoneMeta(
            zone_id=z["zone_id"],
            name=z.get("name", z["zone_id"]),
            bounds=Bounds(**z["bounds"]),
            rows=int(z["rows"]),
            cols=int(z["cols"]),
            cell_size_m=float(z["cell_size_m"]),
        )
        for z in data["zones"]
    ]
    by_id = {z.zone_id: z for z in zones}

    frames: List[Frame] = []
    for fr in data.get("frames", []):
        zframes: List[ZoneFrame] = []
        for zf in fr["zones"]:
            meta = by_id[zf["zone_id"]]
            flow = zf.get("flow")
            zframes.append(
                ZoneFrame(
                    zone_id=zf["zone_id"],
                    density=_grid_from_json(zf["density"], meta.rows, meta.cols, "density"),
                    flow_u=_grid_from_json(flow["u"], meta.rows, meta.cols, "flow.u") if flow else None,
                    flow_v=_grid_from_json(flow["v"], meta.rows, meta.cols, "flow.v") if flow else None,
                    count=zf.get("count"),
                )
            )
        frames.append(
            Frame(t=fr["t"], kind=fr.get("kind", KIND_OBSERVED), zones=zframes,
                  horizon_s=fr.get("horizon_s"))
        )
    return Timeline(schema_version=version, zones=zones, frames=frames)


def timeline_to_dict(tl: Timeline) -> Dict[str, Any]:
    def zone_to_dict(z: ZoneMeta) -> Dict[str, Any]:
        return {
            "zone_id": z.zone_id,
            "name": z.name,
            "bounds": {"south": z.bounds.south, "west": z.bounds.west,
                       "north": z.bounds.north, "east": z.bounds.east},
            "rows": z.rows,
            "cols": z.cols,
            "cell_size_m": z.cell_size_m,
        }

    def zframe_to_dict(zf: ZoneFrame) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "zone_id": zf.zone_id,
            "count": None if zf.count is None else round(float(zf.count), 2),
            "density": _grid_to_json(zf.density),
        }
        if zf.flow_u is not None and zf.flow_v is not None:
            out["flow"] = {"u": _grid_to_json(zf.flow_u), "v": _grid_to_json(zf.flow_v)}
        return out

    frames = []
    for fr in tl.frames:
        d: Dict[str, Any] = {"t": fr.t, "kind": fr.kind,
                             "zones": [zframe_to_dict(z) for z in fr.zones]}
        if fr.horizon_s is not None:
            d["horizon_s"] = fr.horizon_s
        frames.append(d)
    return {"schema_version": tl.schema_version,
            "zones": [zone_to_dict(z) for z in tl.zones],
            "frames": frames}
