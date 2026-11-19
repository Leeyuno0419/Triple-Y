"""compare_flow.timeline_proxies 시험 (손으로 만든 timeline dict).

판정 셀(walkable_area_m2 ≥ 2) 2개와 작은 셀(1 m²) 1개를 둔다.
기대값은 셀 값에서 손으로 센다.
"""
from __future__ import annotations

from src.flow.compare_flow import timeline_proxies


def _cell(cid: str, density: float, vx: float | None, vy: float | None,
          pressure: float | None) -> dict:
    """timeline 셀 하나 (판정에 안 쓰는 키는 null)."""
    return {"cell_id": cid, "density": density, "vx": vx, "vy": vy,
            "speed_var": None, "pressure": pressure}


def _timeline(frames: list[list[dict]]) -> dict:
    """셀 a·b(4 m²), s(1 m²)를 둔 timeline."""
    cells = [{"cell_id": "a", "walkable_area_m2": 4.0},
             {"cell_id": "b", "walkable_area_m2": 4.0},
             {"cell_id": "s", "walkable_area_m2": 1.0}]
    return {"meta": {"cells": cells},
            "frames": [{"t": t, "cells": c} for t, c in enumerate(frames)]}


def test_timeline_proxies_counts_only_judged_cells() -> None:
    """판정 셀만 세고, vx null 셀은 모든 지표에서 빠진다.

    t=0: a 속력 3.5(ρ 0.6, 머리 2.4, P 0.03), b 속력 1.0(ρ 0.6, P 0.01),
         s 속력 4.0(작은 셀).
    t=1: a 속력 1.4(ρ 0.6, P null), b vx null(P 0.9), s 속력 1.0.
    over3: a의 3.5 하나 → 1. 움직이는 셀(머리 ≥ 2, 속력 ≥ 0.3):
    3.5·1.0·1.4 → 중앙 1.4. P > 0.02: 0.03 하나 → 1.
    """
    tl = _timeline([
        [_cell("a", 0.6, 3.5, 0.0, 0.03), _cell("b", 0.6, 0.6, 0.8, 0.01),
         _cell("s", 2.0, 4.0, 0.0, 0.5)],
        [_cell("a", 0.6, 0.0, 1.4, None), _cell("b", 0.2, None, None, 0.9),
         _cell("s", 2.0, 1.0, 0.0, 0.0)],
    ])
    out = timeline_proxies(tl)
    assert out["over3_ms"] == 1
    assert abs(out["moving_speed_median"] - 1.4) < 1e-9
    assert out["p_over_002"] == 1


def test_moving_speed_median_is_none_without_moving_cells() -> None:
    """움직이는 판정 셀이 없으면 moving_speed_median은 None이다."""
    tl = _timeline([[_cell("a", 0.2, 1.0, 0.0, 0.0),
                     _cell("b", 0.6, 0.1, 0.0, 0.0),
                     _cell("s", 2.0, 1.0, 0.0, 0.0)]])
    out = timeline_proxies(tl)
    assert out["moving_speed_median"] is None
    assert out["over3_ms"] == 0 and out["p_over_002"] == 0
