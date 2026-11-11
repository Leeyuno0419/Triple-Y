"""셀 통계를 timeline.json 흐름 필드로 바꾼다.

필드 이름은 기획 2.2 후보이며 팀 합의 전이다. 이름은 FIELDS 한 곳에서만
정해서, 합의 후 바꿀 때 이 상수만 고친다.
셀·구역 집계값만 담고 픽셀 흐름장·좌표는 담지 않는다.
"""
from __future__ import annotations

import math

import numpy as np

# 내부 키 -> timeline.json 셀 레코드 필드 이름 (합의 전 후보)
# (가정) D3 팀 결정 전 임시: flow_estimator는 셀마다 넣지 않고
# 파일 최상위에 run_flow(S11)가 한 번 쓴다.
FIELDS: dict[str, str] = {
    "cell_id": "cell_id",
    "vx": "flow_vx",                    # m/s
    "vy": "flow_vy",                    # m/s
    "instability": "flow_instability",  # m²/s²
    "pressure": "flow_pressure",        # 1/s²
    "counterflow": "flow_counterflow",  # 0~1
    "quality": "flow_quality",          # 유효 픽셀 수 (개)
}


def _num(x: float) -> float | None:
    """NaN·무한대는 None(JSON null)으로 바꾼다."""
    x = float(x)
    return x if math.isfinite(x) else None


def build_flow_cells(
    cell_ids: list[str],
    mean_v: np.ndarray,
    instability: np.ndarray,
    pressure: np.ndarray,
    counterflow: np.ndarray,
    quality: np.ndarray,
    min_quality: int,
) -> list[dict[str, object]]:
    """한 시점의 셀 흐름 레코드 목록을 만든다.

    mean_v는 (n, 2) 셀 평균 지면 속도 [m/s], 나머지는 (n,) 셀 값이다.
    단위는 바꾸지 않고 그대로 담는다. 유효 픽셀 수가 min_quality보다
    적은 셀은 흐름 값을 모두 None(null)으로 비우고 신뢰도만 남긴다.
    quality는 정수 개수(가정)이며 잘라내기 전 값으로 기준과 비교한다.
    셀 수와 배열 길이가 다르면 ValueError를 낸다.
    """
    n = len(cell_ids)
    per_cell = (instability, pressure, counterflow, quality)
    if mean_v.shape != (n, 2) or any(len(a) != n for a in per_cell):
        raise ValueError("셀 배열 길이가 cell_ids와 다르다")
    cells = []
    for i, cid in enumerate(cell_ids):
        ok = bool(quality[i] >= min_quality)
        cells.append({
            FIELDS["cell_id"]: cid,
            FIELDS["vx"]: _num(mean_v[i, 0]) if ok else None,
            FIELDS["vy"]: _num(mean_v[i, 1]) if ok else None,
            FIELDS["instability"]: _num(instability[i]) if ok else None,
            FIELDS["pressure"]: _num(pressure[i]) if ok else None,
            FIELDS["counterflow"]: _num(counterflow[i]) if ok else None,
            FIELDS["quality"]: int(quality[i]),
        })
    return cells
