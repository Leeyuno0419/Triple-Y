"""학습용 합성(더미) 밀도 시계열. 실제 timeline 로그가 없을 때만 쓴다.

현실처럼 보이는 군중 변화를 흉내 낸다.
    - 행사·열차 도착 같은 '파동'이 여러 번 온다: 서서히 늘고(상승) → 한동안 유지(정점) → 서서히 줄어든다(해소).
    - 파동마다 구역 안의 위치와 이동 방향이 다르다 (덩어리가 셀을 가로질러 움직인다).
    - 파동이 시작되는 시각·크기·길이는 무작위라서 미리 알 수 없다 (맞히기 쉬운 문제로 만들지 않는다).
    - 인원 추정 오차(P2PNet 5장 평균의 흔들림)를 흉내 낸 잡음을 더하고, 규격대로 소수 2자리로 반올림한다.

※ 이 데이터로 얻은 점수는 코드가 돌아가는지 확인하는 용도이며 실제 영상의 성능이 아니다.
   실제 성능은 data/processed/timeline/*.json 으로 다시 학습·평가해서 확인한다.
"""
from __future__ import annotations

from typing import List

import numpy as np

PEAK_MAX = 6.5       # 파동 하나의 최대 밀도(명/㎡). 기획서 3.2 의 "심각" 수준(약 6)을 조금 넘는다


def _smoothstep(x: np.ndarray) -> np.ndarray:
    """0 → 1 로 부드럽게 올라가는 곡선 (x 는 0~1 로 잘라서 쓴다)."""
    x = np.clip(x, 0.0, 1.0)
    return x * x * (3.0 - 2.0 * x)


def _wave_amplitude(t: np.ndarray, onset: float, rise: float, hold: float, fall: float, peak: float) -> np.ndarray:
    """파동 하나의 시간 모양: onset 부터 rise 초 동안 오르고, hold 초 유지하고, fall 초 동안 내려간다."""
    up = _smoothstep((t - onset) / rise)
    down = _smoothstep((t - onset - rise - hold) / fall)
    return peak * up * (1.0 - down)


def make_synthetic_density(
    rng: np.random.Generator,
    rows: int = 4,
    cols: int = 6,
    duration_s: int = 1200,
    noise_rel: float = 0.10,
    noise_abs: float = 0.03,
) -> np.ndarray:
    """합성 밀도 기록 한 개를 만든다. 반환값: (duration_s, rows*cols), 명/㎡, 열 순서는 행 우선(row-major).

    noise_rel: 값에 비례하는 잡음(10% 면 값 4 에 ±0.4 정도). noise_abs: 값과 무관한 잡음.
    """
    t = np.arange(duration_s, dtype=float)
    rr, cc = np.mgrid[0:rows, 0:cols]

    density = np.zeros((duration_s, rows, cols))
    density += rng.uniform(0.05, 0.4)                                   # 평소의 옅은 밀도
    slow = rng.uniform(0.0, 0.25) * np.sin(2 * np.pi * t / rng.uniform(400, 900) + rng.uniform(0, 2 * np.pi))
    density += slow[:, None, None]                                      # 천천히 출렁이는 바닥 수준

    for _ in range(int(rng.integers(2, 6))):                            # 파동 2~5개
        amp = _wave_amplitude(
            t,
            onset=rng.uniform(0, duration_s * 0.85),
            rise=rng.uniform(60, 240),
            hold=rng.uniform(30, 300),
            fall=rng.uniform(60, 240),
            peak=rng.uniform(1.0, PEAK_MAX),
        )
        r0, c0 = rng.uniform(0, rows - 1), rng.uniform(0, cols - 1)     # 덩어리 시작 위치(셀 단위)
        vr, vc = rng.normal(0, 0.012), rng.normal(0, 0.02)              # 이동 속도(셀/초)
        sigma = rng.uniform(1.0, 2.2)                                   # 덩어리 퍼짐
        for k in range(duration_s):
            dist2 = (rr - (r0 + vr * k)) ** 2 + (cc - (c0 + vc * k)) ** 2
            density[k] += amp[k] * np.exp(-dist2 / (2.0 * sigma ** 2))

    flat = density.reshape(duration_s, rows * cols)
    flat = flat * (1.0 + noise_rel * rng.standard_normal(flat.shape)) + noise_abs * rng.standard_normal(flat.shape)
    return np.round(np.clip(flat, 0.0, None), 2)


def make_synthetic_series(
    n_series: int, seed: int, rows: int = 4, cols: int = 6, duration_s: int = 1200
) -> List[np.ndarray]:
    """합성 기록 n_series 개를 만든다. 같은 seed 면 항상 같은 결과다 (재현성)."""
    root = np.random.SeedSequence(seed)
    return [
        make_synthetic_density(np.random.default_rng(s), rows, cols, duration_s)
        for s in root.spawn(n_series)
    ]
