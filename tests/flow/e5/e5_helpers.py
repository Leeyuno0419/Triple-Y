"""tests/flow/e5 공용 합성 자료 도우미 (시험용, 실제 원본 자료 없음).

합성 timeline(규격 v0.2 모양)과 실행기 CSV 4개를 만든다. 실행기 CSV
머리줄은 Java E5Sweep 머리줄 상수와 같은 문자열을 직접 적는다(계획 9.1절의 약속).
"""
from __future__ import annotations

import csv
from collections.abc import Sequence
from pathlib import Path

TICKS_HEADER = ("t,zone_grade,max_density,inflow_avg,inflow_alert,"
                "n_unstable,unstable_cells,events")
ALERTS_HEADER = "t,reason,level,value,cell_ids"
SUMMARY_HEADER = ("n_instability,n_grade_up,n_inflow,first_instability_t,"
                  "first_grade_up_t,first_inflow_t,unstable_s,critical_s,"
                  "inflow_on_s")
INSTABILITY_HEADER = "pressure,seconds,is_default," + SUMMARY_HEADER
INFLOW_HEADER = ("ratio,window_seconds,min_samples,min_count,off_seconds,"
                 "is_default," + SUMMARY_HEADER)


def make_timeline(
    areas: Sequence[float],
    density: Sequence[Sequence[float]],
    pressure: Sequence[Sequence[float | None]],
    inflow: Sequence[float | None],
    count: Sequence[float | None],
    vx: Sequence[Sequence[float | None]] | None = None,
    vy: Sequence[Sequence[float | None]] | None = None,
) -> dict:
    """규격 v0.2 모양의 합성 timeline.

    셀 i는 c-00{i:02d}, row 0, col i, image_polygon은 화면을 가로로
    n등분한 사각형이다. density[t][i] 등 t 우선. vx·vy가 None이면
    모두 null. speed_var·counterflow·density_pred_60s는 null이다.
    validate_timeline을 통과한다.
    """
    n = len(areas)
    cells = [
        {
            "cell_id": f"c-00{i:02d}", "row": 0, "col": i,
            "walkable_area_m2": float(areas[i]),
            "image_polygon": [[i / n, 0.0], [(i + 1) / n, 0.0],
                              [(i + 1) / n, 1.0], [i / n, 1.0]],
        }
        for i in range(n)
    ]
    frames = []
    for t in range(len(count)):
        frames.append({
            "t": t,
            "inflow_ratio": inflow[t],
            "count": count[t],
            "cells": [
                {
                    "cell_id": f"c-00{i:02d}",
                    "density": density[t][i],
                    "vx": None if vx is None else vx[t][i],
                    "vy": None if vy is None else vy[t][i],
                    "speed_var": None,
                    "pressure": pressure[t][i],
                    "counterflow": None,
                    "density_pred_60s": None,
                }
                for i in range(n)
            ],
        })
    return {
        "schema_version": "0.2",
        "meta": {
            "zone_id": "zone-test", "camera_id": "cam-test",
            "video_id": "TEST_001", "duration_s": len(count),
            "interval_s": 1, "cell_size_m": 2.0,
            "models": {"counter": "fixture", "flow": "fixture",
                       "predictor": "none"},
            "prediction": {"history_s": 30, "horizon_s": 60},
            "cells": cells,
        },
        "frames": frames,
    }


def _write_rows(path: Path, header: str, rows: Sequence[dict]) -> None:
    """머리줄 문자열 순서로 행을 쓴다. 없는 키·None은 빈칸이다."""
    columns = header.split(",")
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(columns)
        for row in rows:
            writer.writerow(
                ["" if row.get(c) is None else row[c] for c in columns]
            )


def write_runner_csvs(
    out_dir: Path, stem: str, ticks: Sequence[dict],
    alerts: Sequence[dict], instability: Sequence[dict],
    inflow: Sequence[dict],
) -> None:
    """실행기 CSV 4개를 Java와 같은 머리줄(9.1절)로 쓴다 (report 시험용)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    _write_rows(out_dir / f"{stem}_ticks.csv", TICKS_HEADER, ticks)
    _write_rows(out_dir / f"{stem}_alerts.csv", ALERTS_HEADER, alerts)
    _write_rows(out_dir / f"{stem}_sweep_instability.csv",
                INSTABILITY_HEADER, instability)
    _write_rows(out_dir / f"{stem}_sweep_inflow.csv", INFLOW_HEADER, inflow)
