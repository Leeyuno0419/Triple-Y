"""셀 흐름 통계를 timeline.json 프레임 셀 레코드에 채운다.

기준은 docs/timeline-spec.md v0.1이다. 인원 추정 모듈이 만든 프레임
셀 레코드(cell_id·density·density_pred_60s 등)를 받아 흐름 필드
vx·vy(m/s)·speed_var(m²/s²)·pressure(1/s²)만 채운다.
역류 비율·신뢰도는 파일에 쓰지 않는다. 신뢰도는 낮은 셀을 비우는 데만
쓴다. 셀·구역 집계값만 담고 픽셀 흐름장·좌표는 담지 않는다.
"""
from __future__ import annotations

import math
import numbers

import numpy as np


def fill_flow_fields(
    frame_cells: list[dict],
    mean_v: np.ndarray,
    speed_var: np.ndarray,
    quality: np.ndarray,
    min_quality: int,
) -> list[dict]:
    """한 프레임의 셀 레코드에 흐름 필드를 채운 새 레코드 목록을 만든다.

    frame_cells는 meta.cells와 같은 순서라 i번째 레코드가 배열의 i번째
    값과 짝이다. mean_v는 (n, 2) 셀 평균 지면 속도 [m/s], speed_var는
    (n,) 속도 분산 [m²/s²], quality는 (n,) 유효 표본(머리) 수다. 리스트도
    받는다.
    vx·vy는 소수 2자리, speed_var·pressure는 4자리로 round()한다
    (정확히 반이면 짝수 쪽: 0.125 → 0.12). -0.0은 0.0으로 쓰고, 음수
    분산은 0으로 자른다. pressure는 저장값으로 계산한다:
    round(round(density, 2) × 저장된 speed_var, 4). 그래서 파일을 읽는
    쪽이 ρ×Var를 다시 계산해도 같은 값이 나온다 (4.3 × 0.006 = 0.0258).
    소수 2자리 density가 0이면 사람이 없는 셀이라 vx·vy·speed_var는
    None, pressure는 0이다. 유효 표본 수가 min_quality보다 적으면
    vx·vy·speed_var·pressure가 None이다. NaN·무한대는 필드별로 None이다:
    속도는 (vx, vy) 한 벡터라 한 성분이라도 유한하지 않으면 둘 다 None,
    speed_var가 유한하지 않으면 speed_var와 pressure가 None이다
    (불안정 창이 덜 찬 첫 구간에도 속도는 쓴다).
    입력 레코드는 바꾸지 않고, 다른 키는 그대로 복사한다.
    density가 0 이상 유한한 숫자가 아니거나 배열 모양이 셀 수와 맞지
    않으면 ValueError를 낸다.
    """
    n = len(frame_cells)
    mean_v = np.asarray(mean_v, dtype=float)
    speed_var = np.asarray(speed_var, dtype=float)
    quality = np.asarray(quality)
    if (
        mean_v.shape != (n, 2)
        or speed_var.shape != (n,)
        or quality.shape != (n,)
    ):
        raise ValueError("셀 배열 모양이 frame_cells 수와 맞지 않다")
    out = []
    for i, cell in enumerate(frame_cells):
        new = dict(cell)
        density = cell["density"]
        if not (
            isinstance(density, numbers.Real)
            and math.isfinite(density) and density >= 0
        ):
            raise ValueError(f"density가 0 이상 숫자가 아니다: {density!r}")
        rho = round(float(density), 2)
        if rho == 0:
            new.update(vx=None, vy=None, speed_var=None, pressure=0)
            out.append(new)
            continue
        new.update(vx=None, vy=None, speed_var=None, pressure=None)
        if quality[i] < min_quality:
            out.append(new)
            continue
        vx, vy = float(mean_v[i, 0]), float(mean_v[i, 1])
        sv = float(speed_var[i])
        if math.isfinite(vx) and math.isfinite(vy):
            # + 0.0은 반올림으로 생긴 -0.0을 0.0으로 바꾼다
            new["vx"] = round(vx, 2) + 0.0
            new["vy"] = round(vy, 2) + 0.0
        if math.isfinite(sv):
            new["speed_var"] = round(max(sv, 0.0), 4)
            new["pressure"] = round(rho * new["speed_var"], 4)
        out.append(new)
    return out
