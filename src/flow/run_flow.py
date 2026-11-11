"""영상 1개를 1Hz로 분석해 흐름 타임라인 파일을 쓴다.

흐름장(픽셀 단위)은 메모리 안에서 셀 통계로 바로 줄이고 버린다.
출력 파일에는 구역·카메라 ID와 셀 집계값만 담는다 (CLAUDE.md).
"""
from __future__ import annotations

import json
import math
import os
from pathlib import Path

import cv2
import numpy as np

from src.flow.cells import TemporalInstability, reduce_to_cells
from src.flow.estimators import FlowEstimator
from src.flow.ground import ground_velocity
from src.flow.timeline_flow import build_flow_cells


def analyze_video(
    video_path: Path,
    out_path: Path,
    estimator: FlowEstimator,
    cell_index: np.ndarray,
    cell_names: list[str],
    h_vel: np.ndarray,
    zone_id: str,
    camera_id: str,
    gap_frames: int = 1,
    rho_series: np.ndarray | None = None,
    noise_var: np.ndarray | None = None,
    window_s: float = 30.0,
    min_quality: int = 200,
) -> dict[str, object]:
    """초마다 (t초 프레임, t초 + gap 프레임) 쌍의 흐름을 셀 레코드로 줄여 쓴다.

    cell_index는 픽셀별 셀 번호 (H, W) int이며 -1은 버리는 픽셀이다.
    모양이 프레임 (H, W)와 다르면 ValueError다.
    h_vel은 영상 px → 지면 m 호모그래피다. 프레임은 순차로 읽는다.
    gap_frames는 정수(bool 제외)이고 1 ≤ gap < floor(fps)다.
    rho_series는 counting 출력 (T, n_cells) 셀 밀도 [1/m²]다.
    압력 P_c = rho_c × S_c이며, rho_series가 None이거나 t초 행이 없거나
    값이 NaN이면 그 셀 압력은 null이다 (가정).
    역방향 비율은 reduce_to_cells 기본 min_speed(0.05 m/s, 가정)를 쓴다.
    타임라인 dict를 out_path에 JSON(allow_nan=False)으로 쓰고 돌려준다.
    출력 폴더가 없으면 만들고, 같은 폴더의 임시 파일을 바꿔치기해
    중간에 멈춰도 반쯤 쓴 파일이 남지 않게 한다.
    """
    n_cells = len(cell_names)
    if isinstance(gap_frames, bool) or not isinstance(gap_frames, int):
        raise ValueError(f"gap_frames는 정수여야 한다: {gap_frames!r}")
    if rho_series is not None:
        rho_series = np.asarray(rho_series, dtype=np.float64)
        if rho_series.ndim != 2 or rho_series.shape[1] != n_cells:
            raise ValueError(
                f"rho_series 모양은 (T, {n_cells})여야 한다: "
                f"{rho_series.shape}"
            )
    cap = cv2.VideoCapture(str(video_path))
    try:
        if not cap.isOpened():
            raise ValueError(f"영상을 열 수 없다: {video_path}")
        fps = cap.get(cv2.CAP_PROP_FPS)
        if not (math.isfinite(fps) and fps > 0):
            raise ValueError(f"영상 fps가 올바르지 않다: {fps}")
        if not 1 <= gap_frames < math.floor(fps):
            raise ValueError(
                f"gap_frames는 1 이상, floor(fps)={math.floor(fps)} "
                f"미만이어야 한다: {gap_frames}"
            )
        seconds = _analyze_frames(
            cap, fps, estimator, cell_index, cell_names, h_vel, gap_frames,
            rho_series, noise_var, window_s, min_quality,
        )
    finally:
        cap.release()

    timeline: dict[str, object] = {
        "zone_id": zone_id,
        "camera_id": camera_id,
        "rate_hz": 1,
        "flow_estimator": estimator.name,
        "seconds": seconds,
    }
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_path.with_name(out_path.name + ".tmp")
    tmp.write_text(
        json.dumps(timeline, ensure_ascii=False, allow_nan=False),
        encoding="utf-8",
    )
    os.replace(tmp, out_path)
    return timeline


def _analyze_frames(
    cap: cv2.VideoCapture,
    fps: float,
    estimator: FlowEstimator,
    cell_index: np.ndarray,
    cell_names: list[str],
    h_vel: np.ndarray,
    gap_frames: int,
    rho_series: np.ndarray | None,
    noise_var: np.ndarray | None,
    window_s: float,
    min_quality: int,
) -> list[dict[str, object]]:
    """프레임을 순차로 넘기며 초마다 셀 레코드 묶음을 만든다.

    모든 프레임은 grab()으로 넘기고, 쓰는 프레임만 retrieve()로 푼다.
    """
    n_cells = len(cell_names)
    mask = cell_index >= 0
    ids = cell_index[mask]  # np.nonzero(mask)와 같은 행 우선 순서
    tracker = TemporalInstability(
        n_cells, window_s=window_s, noise_var=noise_var,
    )
    seconds: list[dict[str, object]] = []
    t, start, frame_no, prev = 0, 0, -1, None
    while cap.grab():
        frame_no += 1
        if frame_no == start:
            ok, prev = cap.retrieve()
            if ok and prev.shape[:2] != cell_index.shape:
                raise ValueError(
                    f"cell_index 모양 {cell_index.shape}이 프레임 "
                    f"{prev.shape[:2]}과 다르다"
                )
        elif frame_no == start + gap_frames and prev is not None:
            ok, frame = cap.retrieve()
            if not ok:
                break
            flow = estimator.estimate(prev, frame)
            vel = ground_velocity(flow, h_vel, gap_frames / fps, mask)
            del flow  # 흐름장은 여기서 버린다
            cf = reduce_to_cells(ids, vel, n_cells)
            s, _ = tracker.update(cf.mean_v)
            if rho_series is None or t >= len(rho_series):
                pressure = np.full(n_cells, np.nan)
            else:
                pressure = rho_series[t] * s
            cells = build_flow_cells(
                cell_names, cf.mean_v, s, pressure, cf.counterflow,
                cf.count, min_quality,
            )
            seconds.append({"t": t, "cells": cells})
            t += 1
            start, prev = int(round(t * fps)), None
    return seconds
