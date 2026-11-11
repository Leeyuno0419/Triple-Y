"""T5·T6 테스트 경계: run_flow.load_head_plane·analyze_video 시험.

고정 시드 질감이 알려진 px/프레임으로 움직이는 합성 영상을 FFV1(무손실)
코덱으로 tmp_path에 쓰고, 인원 추정 모듈이 만든 것과 같은 모양의 합성
타임라인(meta + density)과 초별 머리 점(메모리)을 함께 넘긴다.
analyze_video가 흐름 필드를 채운 타임라인 파일을 읽어 확인한다.

머리 높이 평면 H = diag(0.05, 0.05, 1) (0.05 m/px), 셀 원점
(0.1, 1.2) m, cell_size_m = 2라 col = ⌊(x − 2) / 40⌋,
row = ⌊(y − 24) / 40⌋다 (count_cells 규칙).
- 0열 셀은 왼쪽 절반(움직이는 질감) x 2~42 px. 화면 왼쪽 끝에서
  2/240 = 0.008 < edge_tol 0.02라 화각 경계 셀이다.
- 3열 셀은 오른쪽 절반(멈춘 질감) x 122~162 px. 경계가 아니다.
- 0행 y 24~64 px, 1행 y 64~104 px. 위·아래 끝에 닿지 않는다.
- 머리는 셀마다 4개, 셀 중심 ± 8 px. 패치 반경 6 px라 셀·절반을
  넘지 않는다.
기대값은 이동량 × fps × 배율로 손으로 계산한 상수다.
"""
from __future__ import annotations

import json
import math
import os
from pathlib import Path

import cv2
import numpy as np
import pytest

from src.flow.estimators import FarnebackEstimator
from src.flow.run_flow import analyze_video, load_head_plane

SEED = 0
FPS = 10
H_PX, W_PX = 128, 240
HALF = W_PX // 2
CELL_PX = 40
# (cell_id, row, col, 왼쪽 x px, 위쪽 y px)
CELLS = [
    ("c-0000", 0, 0, 2, 24),     # 움직임, 경계
    ("c-0003", 0, 3, 122, 24),   # 멈춤
    ("c-0100", 1, 0, 2, 64),     # 움직임, 경계, 밀도 0
    ("c-0103", 1, 3, 122, 64),   # 멈춤
]
CELL_IDS = [c[0] for c in CELLS]
DENSITY = [4.0, 1.5, 0, 2.25]
H_HEAD = np.diag([0.05, 0.05, 1.0])
ORIGIN = (0.1, 1.2)


def _cell_heads(i: int, n: int = 4) -> np.ndarray:
    """CELLS[i] 중심 ± 8 px 머리 점 n개 (최대 4) (n, 2) px."""
    _, _, _, x, y = CELLS[i]
    cx, cy = x + CELL_PX / 2, y + CELL_PX / 2
    pts = [(cx - 8, cy - 8), (cx + 8, cy - 8), (cx - 8, cy + 8),
           (cx + 8, cy + 8)]
    return np.array(pts[:n], dtype=np.float64)


def _heads(n_s: int) -> list[np.ndarray]:
    """모든 초에 네 셀마다 머리 4개를 둔 초별 머리 점 목록."""
    pts = np.vstack([_cell_heads(i) for i in range(len(CELLS))])
    return [pts.copy() for _ in range(n_s)]


def _head_kw(n_s: int, kw: dict) -> dict:
    """heads·h_head·cell_origin_m 기본값을 kw에 채운다."""
    kw.setdefault("heads", _heads(n_s))
    kw.setdefault("h_head", H_HEAD)
    kw.setdefault("cell_origin_m", ORIGIN)
    return kw


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


def _polygon(x: int, y: int) -> list[list[float]]:
    """왼쪽 위 (x, y) px인 40 px 정사각형을 TL, TR, BR, BL 정규화 좌표로."""
    xs, ys = (x, x + CELL_PX), (y, y + CELL_PX)
    return [
        [xs[0] / W_PX, ys[0] / H_PX], [xs[1] / W_PX, ys[0] / H_PX],
        [xs[1] / W_PX, ys[1] / H_PX], [xs[0] / W_PX, ys[1] / H_PX],
    ]


def _counting_timeline(n_frames: int) -> dict:
    """인원 추정 모듈 출력과 같은 모양의 합성 타임라인 (흐름 필드는 null)."""
    return {
        "schema_version": "0.1",
        "meta": {
            "zone_id": "zone-test",
            "camera_id": "cam-test",
            "video_id": "SYN_001",
            "duration_s": n_frames,
            "interval_s": 1,
            "cell_size_m": 2,
            "models": {
                "counter": "p2pnet-vgg16", "flow": None, "predictor": None,
            },
            "prediction": {"history_s": 30, "horizon_s": 60},
            "cells": [
                {
                    "cell_id": cid, "row": r, "col": c,
                    "walkable_area_m2": 4.0, "image_polygon": _polygon(x, y),
                }
                for cid, r, c, x, y in CELLS
            ],
            "note": "알 수 없는 meta 키",
        },
        "frames": [
            {
                "t": t,
                "inflow_ratio": None,
                "cells": [
                    {
                        "cell_id": cid, "density": rho,
                        "vx": None, "vy": None, "speed_var": None,
                        "pressure": None,
                        # 규격 5절: 예측 입력 30초 미만(t < 29)은 null
                        "density_pred_60s": None if t < 29 else 0.5 + t,
                        "extra": t,
                    }
                    for cid, rho in zip(CELL_IDS, DENSITY)
                ],
            }
            for t in range(n_frames)
        ],
    }


def _reject(name: str) -> None:
    """엄격한 JSON: NaN·Infinity 상수가 있으면 실패한다."""
    raise ValueError(f"JSON에 {name}이 있다")


def _write_json(path: Path, data: dict) -> None:
    """dict를 UTF-8 JSON 파일로 쓴다."""
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def _read(path: Path) -> dict:
    """엄격한 JSON(NaN·Infinity 없음)으로 읽는다."""
    return json.loads(
        path.read_text(encoding="utf-8"), parse_constant=_reject,
    )


def _prepare(
    tmp_path: Path, speeds_px: list[int], n_frames: int | None = None,
) -> tuple[Path, Path, dict]:
    """합성 영상과 합성 인원 추정 타임라인을 쓰고 (영상, 타임라인, 내용)."""
    video = tmp_path / "video" / "synthetic.avi"
    video.parent.mkdir()
    _write_video(video, speeds_px)
    timeline_in = tmp_path / "in" / "SYN_001.json"
    timeline_in.parent.mkdir()
    n = len(speeds_px) if n_frames is None else n_frames
    data = _counting_timeline(n)
    _write_json(timeline_in, data)
    return video, timeline_in, data


def _run(
    tmp_path: Path,
    speeds_px: list[int],
    n_frames: int | None = None,
    **kw: object,
) -> tuple[dict, dict, Path]:
    """합성 입력을 분석하고 (읽은 결과, 입력 내용, 출력 폴더)를 돌려준다.

    출력 폴더 tmp_path/out은 미리 만들지 않는다. window_s 기본은 2초다.
    """
    video, timeline_in, data = _prepare(tmp_path, speeds_px, n_frames)
    out_dir = tmp_path / "out"
    kw.setdefault("window_s", 2.0)
    analyze_video(
        video, timeline_in, out_dir / "SYN_001.json", FarnebackEstimator(),
        **_head_kw(len(data["frames"]), kw),
    )
    return _read(out_dir / "SYN_001.json"), data, out_dir


# 프레임당 2 px × 10 fps × 0.05 m/px = 1.0 m/s (오른쪽 = 지면 +x = col 방향)
EXPECTED_VX = 1.0
# 허용 오차 0.1 m/s = 0.2 px/프레임. 머리 4개 × 패치 13×13 중앙값을
# 평균하고 FFV1은 무손실이라 코덱 잡음이 없다.
# 잡을 오류: 배율 빠뜨림(2.0), 부호 뒤집힘(-1.0), dt를 gap/fps가 아닌
# gap으로 씀(gap=1에서 0.1), dt를 1/fps로 고정함(gap=2에서 2.0).
TOL_V = 0.1


def test_moving_cell_velocity_in_m_per_s_and_still_cell_zero(
    tmp_path: Path,
) -> None:
    """움직이는 셀 vx ≈ 1.0 m/s, vy ≈ 0, 멈춘 셀은 vx, vy ≈ 0 m/s다.

    window_s=2라서 t=0은 불안정 창이 덜 차 speed_var·pressure만 null이고,
    속도는 t=0부터 있다 (fill_flow_fields 필드별 null 규칙).
    """
    result, _, _ = _run(tmp_path, [2, 2, 2])
    first = result["frames"][0]["cells"][0]
    assert first["speed_var"] is None
    assert first["pressure"] is None
    for frame in result["frames"]:
        moving, still = frame["cells"][0], frame["cells"][1]
        assert abs(moving["vx"] - EXPECTED_VX) < TOL_V
        assert abs(moving["vy"]) < TOL_V
        assert abs(still["vx"]) < TOL_V
        assert abs(still["vy"]) < TOL_V


def test_speed_var_and_pressure_from_stored_density(tmp_path: Path) -> None:
    """속도가 1초 사이 1.0 → 2.0 m/s로 바뀌면 S = 0.25, ρ = 4.0이면 P = 1.0.

    손 계산 (window_s=2, 잡음 바닥 없음): 프레임당 2 px, 4 px →
    V = 1.0, 2.0 m/s, 창 평균 U = 1.5 m/s.
    S = ((1.0 − 1.5)² + (2.0 − 1.5)²) / 2 = 0.25 m²/s².
    P = density(4.0 /m²) × S = 1.0 /s². 멈춘 셀은 S ≈ 0, P ≈ 0.
    허용 오차: 속도 오차 e이면 S 오차 ≈ e라 TOL_V, P는 4 × TOL_V.
    """
    result, _, _ = _run(tmp_path, [2, 4])
    moving, still = result["frames"][1]["cells"][:2]
    assert abs(moving["vx"] - 2.0) < TOL_V
    assert abs(moving["speed_var"] - 0.25) < TOL_V
    assert abs(moving["pressure"] - 1.0) < 4 * TOL_V
    assert abs(still["speed_var"]) < TOL_V
    assert abs(still["pressure"]) < 4 * TOL_V


def test_empty_cell_has_null_velocity_and_zero_pressure(
    tmp_path: Path,
) -> None:
    """density 0인 셀은 움직임이 있어도 vx·vy·speed_var null, pressure 0."""
    result, _, _ = _run(tmp_path, [2, 2])
    empty = result["frames"][1]["cells"][2]
    assert empty["cell_id"] == "c-0100"
    assert empty["vx"] is None
    assert empty["vy"] is None
    assert empty["speed_var"] is None
    assert empty["pressure"] == 0


def test_keeps_counting_fields_and_sets_flow_model(tmp_path: Path) -> None:
    """density·density_pred_60s·모르는 키·meta는 그대로, models.flow만 채운다.

    프레임 수와 t, 셀 순서도 그대로다. 31프레임이라 t ≥ 29의 숫자
    예측값도 보존되는지 본다. 출력 폴더가 없으면 만들고,
    폴더에는 타임라인 파일 하나만 남는다 (임시 파일·흐름장 없음).
    """
    result, data, out_dir = _run(tmp_path, [2, 2, 2], n_frames=31)
    assert result["schema_version"] == "0.1"
    expected_meta = data["meta"]
    expected_meta["models"]["flow"] = "farneback-cv2 head-r6"
    assert result["meta"] == expected_meta
    assert [f["t"] for f in result["frames"]] == list(range(31))
    assert result["frames"][30]["cells"][0]["density_pred_60s"] == 30.5
    for frame, before in zip(result["frames"], data["frames"]):
        assert [c["cell_id"] for c in frame["cells"]] == CELL_IDS
        for cell, old in zip(frame["cells"], before["cells"]):
            assert cell["density"] == old["density"]
            assert cell["density_pred_60s"] == old["density_pred_60s"]
            assert cell["extra"] == old["extra"]
    assert [p.name for p in out_dir.iterdir()] == ["SYN_001.json"]


def test_inflow_ratio_is_one_for_motion_into_zone(tmp_path: Path) -> None:
    """경계 셀(0열)이 구역 안쪽으로 움직이면 inflow_ratio = 1.0이다.

    손 계산: 셀 중심 (col+0.5, row+0.5)·2 m, 구역 중심 (2, 2) m.
    c-0000 중심 (1, 1) → 안쪽 (1, 1)/√2, c-0100 중심 (1, 3) → (1, −1)/√2.
    움직임은 +x 1.0 m/s라 두 셀 모두 내적 1/√2 > 0 → 비율 1.0.
    1열 셀은 화면 끝에 닿지 않아 분모에 들지 않는다.
    """
    result, _, _ = _run(tmp_path, [2, 2])
    assert [f["inflow_ratio"] for f in result["frames"]] == [1.0, 1.0]


def test_inflow_ratio_is_null_without_movement(tmp_path: Path) -> None:
    """멈춘 영상은 경계에 움직이는 머리가 없어 inflow_ratio가 null이다."""
    result, _, _ = _run(tmp_path, [0, 0])
    assert [f["inflow_ratio"] for f in result["frames"]] == [None, None]


def test_gap_two_frames_divides_by_gap_over_fps(tmp_path: Path) -> None:
    """gap=2: 흐름 4 px, dt = 2/10 s → 4 × 0.05 / 0.2 = 1.0 m/s."""
    result, _, _ = _run(tmp_path, [2, 2], gap_frames=2)
    assert abs(result["frames"][1]["cells"][0]["vx"] - EXPECTED_VX) < TOL_V


def test_writes_in_place_when_output_is_input(tmp_path: Path) -> None:
    """timeline_out이 timeline_in과 같으면 그 파일을 바꾸고 임시 파일은 없다."""
    video, timeline_in, _ = _prepare(tmp_path, [2, 2])
    analyze_video(
        video, timeline_in, timeline_in, FarnebackEstimator(),
        **_head_kw(2, {"window_s": 2.0}),
    )
    result = _read(timeline_in)
    assert abs(result["frames"][1]["cells"][0]["vx"] - EXPECTED_VX) < TOL_V
    assert [p.name for p in timeline_in.parent.iterdir()] == ["SYN_001.json"]


def test_rejects_missing_video(tmp_path: Path) -> None:
    """열 수 없는 영상이면 ValueError다."""
    _, timeline_in, _ = _prepare(tmp_path, [2])
    with pytest.raises(ValueError, match="열 수 없다"):
        analyze_video(
            tmp_path / "none.avi", timeline_in, tmp_path / "o.json",
            FarnebackEstimator(), **_head_kw(1, {}),
        )


@pytest.mark.parametrize("gap", [0, 10, True])
def test_rejects_bad_gap_frames(tmp_path: Path, gap: object) -> None:
    """gap_frames는 정수 1 이상, floor(fps)=10 미만이다. bool은 받지 않는다."""
    video, timeline_in, _ = _prepare(tmp_path, [2])
    with pytest.raises(ValueError, match="gap_frames"):
        analyze_video(
            video, timeline_in, tmp_path / "o.json", FarnebackEstimator(),
            **_head_kw(1, {"gap_frames": gap}),
        )


def test_rejects_frame_cells_out_of_meta_order(tmp_path: Path) -> None:
    """프레임 셀 순서가 meta.cells와 다르면 짝이 어긋나므로 ValueError다."""
    video, timeline_in, data = _prepare(tmp_path, [2])
    cells = data["frames"][0]["cells"]
    cells[0], cells[1] = cells[1], cells[0]
    _write_json(timeline_in, data)
    with pytest.raises(ValueError, match="셀 순서"):
        analyze_video(
            video, timeline_in, tmp_path / "o.json", FarnebackEstimator(),
            **_head_kw(1, {}),
        )


@pytest.mark.parametrize("change", ["duplicate_t", "descending_t", "interval"])
def test_rejects_timeline_not_one_second_from_zero(
    tmp_path: Path, change: str,
) -> None:
    """interval_s가 1이 아니거나 frames[i].t가 i가 아니면 ValueError다.

    PR #20 검사기와 같은 규칙이다: t = 0, 1, 2, … 빠짐없이 오름차순.
    """
    video, timeline_in, data = _prepare(tmp_path, [2, 2, 2])
    frames = data["frames"]
    if change == "duplicate_t":
        frames[2]["t"] = 1          # 0, 1, 1
    elif change == "descending_t":
        frames.reverse()            # 2, 1, 0
    else:
        data["meta"]["interval_s"] = 2
    _write_json(timeline_in, data)
    with pytest.raises(ValueError, match="interval_s|t="):
        analyze_video(
            video, timeline_in, tmp_path / "o.json", FarnebackEstimator(),
            **_head_kw(3, {}),
        )


def test_pairs_frame_round_t_fps_with_next_gap_frame(tmp_path: Path) -> None:
    """t초 흐름은 (round(t·fps), round(t·fps) + gap) 프레임 쌍에서만 잰다.

    fps = 7.5, 30프레임(4초). 질감은 프레임 0→1, 8→9, 15→16, 22→23
    사이에서만 2 px 움직이고 나머지 쌍은 멈춰 있다.
    round(t·7.5) = 0, 8, 15, 22 (파이썬 round: 22.5 → 22).
    기대 vx = 2 px × 7.5 fps × 0.05 m/px = 0.75 m/s (모든 t).
    잡을 오류: int(t·fps)(t=1에서 7→8 쌍, 0), 반올림 올림(t=3에서
    23→24, 0), 시작 +1·+fps//2 어긋남(0).
    """
    fps, n_frames, moves = 7.5, 30, {0, 8, 15, 22}
    video = tmp_path / "pair.avi"
    wide = _texture(H_PX, HALF + 2 * len(moves), SEED)
    still = _texture(H_PX, HALF, SEED + 1)
    writer = cv2.VideoWriter(
        str(video), cv2.VideoWriter_fourcc(*"FFV1"), fps, (W_PX, H_PX),
    )
    x0 = 2 * len(moves)
    for k in range(n_frames):
        gray = np.hstack([wide[:, x0:x0 + HALF], still])
        writer.write(np.dstack([gray, gray, gray]))
        if k in moves:
            x0 -= 2
    writer.release()
    timeline_in = tmp_path / "SYN_001.json"
    _write_json(timeline_in, _counting_timeline(4))
    out = tmp_path / "out.json"
    analyze_video(
        video, timeline_in, out, FarnebackEstimator(),
        **_head_kw(4, {"window_s": 2.0}),
    )
    vx = [f["cells"][0]["vx"] for f in _read(out)["frames"]]
    assert all(abs(v - 0.75) < TOL_V for v in vx), vx


class _StubEstimator:
    """호출 순서마다 정해 둔 흐름장을 돌려주는 시험용 추정기.

    make(call_no)가 (H, W, 2) px 흐름을 만든다. 영상 내용은 보지 않는다.
    """

    name = "stub"

    def __init__(self, make: object) -> None:
        """흐름장 생성 함수를 받는다."""
        self._make = make
        self._calls = 0

    def estimate(
        self, prev_bgr: np.ndarray, next_bgr: np.ndarray,
    ) -> np.ndarray:
        """다음 호출 번호의 흐름장을 돌려준다."""
        flow = self._make(self._calls)
        self._calls += 1
        return flow


def _uniform(dx: float) -> np.ndarray:
    """프레임 전체가 +x로 dx px 움직이는 흐름장."""
    flow = np.zeros((H_PX, W_PX, 2), dtype=np.float32)
    flow[..., 0] = dx
    return flow


def _run_stub(
    tmp_path: Path, n_s: int, make: object, data: dict | None = None,
    **kw: object,
) -> dict:
    """멈춘 n_s초 영상과 흐름 시험 추정기로 분석해 결과를 읽어 돌려준다."""
    video, timeline_in, base = _prepare(tmp_path, [0] * n_s)
    if data is not None:
        _write_json(timeline_in, data)
    else:
        data = base
    out = tmp_path / "out.json"
    kw.setdefault("window_s", 2.0)
    analyze_video(
        video, timeline_in, out, _StubEstimator(make),
        **_head_kw(len(data["frames"]), kw),
    )
    return _read(out)


def test_low_quality_cell_sample_is_kept_out_of_window(
    tmp_path: Path,
) -> None:
    """유효 머리가 min_heads보다 적은 초의 셀 속도는 불안정 창에 넣지 않는다.

    전체 흐름 2 px → 1.0 m/s. t=1에만 c-0000 머리가 1개(< 2)이고
    그 자리 흐름이 10 px(5.0 m/s)다.
    window_s=5, t=4 창 = t0~t4. 유효 표본 기준 ceil(0.8 × 5) = 4.
    t=1을 빼면 1.0 네 개 → S = 0. 넣으면 (1, 5, 1, 1, 1) →
    평균 1.8, S = (4 × 0.64 + 10.24) / 5 = 2.56.
    """
    def make(call: int) -> np.ndarray:
        flow = _uniform(2.0)
        if call == 1:
            flow[24:64, 2:43, 0] = 10.0
        return flow

    heads = _heads(6)
    heads[1] = np.vstack(
        [_cell_heads(0, 1)] + [_cell_heads(i) for i in (1, 2, 3)]
    )
    result = _run_stub(
        tmp_path, 6, make, window_s=5.0, min_heads=2, heads=heads,
    )
    assert result["frames"][1]["cells"][0]["vx"] is None
    assert result["frames"][4]["cells"][0]["speed_var"] == 0.0


def test_inflow_ignores_boundary_cells_without_people(tmp_path: Path) -> None:
    """density 0인 경계 셀의 움직임은 잡음이라 inflow_ratio에서 뺀다 (가정).

    c-0000(ρ 4.0)은 +x(안쪽 (1, 1)/√2와 내적 > 0), c-0100(ρ 0)은 −x
    (안쪽 (1, −1)/√2와 내적 < 0)로 2 px 움직인다. c-0100을 빼면 1.0이고,
    넣으면 약 0.49다.
    """
    def make(call: int) -> np.ndarray:
        flow = _uniform(2.0)
        flow[64:, :, 0] = -2.0
        return flow

    result = _run_stub(tmp_path, 2, make)
    assert [f["inflow_ratio"] for f in result["frames"]] == [1.0, 1.0]


def test_inflow_is_null_when_only_moving_boundary_cell_is_empty(
    tmp_path: Path,
) -> None:
    """경계 셀이 모두 density 0이면 움직여도 inflow_ratio는 null이다."""
    data = _counting_timeline(2)
    for frame in data["frames"]:
        frame["cells"][0]["density"] = 0
    result = _run_stub(tmp_path, 2, lambda call: _uniform(2.0), data=data)
    assert [f["inflow_ratio"] for f in result["frames"]] == [None, None]


def _stale(data: dict) -> dict:
    """모든 프레임에 이전 실행이 남긴 흐름 값을 채운다 (다시 돌리기 시험용)."""
    for frame in data["frames"]:
        frame["inflow_ratio"] = 0.9
        for cell in frame["cells"]:
            cell.update(vx=9.0, vy=9.0, speed_var=9.0, pressure=9.0)
    return data


def test_frames_after_video_end_clear_stale_flow_values(
    tmp_path: Path,
) -> None:
    """영상 밖 프레임은 이전 값을 지우고 vx·vy·speed_var·inflow_ratio null.

    pressure는 소수 2자리 density가 0이면 0(사람 없음), 아니면 null이다.
    영상 2초, 타임라인 4초 → t=2, 3이 영상 밖이다.
    """
    data = _stale(_counting_timeline(4))
    result = _run_stub(tmp_path, 2, lambda call: _uniform(2.0), data=data)
    assert [f["t"] for f in result["frames"]] == [0, 1, 2, 3]
    assert result["frames"][1]["cells"][0]["vx"] == 1.0
    for frame in result["frames"][2:]:
        assert frame["inflow_ratio"] is None
        for cell in frame["cells"]:
            assert cell["vx"] is None
            assert cell["vy"] is None
            assert cell["speed_var"] is None
        assert [c["pressure"] for c in frame["cells"]] == [
            None, None, 0, None,
        ]


def test_failed_start_frame_leaves_that_second_null_and_continues(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """t=1 시작 프레임(10번) 디코딩이 실패하면 t=1만 비우고 t=2는 잰다.

    retrieve()가 10번 프레임에서만 (False, None)을 내는 캡처로 바꾼다.
    흐름은 2 px → 1.0 m/s. t=1은 이전 값(9.0)을 지우고 null이다.
    """
    real = cv2.VideoCapture

    class FailingCapture:
        """10번 프레임 retrieve()만 실패하는 VideoCapture 감싸개."""

        def __init__(self, path: str) -> None:
            """실제 캡처를 연다."""
            self._cap = real(path)
            self._no = -1

        def __getattr__(self, name: str) -> object:
            """나머지 메서드는 실제 캡처에 넘긴다."""
            return getattr(self._cap, name)

        def grab(self) -> bool:
            """프레임 번호를 세며 넘긴다."""
            self._no += 1
            return self._cap.grab()

        def retrieve(self) -> tuple[bool, np.ndarray | None]:
            """10번 프레임이면 실패를 낸다."""
            if self._no == 10:
                return False, None
            return self._cap.retrieve()

    monkeypatch.setattr(cv2, "VideoCapture", FailingCapture)
    data = _stale(_counting_timeline(3))
    result = _run_stub(tmp_path, 3, lambda call: _uniform(2.0), data=data)
    vx = [f["cells"][0]["vx"] for f in result["frames"]]
    assert vx == [1.0, None, 1.0]
    assert result["frames"][1]["inflow_ratio"] is None


def test_noise_var_is_subtracted_from_speed_var(tmp_path: Path) -> None:
    """noise_var가 불안정 계산에 넘어간다: S = 0.25 − 0.05 = 0.2.

    흐름 2 px, 4 px → V = 1.0, 2.0 m/s → 잡음 빼기 전 0.25 m²/s²
    (window_s=2). P = round(4.0 × 0.2, 4) = 0.8.
    """
    result = _run_stub(
        tmp_path, 2, lambda call: _uniform(2.0 * (call + 1)),
        noise_var=np.full(4, 0.05),
    )
    cell = result["frames"][1]["cells"][0]
    assert cell["speed_var"] == 0.2
    assert cell["pressure"] == 0.8


@pytest.mark.parametrize("min_heads, expected", [(4, 1.0), (5, None)])
def test_inflow_min_heads_forces_null(
    tmp_path: Path, min_heads: int, expected: float | None,
) -> None:
    """움직이는 경계 머리가 inflow_min_heads보다 적으면 null이다.

    사람이 있는 경계 셀은 c-0000 하나이고 머리는 4개다.
    """
    result = _run_stub(
        tmp_path, 1, lambda call: _uniform(2.0),
        inflow_min_heads=min_heads,
    )
    assert result["frames"][0]["inflow_ratio"] == expected


def test_inflow_ratio_is_rounded_to_two_decimals(tmp_path: Path) -> None:
    """c-0000 머리 3개 중 (14, 36)만 +x, (30, 36)·(30, 52)는 −x → 1/3.

    패치 반경 6이라 x 8~20은 +x 구역(x < 22), x 24~36은 −x 구역이다.
    소수 2자리로 반올림해 0.33이다 (가정: 규격에 자릿수가 없다).
    """
    def make(call: int) -> np.ndarray:
        flow = _uniform(-2.0)
        flow[:, :22, 0] = 2.0
        return flow

    mixed = np.array([[14.0, 36.0], [30.0, 36.0], [30.0, 52.0]])
    heads = [np.vstack([mixed] + [_cell_heads(i) for i in (1, 2, 3)])]
    result = _run_stub(tmp_path, 1, make, heads=heads)
    assert result["frames"][0]["inflow_ratio"] == 0.33


def test_failed_write_leaves_no_temp_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """바꿔치기가 실패하면 오류를 그대로 내고 .tmp 파일을 지운다."""
    video, timeline_in, _ = _prepare(tmp_path, [2])
    out_dir = tmp_path / "out"

    def fail(src: object, dst: object) -> None:
        raise OSError("바꿔치기 실패")

    monkeypatch.setattr(os, "replace", fail)
    with pytest.raises(OSError, match="바꿔치기 실패"):
        analyze_video(
            video, timeline_in, out_dir / "SYN_001.json",
            _StubEstimator(lambda call: _uniform(2.0)), **_head_kw(1, {}),
        )
    assert list(out_dir.iterdir()) == []


def test_load_head_plane_reads_e04_039() -> None:
    """E04_039 설정에서 (3, 3) 머리 평면 행렬과 셀 원점을 읽는다."""
    h, origin = load_head_plane(Path("infra/homography/E04_039.json"))

    assert h.shape == (3, 3) and h.dtype == np.float64
    assert origin == (-0.5, -1.34)


def test_load_head_plane_rejects_config_without_head_plane() -> None:
    """E04_022에는 head_plane·cell_origin_m이 없어 ValueError다."""
    with pytest.raises(ValueError):
        load_head_plane(Path("infra/homography/E04_022.json"))


@pytest.mark.parametrize("cfg", [
    {"head_plane": {"H_head_img_to_ground": [[1, 0, 0], [0, 1, 0]]},
     "cell_origin_m": [0, 0]},
    {"head_plane": {"H_head_img_to_ground": np.eye(3).tolist()},
     "cell_origin_m": [0, 0, 0]},
    {"head_plane": {"H_head_img_to_ground": np.eye(3).tolist()}},
])
def test_load_head_plane_rejects_bad_shapes(
    tmp_path: Path, cfg: dict,
) -> None:
    """행렬이 (3, 3)이 아니거나 원점이 (x, y)가 아니거나 없으면 ValueError."""
    path = tmp_path / "zone.json"
    _write_json(path, cfg)

    with pytest.raises(ValueError):
        load_head_plane(path)


@pytest.mark.parametrize("sign", [1.0, -1.0])
def test_head_plane_sign_does_not_change_result(
    tmp_path: Path, sign: float,
) -> None:
    """H와 −H는 같은 사상이라 결과가 같다 (orient_homography).

    흐름 2 px → 2 × 0.05 × 10 = 1.0 m/s. 경계 셀 inflow 1.0.
    """
    result = _run_stub(
        tmp_path, 2, lambda call: _uniform(2.0), h_head=sign * H_HEAD,
    )
    for frame in result["frames"]:
        assert [c["vx"] for c in frame["cells"]] == [1.0, 1.0, None, 1.0]
        assert frame["inflow_ratio"] == 1.0


def test_orientation_uses_cell_centres_in_pixels(tmp_path: Path) -> None:
    """부호는 셀 중심 px에서 정한다 (정규화 좌표 0~1에서 정하면 안 된다).

    이 H는 w = 0.02·y − 0.2라 y ≤ 1에서 음수, 셀 영역(y 24~104 px)에서
    양수다. 정규화 좌표로 부호를 정하면 셀 영역 w가 음수가 되어 머리가
    모두 버려지고 vx가 전부 null이 된다.
    """
    h = np.array([[0.05, 0, 0], [0, 0.05, 0], [0, 0.02, -0.2]])
    result = _run_stub(
        tmp_path, 2, lambda call: _uniform(2.0), h_head=h,
    )
    vxs = [
        c["vx"] for f in result["frames"] for c in f["cells"]
        if c["vx"] is not None
    ]
    assert vxs and all(math.isfinite(v) for v in vxs)


def test_cell_with_people_but_no_heads_that_second_is_null(
    tmp_path: Path,
) -> None:
    """density > 0인데 그 초 머리가 0개면 측정 못 함이라 null이다 (0 아님).

    t=1에 c-0000(ρ 4.0) 머리를 모두 뺀다.
    """
    heads = _heads(2)
    heads[1] = np.vstack([_cell_heads(i) for i in (1, 2, 3)])
    result = _run_stub(
        tmp_path, 2, lambda call: _uniform(2.0), heads=heads,
    )
    cell = result["frames"][1]["cells"][0]
    assert cell["vx"] is None and cell["vy"] is None
    assert cell["speed_var"] is None and cell["pressure"] is None
    assert result["frames"][1]["cells"][1]["vx"] == 1.0


def test_heads_outside_cells_or_frame_are_ignored(tmp_path: Path) -> None:
    """셀 밖·화면 밖 머리는 결과를 바꾸지 않고 오류도 없다.

    (200, 10): row −1. (60, 44): col 1 (셀 없음). (−5, 50)·(300, 50):
    화면 밖. 이 점들 자리 흐름은 50 px라 섞이면 vx가 크게 바뀐다.
    """
    def make(call: int) -> np.ndarray:
        flow = _uniform(2.0)
        flow[:20, 190:, 0] = 50.0
        flow[38:51, 54:67, 0] = 50.0
        return flow

    extra = np.array(
        [[200.0, 10.0], [60.0, 44.0], [-5.0, 50.0], [300.0, 50.0]]
    )
    heads = [np.vstack([h, extra]) for h in _heads(2)]
    result = _run_stub(tmp_path, 2, make, heads=heads)
    for frame in result["frames"]:
        assert [c["vx"] for c in frame["cells"]] == [1.0, 1.0, None, 1.0]


def test_no_heads_at_all_gives_null_flow(tmp_path: Path) -> None:
    """모든 초 머리 0개면 vx 전부 null, inflow null, 파일은 정상이다."""
    heads = [np.empty((0, 2)) for _ in range(2)]
    result = _run_stub(
        tmp_path, 2, lambda call: _uniform(2.0), heads=heads,
    )
    for frame in result["frames"]:
        assert frame["inflow_ratio"] is None
        assert all(c["vx"] is None for c in frame["cells"])
        assert [c["pressure"] for c in frame["cells"]] == [
            None, None, 0, None,
        ]


def test_rejects_heads_length_not_matching_frames(tmp_path: Path) -> None:
    """len(heads) ≠ 프레임 수면 ValueError이고 출력 파일이 없다."""
    video, timeline_in, _ = _prepare(tmp_path, [2, 2])
    out = tmp_path / "out" / "o.json"
    with pytest.raises(ValueError, match="heads"):
        analyze_video(
            video, timeline_in, out, FarnebackEstimator(),
            **_head_kw(2, {"heads": _heads(3)}),
        )
    assert not out.exists()


@pytest.mark.parametrize("bad", [
    np.array([[np.nan, 1.0]]), np.zeros((1, 3)), np.zeros(2),
])
def test_rejects_bad_heads_entry(tmp_path: Path, bad: np.ndarray) -> None:
    """heads[t]가 유한한 (N, 2)가 아니면 ValueError다."""
    video, timeline_in, _ = _prepare(tmp_path, [2, 2])
    heads = _heads(2)
    heads[1] = bad
    with pytest.raises(ValueError, match="heads"):
        analyze_video(
            video, timeline_in, tmp_path / "o.json", FarnebackEstimator(),
            **_head_kw(2, {"heads": heads}),
        )


@pytest.mark.parametrize(
    "bad", [np.zeros((2, 3)), np.full((3, 3), np.nan)],
    ids=["shape", "nan"],
)
def test_rejects_bad_head_plane(tmp_path: Path, bad: np.ndarray) -> None:
    """h_head가 유한한 (3, 3)이 아니면 영상을 열기 전에 ValueError다.

    시작 프레임을 하나도 못 읽어도 NaN 행렬이 통과하지 않는다.
    출력 파일도 만들지 않는다.
    """
    video, timeline_in, _ = _prepare(tmp_path, [2])
    out = tmp_path / "o.json"
    with pytest.raises(ValueError, match="h_head"):
        analyze_video(
            video, timeline_in, out, FarnebackEstimator(),
            **_head_kw(1, {"h_head": bad}),
        )
    assert not out.exists()


def test_head_points_are_not_written(tmp_path: Path) -> None:
    """출력 프레임·셀 키 집합은 입력과 같고 폴더에는 파일 1개뿐이다.

    머리 점은 메모리로만 받고 파일에 남기지 않는다 (규격 9절 4번).
    """
    result, data, out_dir = _run(tmp_path, [2, 2])
    assert set(result) == set(data)
    assert set(result["meta"]) == set(data["meta"])
    for frame, before in zip(result["frames"], data["frames"]):
        assert set(frame) == set(before)
        for cell, old in zip(frame["cells"], before["cells"]):
            assert set(cell) == set(old)
    assert [p.name for p in out_dir.iterdir()] == ["SYN_001.json"]
