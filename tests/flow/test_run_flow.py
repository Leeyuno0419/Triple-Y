"""S11 seam: run_flow.analyze_video 통합 시험.

고정 시드 질감이 알려진 px/프레임으로 움직이는 합성 영상을 FFV1(무손실)
코덱으로 tmp_path에 쓰고, 영상 1개를 끝까지 분석해 흐름 타임라인 파일을
확인한다. 지면 변환은 배율을 아는 임시 호모그래피(순수 배율 0.05 m/px)로
이 시험 안에서만 확인한다 (S2·S3는 격자 합의 뒤로 미룸).
기대값은 이동량 × fps × 배율로 손으로 계산한 상수다.
"""
from __future__ import annotations

import json
import warnings
from pathlib import Path

import cv2
import numpy as np
import pytest

from src.flow.estimators import FarnebackEstimator
from src.flow.run_flow import analyze_video

SEED = 0
FPS = 10
H_PX, W_PX = 128, 160
HALF = W_PX // 2
M_PER_PX = 0.05
H_VEL = np.diag([M_PER_PX, M_PER_PX, 1.0])  # 임시 H: 순수 배율
BORDER = 24  # 영상 가장자리·두 영역 이음매 근처 픽셀은 셀에서 뺀다
CELL_NAMES = ["moving", "static", "empty"]  # empty: 픽셀이 하나도 없는 셀


def _texture(h: int, w: int, seed: int) -> np.ndarray:
    """고정 시드의 매끄러운 무작위 질감 회색조 uint8 영상을 만든다."""
    rng = np.random.default_rng(seed)
    noise = rng.standard_normal((h, w)).astype(np.float32)
    smooth = cv2.GaussianBlur(noise, (0, 0), sigmaX=2.0)
    smooth = (smooth - smooth.min()) / (smooth.max() - smooth.min())
    return (smooth * 255).astype(np.uint8)


def _write_video(path: Path, speeds_px: list[int]) -> None:
    """왼쪽 절반은 오른쪽(+x)으로 움직이고 오른쪽 절반은 멈춘 영상을 쓴다.

    speeds_px[s]는 s초 동안의 프레임당 이동량(px)이다. 영상 길이는
    len(speeds_px)초다. 넓은 질감에서 창을 옮겨 잘라내므로 이음매가 없다.
    """
    n_frames = FPS * len(speeds_px)
    total = sum(speeds_px) * FPS
    wide = _texture(H_PX, HALF + total, SEED)
    still = _texture(H_PX, HALF, SEED + 1)
    writer = cv2.VideoWriter(
        str(path), cv2.VideoWriter_fourcc(*"FFV1"), FPS, (W_PX, H_PX),
    )
    assert writer.isOpened()
    x0 = total  # 창 왼쪽 끝. 줄어들수록 내용은 +x로 이동한다
    for k in range(n_frames):
        gray = np.hstack([wide[:, x0:x0 + HALF], still])
        writer.write(np.dstack([gray, gray, gray]))
        x0 -= speeds_px[min(k // FPS, len(speeds_px) - 1)]
    writer.release()


def _cell_index() -> np.ndarray:
    """왼쪽 내부 = 셀 0, 오른쪽 내부 = 셀 1, 나머지 = -1. 셀 2는 비어 있다."""
    index = np.full((H_PX, W_PX), -1, dtype=np.int32)
    rows = slice(BORDER, H_PX - BORDER)
    index[rows, BORDER:HALF - BORDER] = 0
    index[rows, HALF + BORDER:W_PX - BORDER] = 1
    return index


def _args(video: Path, out_path: Path, **kw: object) -> dict:
    """analyze_video 기본 인자. kw로 일부만 바꾼다."""
    args: dict = {
        "video_path": video,
        "out_path": out_path,
        "estimator": FarnebackEstimator(),
        "cell_index": _cell_index(),
        "cell_names": CELL_NAMES,
        "h_vel": H_VEL,
        "zone_id": "zone-01",
        "camera_id": "cam-01",
    }
    args.update(kw)
    return args


def _run(
    tmp_path: Path, speeds_px: list[int], **kw: object
) -> tuple[dict, Path]:
    """합성 영상을 만들어 분석하고 (읽은 타임라인, 출력 폴더)를 돌려준다."""
    video_dir = tmp_path / "video"
    out_dir = tmp_path / "out"
    video_dir.mkdir()
    out_dir.mkdir()
    video = video_dir / "synthetic.avi"
    _write_video(video, speeds_px)
    out_path = out_dir / "timeline_flow.json"
    analyze_video(**_args(video, out_path, **kw))

    def _reject(name: str) -> None:
        raise ValueError(f"JSON에 {name}이 있다")

    timeline = json.loads(
        out_path.read_text(encoding="utf-8"), parse_constant=_reject,
    )
    return timeline, out_dir


def test_writes_one_record_set_per_second_and_no_flow_file(
    tmp_path: Path,
) -> None:
    """3초 영상 → 1Hz로 t=0,1,2 세 묶음, 묶음마다 셀 3개, 파일은 1개뿐."""
    timeline, out_dir = _run(tmp_path, [2, 2, 2])
    assert timeline["zone_id"] == "zone-01"
    assert timeline["camera_id"] == "cam-01"
    assert timeline["rate_hz"] == 1
    assert timeline["flow_estimator"] == "farneback-cv2"
    assert [sec["t"] for sec in timeline["seconds"]] == [0, 1, 2]
    for sec in timeline["seconds"]:
        assert [c["cell_id"] for c in sec["cells"]] == CELL_NAMES
    # 흐름장·프레임 파일(.npy, .npz, 이미지 등)이 생기지 않는다
    assert [p.name for p in out_dir.iterdir()] == ["timeline_flow.json"]


# 프레임당 2 px × 10 fps × 0.05 m/px = 1.0 m/s (오른쪽 = +x)
EXPECTED_VX = 1.0
# 허용 오차 0.1 m/s = 0.2 px/프레임. S1 단독 허용 오차(0.5 px)보다 좁다.
# 셀 평균은 내부 픽셀 수천 개를 모으고, FFV1은 무손실이라 코덱 잡음이 없다.
# 실측(2026-11-09) 오차는 1e-4 m/s 이하다.
# 잡을 오류: 배율 빠뜨림(2.0), 부호 뒤집힘(-1.0), dt를 gap/fps가 아닌
# gap으로 씀(gap=1에서 0.1), dt를 1/fps로 고정함(gap=2에서 2.0).
# 마지막 오류는 gap=1에서는 값이 같아서 gap=2 시험이 따로 잡는다.
TOL_V = 0.1


def test_moving_cell_speed_is_converted_to_ground_m_per_s(
    tmp_path: Path,
) -> None:
    """움직이는 셀은 flow_vx ≈ 1.0 m/s, vy ≈ 0, 멈춘 셀은 ≈ 0 m/s다."""
    timeline, _ = _run(tmp_path, [2, 2, 2])
    for sec in timeline["seconds"]:
        moving, static = sec["cells"][0], sec["cells"][1]
        assert abs(moving["flow_vx"] - EXPECTED_VX) < TOL_V
        assert abs(moving["flow_vy"]) < TOL_V
        assert abs(static["flow_vx"]) < TOL_V
        assert abs(static["flow_vy"]) < TOL_V


def test_unavailable_values_become_json_null(tmp_path: Path) -> None:
    """빈 셀은 흐름 값 전부 null, 창이 차기 전 불안정은 null, 밀도 없으면 압력 null.

    window_s=2라서 t=0은 창이 덜 차고 t=1부터 불안정이 숫자가 된다.
    파일은 NaN 상수 없이 엄격한 JSON으로 읽힌다 (_run에서 확인).
    """
    timeline, _ = _run(tmp_path, [2, 2], window_s=2.0)
    first, second = timeline["seconds"]
    empty = second["cells"][2]
    assert empty["flow_quality"] == 0
    for key in ("flow_vx", "flow_vy", "flow_instability",
                "flow_pressure", "flow_counterflow"):
        assert empty[key] is None
    assert first["cells"][0]["flow_instability"] is None
    moving = second["cells"][0]
    assert moving["flow_instability"] is not None
    assert moving["flow_pressure"] is None  # rho_series=None


def test_pressure_is_density_times_instability(tmp_path: Path) -> None:
    """속도가 1초 동안 1.0 → 2.0 m/s로 바뀌면 S = 0.25, rho = 4.0이면 P = 1.0.

    손 계산 (window_s=2, 잡음 바닥 없음):
    프레임당 2 px, 4 px → V = 1.0, 2.0 m/s, 창 평균 U = 1.5 m/s.
    S = ((1.0 − 1.5)² + (2.0 − 1.5)²) / 2 = 0.25 m²/s².
    P = rho[t=1] × S = 4.0 /m² × 0.25 = 1.0 /s². 멈춘 셀은 S ≈ 0, P ≈ 0.
    허용 오차: 속도 오차 e이면 S 오차 ≈ 2 × 0.5 × e = e. TOL_V(0.1) 그대로.
    """
    rho = np.array([[1.0] * 3, [4.0] * 3])  # t=0 행과 t=1 행이 다르다
    timeline, _ = _run(tmp_path, [2, 4], window_s=2.0, rho_series=rho)
    moving, static = timeline["seconds"][1]["cells"][:2]
    assert abs(moving["flow_instability"] - 0.25) < TOL_V
    # rho[t] = 4.0 → P = 1.0. 허용 오차 4 × TOL_V. rho[t-1]을 쓰면 0.25다
    assert abs(moving["flow_pressure"] - 1.0) < 4 * TOL_V
    assert abs(static["flow_instability"]) < TOL_V
    assert abs(static["flow_pressure"]) < 4 * TOL_V


def test_gap_two_frames_divides_by_gap_over_fps(tmp_path: Path) -> None:
    """gap=2: 흐름 4 px, dt = 2/10 s → 4 × 0.05 / 0.2 = 1.0 m/s."""
    timeline, _ = _run(tmp_path, [2, 2], gap_frames=2)
    for sec in timeline["seconds"]:
        assert abs(sec["cells"][0]["flow_vx"] - EXPECTED_VX) < TOL_V


def test_cells_below_min_quality_are_emptied(tmp_path: Path) -> None:
    """움직이는 셀 픽셀 수(80 × 32 = 2560)보다 큰 기준이면 흐름 값이 null이다."""
    timeline, _ = _run(tmp_path, [2], min_quality=2561)
    moving = timeline["seconds"][0]["cells"][0]
    assert moving["flow_quality"] == 2560
    assert moving["flow_vx"] is None
    assert moving["flow_vy"] is None


def test_creates_missing_output_folder(tmp_path: Path) -> None:
    """출력 폴더가 없으면 만들고, 임시 파일을 남기지 않는다."""
    video = tmp_path / "synthetic.avi"
    _write_video(video, [2])
    out_dir = tmp_path / "new" / "nested"
    analyze_video(**_args(video, out_dir / "timeline_flow.json"))
    assert [p.name for p in out_dir.iterdir()] == ["timeline_flow.json"]


def test_horizon_crossing_mask_drops_pixels_behind_camera(
    tmp_path: Path,
) -> None:
    """원근 H의 지평선(w = 0)이 셀을 가로지르면 그 위 픽셀은 버린다.

    H의 셋째 행 (0, 1/40, -1) → w = y/40 − 1. y = 40에서 0, 위쪽은 음수
    (카메라 뒤). 셀 행 24~103 중 y ≤ 40 픽셀이 무한대·부호 뒤집힌 값을
    내지 않아야 한다. y > 40 픽셀은 +x 이동이므로 셀 vx는 유한한 양수다.
    numpy 0 나눗셈 경고도 나오지 않아야 한다.
    """
    h = np.array([
        [M_PER_PX, 0.0, 0.0],
        [0.0, M_PER_PX, 0.0],
        [0.0, 1.0 / 40.0, -1.0],
    ])
    with warnings.catch_warnings():
        warnings.simplefilter("error", RuntimeWarning)
        timeline, _ = _run(tmp_path, [2], h_vel=h)
    moving = timeline["seconds"][0]["cells"][0]
    assert moving["flow_vx"] is not None
    assert moving["flow_vx"] > 0
    # y = 41~103 행만 남는다: 63 × 32 = 2016. 경계 행은 흐름에 따라
    # 끝점 w가 0 이하일 수 있어 1행 여유를 둔다.
    assert 62 * 32 <= moving["flow_quality"] <= 63 * 32


def test_rejects_cell_index_not_matching_frame_size(tmp_path: Path) -> None:
    """셀 번호표 모양이 프레임 (H, W)와 다르면 ValueError다."""
    video = tmp_path / "synthetic.avi"
    _write_video(video, [2])
    small = _cell_index()[:64, :80]
    with pytest.raises(ValueError, match="cell_index"):
        analyze_video(**_args(video, tmp_path / "t.json", cell_index=small))


def test_rejects_missing_video(tmp_path: Path) -> None:
    """열 수 없는 영상이면 ValueError다."""
    with pytest.raises(ValueError, match="열 수 없다"):
        analyze_video(**_args(tmp_path / "none.avi", tmp_path / "t.json"))


@pytest.mark.parametrize("gap", [0, 10, True])
def test_rejects_bad_gap_frames(tmp_path: Path, gap: object) -> None:
    """gap_frames는 정수 1 이상, floor(fps)=10 미만이다. bool은 받지 않는다."""
    video = tmp_path / "synthetic.avi"
    _write_video(video, [2])
    with pytest.raises(ValueError, match="gap_frames"):
        analyze_video(**_args(video, tmp_path / "t.json", gap_frames=gap))


@pytest.mark.parametrize("rho", [
    np.full(3, 1.0),        # 1차원
    np.full((2, 2), 1.0),   # 셀 수가 다르다
])
def test_rejects_bad_rho_series_shape(
    tmp_path: Path, rho: np.ndarray
) -> None:
    """rho_series는 (T, n_cells) 2차원이어야 한다."""
    video = tmp_path / "synthetic.avi"
    _write_video(video, [2])
    with pytest.raises(ValueError, match="rho_series"):
        analyze_video(**_args(video, tmp_path / "t.json", rho_series=rho))
