"""흐름 추정기 어댑터. 모든 추정기는 같은 입출력을 쓴다."""
from __future__ import annotations

from typing import Protocol

import cv2
import numpy as np


class FlowEstimator(Protocol):
    """두 프레임 사이 광학 흐름을 구하는 추정기의 공통 인터페이스."""

    name: str

    def estimate(
        self, prev_bgr: np.ndarray, next_bgr: np.ndarray
    ) -> np.ndarray:
        """BGR uint8 프레임 2장의 흐름을 (H, W, 2) float32, px 단위로 돌려준다.
        """
        ...


def _to_gray(img_bgr: np.ndarray) -> np.ndarray:
    """BGR 프레임을 회색조 uint8로 바꾼다."""
    return cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)


class FarnebackEstimator:
    """OpenCV Farneback 흐름. 학습하지 않는 기준선이다."""

    def __init__(self) -> None:
        """기본 파라미터(proposal-detail 3.4 시작값, 가정)로 만든다."""
        self.name = "farneback-cv2"

    def estimate(
        self, prev_bgr: np.ndarray, next_bgr: np.ndarray
    ) -> np.ndarray:
        """Farneback 흐름을 px 단위로 돌려준다."""
        # 인자 순서: prev, next, flow, pyr_scale, levels, winsize,
        # iterations, poly_n, poly_sigma, flags. 값은 시작값 (가정)
        flow = cv2.calcOpticalFlowFarneback(
            _to_gray(prev_bgr), _to_gray(next_bgr), None,
            0.5, 3, 15, 3, 5, 1.2, 0,
        )
        return flow.astype(np.float32)


class DisEstimator:
    """OpenCV DIS 흐름. 학습하지 않는 기준선이다."""

    def __init__(
        self, preset: int = cv2.DISOPTICAL_FLOW_PRESET_MEDIUM
    ) -> None:
        """DIS 프리셋을 정해 만든다.

        TUB CrowdFlow DIS4·DIS2와의 대응은 (확인 필요).
        """
        self.name = f"dis-cv2-preset{preset}"
        self._dis = cv2.DISOpticalFlow_create(preset)

    def estimate(
        self, prev_bgr: np.ndarray, next_bgr: np.ndarray
    ) -> np.ndarray:
        """DIS 흐름을 px 단위로 돌려준다."""
        return self._dis.calc(_to_gray(prev_bgr), _to_gray(next_bgr), None)


class RaftEstimator:
    """torchvision RAFT 흐름. 사전학습 가중치를 쓴다."""

    def __init__(
        self,
        size: str = "large",
        device: str | None = None,
        work_hw: tuple[int, int] = (544, 960),
        num_flow_updates: int = 12,
    ) -> None:
        """모델을 만든다.

        work_hw는 추론 해상도(높이, 너비)이며 8의 배수, 128 이상이어야 한다.
        device가 None이면 CUDA가 있으면 "cuda", 없으면 "cpu"를 쓴다.
        """
        import torch
        from torchvision.models.optical_flow import (
            Raft_Large_Weights, Raft_Small_Weights, raft_large, raft_small,
        )

        if work_hw[0] % 8 or work_hw[1] % 8 or min(work_hw) < 128:
            raise ValueError("work_hw는 8의 배수이고 128 이상이어야 한다")
        if size == "large":
            weights, builder = Raft_Large_Weights.DEFAULT, raft_large
        elif size == "small":
            weights, builder = Raft_Small_Weights.DEFAULT, raft_small
        else:
            raise ValueError(f"알 수 없는 size: {size}")
        # 계획 5.1 초안은 기본값이 "cuda"였다. CPU 전용 PC에서도 바로
        # 돌도록 자동 선택으로 바꿨다 (2026-11-09 결정).
        if device is None:
            device = "cuda" if torch.cuda.is_available() else "cpu"

        self._preprocess = weights.transforms()
        self._model = builder(weights=weights).to(device).eval()
        self.name = f"raft_{size}-pretrained-{weights}"
        self._device = device
        self._work_hw = work_hw
        self._iters = num_flow_updates
        self._torch = torch

    def _to_tensor(
        self, img_bgr: np.ndarray
    ) -> "torch.Tensor":  # noqa: F821
        """BGR 프레임을 작업 해상도의 (1, 3, h, w) uint8 RGB 텐서로 바꾼다."""
        h, w = self._work_hw
        rgb = cv2.cvtColor(cv2.resize(img_bgr, (w, h)), cv2.COLOR_BGR2RGB)
        tensor = self._torch.from_numpy(rgb).permute(2, 0, 1)
        return tensor.unsqueeze(0).contiguous()

    def estimate(
        self, prev_bgr: np.ndarray, next_bgr: np.ndarray
    ) -> np.ndarray:
        """RAFT 흐름을 원본 해상도 px 단위로 돌려준다."""
        h0, w0 = prev_bgr.shape[:2]
        h, w = self._work_hw
        a, b = self._preprocess(
            self._to_tensor(prev_bgr), self._to_tensor(next_bgr)
        )
        with self._torch.no_grad():
            flows = self._model(
                a.to(self._device), b.to(self._device),
                num_flow_updates=self._iters,
            )
        # 마지막 반복 결과
        flow = flows[-1][0].permute(1, 2, 0).cpu().numpy()
        flow = cv2.resize(flow, (w0, h0), interpolation=cv2.INTER_LINEAR)
        flow[..., 0] *= w0 / w  # 작업 해상도 px → 원본 px
        flow[..., 1] *= h0 / h
        return flow.astype(np.float32)
