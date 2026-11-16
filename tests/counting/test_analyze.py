"""통합 분석: 인원 세기가 흐름에 넘기는 머리 점 프레임이 흐름 모듈 규칙(round(t·fps))과 맞는지 확인한다."""
from __future__ import annotations

import numpy as np

from src.counting.run_density import frame_plan


def test_centre_frame_matches_flow_rule() -> None:
    """정각 프레임은 round(t·fps)이고, 그 프레임은 같은 초의 평균에도 쓰인다."""
    fps, n_frames = 29.97, 300
    offsets = np.linspace(-0.4, 0.4, 5)
    need, centre = frame_plan(9, fps, n_frames, offsets)
    assert centre == [round(t * fps) for t in range(9)]
    for t, f in enumerate(centre):
        assert t in need[f]


def test_frame_plan_clips_to_video() -> None:
    """영상 앞뒤 끝을 넘는 프레임은 안쪽으로 자른다."""
    need, centre = frame_plan(3, 30.0, 70, np.linspace(-0.4, 0.4, 5))
    assert min(need) == 0 and max(need) == 69
    assert centre == [0, 30, 60]
    assert all(len(ts) >= 1 for ts in need.values())
