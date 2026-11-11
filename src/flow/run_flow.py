"""인원 추정 타임라인에 영상 1개의 흐름 필드를 채워 다시 쓴다.

기준은 docs/timeline-spec.md v0.2다. 실행 순서는 인원 추정 → 흐름 →
예측이다. 흐름장(픽셀 단위)은 메모리 안에서 머리 점 주변만 읽어 셀
통계로 바로 줄이고 버린다. 머리 점도 메모리로만 받고 남기지 않는다.
출력 파일에는 구역·카메라 ID와 셀·구역 집계값만 담는다 (CLAUDE.md).
"""
from __future__ import annotations

import json
import math
import os
from collections.abc import Sequence
from pathlib import Path

import cv2
import numpy as np

from src.flow.cells import TemporalInstability, reduce_to_cells
from src.flow.estimators import FlowEstimator
from src.flow.ground import (
    head_cell_ids, head_ground_velocity, orient_homography,
    sample_head_flow,
)
from src.flow.inflow import boundary_inward, inflow_ratio
from src.flow.timeline_flow import fill_flow_fields


def load_head_plane(
    config_path: Path,
) -> tuple[np.ndarray, tuple[float, float]]:
    """구역 설정 파일에서 머리 높이 평면 행렬과 셀 원점을 읽는다.

    head_plane.H_head_img_to_ground (3, 3)와 cell_origin_m (x, y) m를
    돌려준다. 키가 없거나(E04_022처럼 머리 평면이 없는 설정) 모양이
    맞지 않으면 ValueError다.
    """
    cfg = json.loads(Path(config_path).read_text(encoding="utf-8"))
    try:
        h = np.array(
            cfg["head_plane"]["H_head_img_to_ground"], dtype=np.float64,
        )
        origin = np.array(cfg["cell_origin_m"], dtype=np.float64)
    except (KeyError, TypeError) as e:
        raise ValueError(
            f"{config_path}에 머리 평면 설정이 없다: {e}"
        ) from e
    if h.shape != (3, 3) or origin.shape != (2,):
        raise ValueError(
            f"모양이 맞지 않는다: H {h.shape}, cell_origin_m {origin.shape}"
        )
    return h, (float(origin[0]), float(origin[1]))


def analyze_video(
    video_path: Path,
    timeline_in: Path,
    timeline_out: Path,
    estimator: FlowEstimator,
    *,
    heads: Sequence[np.ndarray],
    h_head: np.ndarray,
    cell_origin_m: tuple[float, float],
    gap_frames: int = 1,
    noise_var: np.ndarray | None = None,
    window_s: float = 30.0,
    min_heads: int = 1,
    patch_radius_px: int = 6,
    inflow_min_heads: int = 0,
) -> dict:
    """인원 추정 타임라인의 각 프레임 t에 흐름 필드를 채워 쓰고 돌려준다.

    heads[t]는 round(t·fps) 프레임의 머리 점 (N, 2) 원본 px다.
    통합 분석 스크립트가 같은 프로세스 안에서 메모리로만 넘기며,
    이 함수도 파일·반환값 어디에도 남기지 않는다 (규격 9절 4번).
    t초마다 (round(t·fps) 프레임, 그 뒤 gap_frames 프레임) 쌍의 흐름을
    잰다 (dt = gap_frames / fps). 머리마다 반경 patch_radius_px 패치
    흐름의 중앙값을 h_head(머리 높이 평면)로 지면 속도(m/s)로 바꾸고,
    count_cells와 같은 규칙(cell_origin_m, meta.cell_size_m)으로 셀에
    넣어 셀 평균을 낸다. h_head 부호는 셀 중심에서 w > 0이 되게
    맞춘다. 셀마다 vx·vy·speed_var·pressure를, 프레임마다
    inflow_ratio(소수 2자리, 가정)를 채운다.
    유효 머리가 min_heads보다 적은 셀은 vx·vy·speed_var·pressure가
    null이고 불안정 창에도 넣지 않는다. density > 0인데 그 초 머리가
    없으면 측정 못 함이라 null이다 (0 아님).
    meta.models.flow는 "{estimator.name} head-r{patch_radius_px}"다.
    다른 필드(density, density_pred_60s, meta, 모르는 키)는 그대로 둔다.
    영상이 어떤 t보다 먼저 끝나면 그 프레임은 지우지 않고 흐름 필드를
    비운다: vx·vy·speed_var·inflow_ratio는 null, pressure는 density가
    0이면 0, 아니면 null이다. 그래서 같은 파일을 다시 돌려도 이전 값이
    남지 않는다. 시작 프레임 디코딩이 실패한 t도 이렇게 비우고 다음 t로
    넘어간다. 짝 프레임(+gap) 디코딩이 실패하면 영상 끝으로 본다.
    (가정) [토론] inflow_ratio는 소수 2자리 density가 0보다 큰 경계
    셀의 머리만 쓴다. 사람이 없는 셀의 움직임은 잡음으로 본다.
    움직이는 경계 머리가 inflow_min_heads보다 적으면 null이다.
    경계 셀과 h_head 부호는 첫 프레임 크기로 한 번만 정한다.
    gap_frames는 정수(bool 제외)이고 1 ≤ gap < floor(fps)다.
    meta.interval_s가 1이 아니거나 frames[i].t가 i가 아니면(0부터 빠짐없이
    1초 간격) ValueError다. 프레임 셀 cell_id 순서가 meta.cells와 다르면
    ValueError다. len(heads)가 프레임 수와 다르거나, heads[t]가 유한한
    (N, 2)가 아니거나, h_head가 유한한 (3, 3)이 아니면 ValueError다.
    결과는 JSON(allow_nan=False)으로 같은 폴더의 임시 파일에 쓴 뒤
    바꿔치기한다. 그래서 timeline_out이 timeline_in과 같아도 되고,
    중간에 멈춰도 반쯤 쓴 파일이 남지 않는다. 출력 폴더가 없으면 만든다.
    """
    if isinstance(gap_frames, bool) or not isinstance(gap_frames, int):
        raise ValueError(f"gap_frames는 정수여야 한다: {gap_frames!r}")
    if np.shape(h_head) != (3, 3) or not np.isfinite(h_head).all():
        raise ValueError(
            f"h_head는 유한한 (3, 3)이어야 한다: {np.shape(h_head)}"
        )
    timeline = json.loads(Path(timeline_in).read_text(encoding="utf-8"))
    meta = timeline["meta"]
    if meta.get("interval_s") != 1:
        raise ValueError(f"interval_s는 1이어야 한다: {meta.get('interval_s')}")
    cell_ids = [c["cell_id"] for c in meta["cells"]]
    for i, frame in enumerate(timeline["frames"]):
        if frame["t"] != i:
            raise ValueError(f"frames[{i}]의 t={frame['t']}가 {i}가 아니다")
        if [c["cell_id"] for c in frame["cells"]] != cell_ids:
            raise ValueError(
                f"t={frame['t']} 프레임 셀 순서가 meta.cells와 다르다"
            )
    if len(heads) != len(timeline["frames"]):
        raise ValueError(
            f"heads 길이 {len(heads)}가 프레임 수 "
            f"{len(timeline['frames'])}와 다르다"
        )
    for t, pts in enumerate(heads):
        pts = np.asarray(pts, dtype=np.float64)
        if pts.ndim != 2 or pts.shape[1] != 2 or not np.isfinite(pts).all():
            raise ValueError(f"heads[{t}]는 유한한 (N, 2)여야 한다")
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
        _fill_frames(
            cap, fps, estimator, meta, timeline["frames"], heads,
            np.asarray(h_head, dtype=np.float64), cell_origin_m,
            gap_frames, noise_var, window_s, min_heads, patch_radius_px,
            inflow_min_heads,
        )
    finally:
        cap.release()

    meta.setdefault("models", {})["flow"] = (
        f"{estimator.name} head-r{patch_radius_px}"
    )
    out_path = Path(timeline_out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_path.with_name(out_path.name + ".tmp")
    try:
        tmp.write_text(
            json.dumps(timeline, ensure_ascii=False, allow_nan=False),
            encoding="utf-8",
        )
        os.replace(tmp, out_path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    return timeline


def _fill_frames(
    cap: cv2.VideoCapture,
    fps: float,
    estimator: FlowEstimator,
    meta: dict,
    frames: list[dict],
    heads: Sequence[np.ndarray],
    h_head: np.ndarray,
    cell_origin_m: tuple[float, float],
    gap_frames: int,
    noise_var: np.ndarray | None,
    window_s: float,
    min_heads: int,
    patch_radius_px: int,
    inflow_min_heads: int,
) -> None:
    """프레임을 순차로 넘기며 타임라인 프레임에 흐름 필드를 채운다.

    모든 프레임은 grab()으로 넘기고, 쓰는 프레임만 retrieve()로 푼다.
    frames[i].t는 i다 (analyze_video가 검사한다).
    """
    cells = meta["cells"]
    n_cells = len(cells)
    tracker = TemporalInstability(
        n_cells, window_s=window_s, noise_var=noise_var,
    )
    is_boundary, inward = boundary_inward(cells, meta["cell_size_m"])
    h = None
    k, frame_no, prev = 0, -1, None
    while k < len(frames) and cap.grab():
        frame_no += 1
        start = int(round(frames[k]["t"] * fps))
        if frame_no == start:
            ok, prev = cap.retrieve()
            if not ok:  # 이 초만 비우고 다음 t로 넘어간다
                _clear_flow(frames[k])
                k, prev = k + 1, None
            elif h is None:
                hw = np.array(prev.shape[1::-1], dtype=np.float64)  # W, H
                centres = np.array(
                    [np.mean(c["image_polygon"], axis=0) for c in cells]
                ) * hw
                h = orient_homography(h_head, centres)
        elif frame_no == start + gap_frames and prev is not None:
            ok, frame = cap.retrieve()
            if not ok:
                break
            pts = np.asarray(heads[k], dtype=np.float64)
            flow = estimator.estimate(prev, frame)
            disp = sample_head_flow(flow, pts, patch_radius_px)
            del flow  # 흐름장은 여기서 버린다
            g, vel = head_ground_velocity(pts, disp, h, gap_frames / fps)
            ids = head_cell_ids(
                g, cells, cell_origin_m, meta["cell_size_m"],
            )
            cf = reduce_to_cells(ids, vel, n_cells)
            # 유효 머리가 적은 셀의 잡음 섞인 속도는 창에 넣지 않는다
            low = cf.count < min_heads
            s, _ = tracker.update(np.where(low[:, None], np.nan, cf.mean_v))
            frames[k]["cells"] = fill_flow_fields(
                frames[k]["cells"], cf.mean_v, s, cf.count, min_heads,
            )
            # (가정) [토론] 사람이 없는 경계 셀의 움직임은 잡음이라 뺀다
            occupied = np.array([
                round(float(c["density"]), 2) > 0 for c in frames[k]["cells"]
            ])
            ratio = inflow_ratio(
                ids, vel, is_boundary & occupied, inward,
                min_samples=inflow_min_heads,
            )
            frames[k]["inflow_ratio"] = (
                None if ratio is None else round(ratio, 2)
            )
            k, prev = k + 1, None
    for frame in frames[k:]:  # 영상이 먼저 끝나 흐름을 못 잰 프레임
        _clear_flow(frame)


def _clear_flow(frame: dict) -> None:
    """흐름을 못 잰 프레임의 흐름 필드를 비운다 (이전 실행 값도 지운다).

    vx·vy·speed_var·inflow_ratio는 null이다. pressure는 소수 2자리
    density가 0이면 0(사람 없음, 규격 5절), 아니면 null이다.
    """
    frame["inflow_ratio"] = None
    for cell in frame["cells"]:
        empty = round(float(cell["density"]), 2) == 0
        cell.update(
            vx=None, vy=None, speed_var=None,
            pressure=0 if empty else None,
        )
