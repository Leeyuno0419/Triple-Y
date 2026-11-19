"""flow_proxy 지표 함수 시험 (머리 점·정답 흐름 없이 재는 프레임 프록시).

합성 질감을 알려진 px만큼 옮긴 쌍과 손으로 만든 흐름장·마스크를 쓴다.
기대값은 이동량·상수에서 손으로 얻는다.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import cv2
import numpy as np
import pytest

from src.flow.flow_proxy import (
    frame_masks, main, photometric_ratio, static_noise_p95,
)

H, W = 96, 128
BORDER = 16


def _texture(h: int, w: int, seed: int = 0) -> np.ndarray:
    """고정 시드의 매끄러운 무작위 질감 회색조 uint8 영상."""
    rng = np.random.default_rng(seed)
    noise = rng.standard_normal((h, w)).astype(np.float32)
    smooth = cv2.GaussianBlur(noise, (0, 0), sigmaX=2.0)
    smooth = (smooth - smooth.min()) / (smooth.max() - smooth.min())
    return (smooth * 255).astype(np.uint8)


def _inner_mask() -> np.ndarray:
    """가장자리 BORDER px를 뺀 내부 마스크 (np.roll 이음매 제외)."""
    mask = np.zeros((H, W), dtype=bool)
    mask[BORDER:-BORDER, BORDER:-BORDER] = True
    return mask


def _const_flow(dx: float, dy: float) -> np.ndarray:
    """모든 화소가 (dx, dy) px인 흐름장."""
    flow = np.zeros((H, W, 2), dtype=np.float32)
    flow[..., 0], flow[..., 1] = dx, dy
    return flow


def test_photometric_ratio_low_for_true_flow_one_for_zero() -> None:
    """(+3, −2) 옮긴 쌍: 정확한 흐름은 < 0.05, 흐름 0은 1.0이다."""
    prev = _texture(H, W)
    nxt = np.roll(prev, shift=(-2, 3), axis=(0, 1))
    mask = _inner_mask()
    assert photometric_ratio(prev, nxt, _const_flow(3, -2), mask) < 0.05
    zero = photometric_ratio(prev, nxt, _const_flow(0, 0), mask)
    assert abs(zero - 1.0) < 1e-6


def test_static_noise_p95_per_frame_and_nan_for_empty_mask() -> None:
    """|흐름| 0.4 px, gap 2 → 0.2 px/프레임. 마스크가 비면 NaN이다."""
    flow = _const_flow(0.24, -0.32)  # |흐름| = 0.4 px
    mask = _inner_mask()
    assert abs(static_noise_p95(flow, mask, 2) - 0.2) < 1e-6
    empty = np.zeros((H, W), dtype=bool)
    assert math.isnan(static_noise_p95(flow, empty, 2))


def test_frame_masks_split_static_outside_and_moving_inside() -> None:
    """오른쪽 절반만 바뀌고 걷는 곳 = 오른쪽 절반이면 마스크가 갈린다.

    움직인 곳은 오른쪽(걷는 곳) 안에만, 정지는 왼쪽(걷는 곳 밖)에만
    있고 둘 다 비지 않는다. 경계에서 흐림(σ 3)이 번지는 띠는 어느
    쪽이어도 되므로 가운데 ±16 px는 보지 않는다.
    """
    prev = _texture(H, W)
    nxt = prev.copy()
    nxt[:, W // 2:] = _texture(H, W - W // 2, seed=1)
    walkable = np.zeros((H, W), dtype=bool)
    walkable[:, W // 2:] = True
    static, moving = frame_masks(prev, nxt, walkable)
    assert not moving[:, :W // 2].any()
    assert not static[:, W // 2:].any()
    assert static[:, :W // 2 - 16].all()
    assert moving[:, W // 2 + 16:].mean() > 0.5


def test_main_rejects_unopenable_video(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """열 수 없는 영상이면 ValueError이고 출력 파일이 생기지 않는다."""
    homography = tmp_path / "h.json"
    homography.write_text('{"walkable_polygon_px": []}', encoding="utf-8")
    out = tmp_path / "proxy.json"
    monkeypatch.setattr(sys, "argv", [
        "flow_proxy", "--video", str(tmp_path / "missing.mp4"),
        "--homography", str(homography), "--out", str(out),
    ])
    with pytest.raises(ValueError, match="영상을 열 수 없다"):
        main()
    assert not out.exists()
