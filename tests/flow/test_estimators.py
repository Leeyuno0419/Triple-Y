"""S1 seam: FlowEstimator.estimate 시험.

합성 질감 영상을 알려진 정수 px만큼 평행 이동해 두 프레임을 만들고,
추정 흐름의 내부 중앙값이 그 이동량과 맞는지 본다.
기대값은 알고리즘을 다시 돌려 얻지 않고, 이동량 자체에서 가져온다.
"""
from __future__ import annotations

import cv2
import numpy as np
import pytest

from src.flow.estimators import DisEstimator, FarnebackEstimator

SEED = 0
SHIFT_X = 3   # 오른쪽 이동 = +x
SHIFT_Y = -2  # 위쪽 이동 = -y
BORDER = 24   # np.roll 이음매와 경계 효과를 피하려고 가장자리를 뺀다


def _texture(h: int, w: int, seed: int = SEED) -> np.ndarray:
    """고정 시드의 매끄러운 무작위 질감 BGR uint8 영상을 만든다."""
    rng = np.random.default_rng(seed)
    noise = rng.standard_normal((h, w)).astype(np.float32)
    smooth = cv2.GaussianBlur(noise, (0, 0), sigmaX=2.0)
    smooth = (smooth - smooth.min()) / (smooth.max() - smooth.min())
    gray = (smooth * 255).astype(np.uint8)
    return np.dstack([gray, gray, gray])


def _shifted_pair(
    h: int, w: int, dx: int, dy: int
) -> tuple[np.ndarray, np.ndarray]:
    """질감을 (dx, dy) px 만큼 옮긴 (이전, 다음) 프레임 쌍을 만든다."""
    prev = _texture(h, w)
    nxt = np.roll(prev, shift=(dy, dx), axis=(0, 1))
    return prev, nxt


def _interior_median(
    flow: np.ndarray, border: int = BORDER
) -> tuple[float, float]:
    """가장자리를 뺀 내부 흐름의 (x, y) 중앙값을 구한다."""
    inner = flow[border:-border, border:-border]
    return float(np.median(inner[..., 0])), float(np.median(inner[..., 1]))


# Farneback·DIS 허용 오차 0.5 px.
# 두 추정기는 원본 해상도에서 바로 계산하므로 배율 복원 경로가 없다.
# 잡을 오류는 부호 뒤집힘과 x·y 축 뒤바뀜이다.
# 변이 검사(2026-11-09) 결과, 이동 (+3, -2) px 에서:
#   정상: 차이 0.001 px 이하
#   부호 뒤집힘: 차이 x 6.0, y 4.0 px
#   축 뒤바뀜: 차이 x 5.0, y 5.0 px
# 0.5 px 는 정상 오차보다 충분히 크고, 두 변이보다 훨씬 작다.
TOL_CV_PX = 0.5


def test_farneback_recovers_known_shift_in_px() -> None:
    """Farneback: (H, W, 2) float32, px 단위, 오른쪽 이동이 +x 로 나온다."""
    prev, nxt = _shifted_pair(128, 160, SHIFT_X, SHIFT_Y)
    flow = FarnebackEstimator().estimate(prev, nxt)
    assert flow.shape == (128, 160, 2)
    assert flow.dtype == np.float32
    mx, my = _interior_median(flow)
    assert abs(mx - SHIFT_X) < TOL_CV_PX
    assert abs(my - SHIFT_Y) < TOL_CV_PX


def test_dis_recovers_known_shift_in_px() -> None:
    """DIS: (H, W, 2) float32, px 단위, 오른쪽 이동이 +x 로 나온다."""
    prev, nxt = _shifted_pair(128, 160, SHIFT_X, SHIFT_Y)
    flow = DisEstimator().estimate(prev, nxt)
    assert flow.shape == (128, 160, 2)
    assert flow.dtype == np.float32
    mx, my = _interior_median(flow)
    assert abs(mx - SHIFT_X) < TOL_CV_PX
    assert abs(my - SHIFT_Y) < TOL_CV_PX


# RAFT 허용 오차 1.0 px.
# 작업 해상도 오차가 원본으로 되돌릴 때 배율(최대 2배)만큼 커진다.
# 변이 검사(2026-11-09) 결과, 이동 (+8, -6) px 에서:
#   정상: 차이 x 0.41, y 0.02 px
#   배율 복원 누락: 차이 x 3.80, y 2.01 px
#   x·y 배율 뒤바뀜: 차이 x 1.69, y 1.98 px
# 1.0 px 는 정상 오차보다 크고, 모든 변이를 두 축에서 잡는다.
TOL_RAFT_PX = 1.0


def _raft_small(work_hw: tuple[int, int]) -> object:
    """CPU raft_small 추정기를 만든다. 가중치를 못 받으면 시험을 건너뛴다."""
    pytest.importorskip("torch")
    from src.flow.estimators import RaftEstimator

    try:
        return RaftEstimator(size="small", device="cpu", work_hw=work_hw)
    except OSError as exc:  # 내려받기 실패 (URLError 는 OSError 의 하위형)
        pytest.skip(f"RAFT 가중치를 내려받지 못함: {exc}")


@pytest.mark.slow
def test_raft_small_restores_original_px_after_downscale() -> None:
    """RAFT: 작업 해상도로 줄여 추론한 뒤 원본 px 단위·모양으로 되돌린다.

    원본 192×320 을 작업 해상도 128×160 으로 줄이면 배율이
    y 1.5, x 2.0 으로 달라서, 배율 복원 누락이나 x·y 배율 뒤바뀜이
    모두 드러난다. 이동량 (+8, -6) px 은 작업 해상도에서 (+4, -4) px 다.
    """
    est = _raft_small((128, 160))
    dx, dy = 8, -6
    prev, nxt = _shifted_pair(192, 320, dx, dy)
    flow = est.estimate(prev, nxt)
    assert flow.shape == (192, 320, 2)
    assert flow.dtype == np.float32
    mx, my = _interior_median(flow, border=40)
    assert abs(mx - dx) < TOL_RAFT_PX
    assert abs(my - dy) < TOL_RAFT_PX


@pytest.mark.parametrize(
    "work_hw",
    [(130, 160), (128, 164), (120, 160), (128, 120)],
    ids=["h-not-mult8", "w-not-mult8", "h-below-128", "w-below-128"],
)
def test_raft_rejects_invalid_work_hw(work_hw: tuple[int, int]) -> None:
    """RAFT: 작업 해상도가 8의 배수가 아니거나 128 미만이면 거부한다."""
    pytest.importorskip("torch")
    from src.flow.estimators import RaftEstimator

    with pytest.raises(ValueError):
        RaftEstimator(size="small", device="cpu", work_hw=work_hw)
