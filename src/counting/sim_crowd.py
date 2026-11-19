"""군중이 불어나는 30초 시뮬레이션 영상과 그 timeline.json을 만든다 (등급 시연용, 합성).

실제 CCTV 배경(사람 없는 중앙값 화면) 위에 시뮬레이션 인원을 그리고, P2PNet 결과처럼 머리마다 점을 찍는다.
인원 위치는 지면 좌표(m)에서 움직이고 호모그래피로 화면에 옮긴다. 밀도·흐름 값은 그 위치에서 직접 센다
(models = "simulation"). 실제 검출 결과가 아니므로 영상에 "시뮬레이션"이라고 적는다.

인원은 세 무리다.
- 지나가는 사람: 길 위아래 양쪽에서 들어와 반대쪽으로 걸어 나간다. 붐빌수록 느려지지만 멈추지는 않는다.
- 가장자리로 빠져나가는 사람: 길 양쪽 통로를 따라 한 줄로 꾸준히 지나간다. 가운데가 막혀도 계속 빠져나간다.
- 머무는 사람: 가운데로 조금씩 모여 정체를 만든다. 가운데 밀도가 목표 곡선을 따르도록 자리를 정한다.
가장 붐비는 셀이 정상 → 주의 → 경계 → 심각 순으로 오른다. 군중이 출렁이는 움직임(난류)은 중간에 짧게 몇 번,
심각 구간에서는 계속 넣는다. 중간 난류는 밀도 3명/㎡ 미만인 곳에 두어 서버의 불안정 판정(밀도 3 이상)에는 걸리지 않는다.

속도 분산(speed_var)은 흐름 모듈과 같은 뜻이다: 셀 평균 속도가 최근 몇 초 동안 평균에서 벗어난 정도.
흐름 모듈은 30초 창을 쓰지만 영상이 30초뿐이라 여기서는 VAR_WINDOW_S초 창을 쓴다.

    python -m src.counting.sim_crowd --homography infra/homography/E04_022.json \
        --video data/processed/g0/E04_022.mp4 --out-video data/processed/sim/SIM_E04_022.mp4 \
        --out-timeline data/processed/timeline/sim_E04_022.json
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from src.counting.cells import build_cells, ground_to_image, image_to_ground
from src.predict.schema import SCHEMA_VERSION, validate_timeline

SEED = 7
FPS = 30
DURATION_S = 30
CELL_M = 2.0
CENTER_PX = (900, 720)                 # 가장 붐비게 할 곳 (영상 좌표)
AXIS_PX = ((940, 390), (960, 1080))    # 길 방향 (먼 쪽 → 카메라 쪽)
# 가운데 꼭대기 밀도(명/㎡) 목표: (초, 밀도). 완만하게 오른다. 오르는 빠르기가 갑자기 바뀌면
# 모여드는 속도가 출렁여 난류가 아닌데도 속도 분산이 커지기 때문이다
DENSITY_KNOTS = ((0, 1.4), (11, 3.2), (21, 5.0), (30, 7.6))
SPREAD_ALONG_M, SPREAD_ACROSS_M = 6.5, 6.0   # 가운데 붐비는 덩어리의 길 방향·폭 방향 크기
EDGE_SHARE = 0.8                       # 길 가장자리 밀도 / 길 가운데 밀도
FAR_DENSITY = 1.3                      # 가운데에서 먼 곳의 밀도(명/㎡)
PEAK_SCALE = 1.0                       # 가장 붐비는 셀이 목표 곡선에 맞도록 곱하는 보정값 (시드 7 기준)
HALF_ALONG_M, HALF_ACROSS_M = 9.0, 9.0  # 끝 시각 배치를 만드는 범위 (화면에 보이는 범위보다 넓게)

WALKER_FAR_DENSITY = 0.6               # 먼 곳에서 지나가는 사람이 차지하는 밀도(명/㎡, 두 방향 합)
SPAWN_M, PREROLL_S = 22.0, 60.0        # 지나가는 사람이 출발하는 거리와 0초 전에 미리 돌리는 시간
LANE_SHIFT_M = 1.3                     # 우측통행: 방향마다 길 폭 방향으로 치우치는 거리
WALK_FAST, WALK_SLOW, WALK_DROP = 1.1, 0.2, 0.45   # 보행 속도(m/s): 한산할 때, 꽉 찼을 때, 밀도 1명/㎡마다 줄어드는 양
LANE_BETAS = (3.5, 4.3, 5.1)           # 가장자리 통행 줄의 폭 방향 자리(m). 길 양쪽에 세 줄씩, 한쪽은 올라가고 한쪽은 내려간다
LANE_CLEAR = (3.1, 5.5)                # 머무는 사람이 서지 않는 통로 (폭 방향 범위 m)
LANE_SPEED, LANE_GAP_M = 0.8, 1.25     # 통행 줄의 걷는 속도(m/s)와 앞사람과의 간격(m)

# 난류: (시작 초, 끝 초, 길 방향 위치 m, 폭 방향 위치 m, 반경 m, 성긴 곳에서만 일어나는가).
# 앞의 셋은 짧게 지나가고 밀도가 TURB_SPARSE_BELOW보다 낮은 곳에서만 출렁인다. 마지막은 심각 구간 내내 이어진다
TURBULENCE = ((1.5, 4.0, 0.0, 0.0, 3.5, True), (10.5, 13.0, 5.5, -5.0, 3.2, True), (15.5, 18.0, -6.0, 5.0, 3.2, True),
              (21.5, 99.0, 0.0, 0.0, 5.0, False))
TURB_SPARSE_BELOW = 2.7
TURB_AMP_M = 0.08                     # 출렁임 파동 하나의 진폭
VAR_WINDOW_S = 3                       # 속도 분산을 재는 창 (초)
PERSON_H_M, HEIGHT_FACTOR = 1.62, 0.88  # 머리 중심 높이, 카메라가 내려다보는 각도 때문에 줄어드는 비율
FONT = "C:/Windows/Fonts/malgunbd.ttf"


def knot_value(t: np.ndarray | float) -> np.ndarray:
    """목표 밀도 곡선. 꺾이는 점을 3초 폭으로 다듬어 속도가 갑자기 바뀌지 않게 한다. 0초 전은 0초 값이다."""
    ts = np.linspace(-2, DURATION_S + 2, 2000)
    raw = np.interp(ts, [k[0] for k in DENSITY_KNOTS], [k[1] for k in DENSITY_KNOTS])
    win = int(3.0 / (ts[1] - ts[0]))
    smooth = np.convolve(np.pad(raw, win, mode="edge"), np.ones(win) / win, mode="same")[win:-win]
    return np.interp(t, ts, smooth) * PEAK_SCALE


def across_shape(beta: np.ndarray) -> np.ndarray:
    """폭 방향 밀도 모양. 길 가운데가 1, 가장자리는 EDGE_SHARE."""
    return EDGE_SHARE + (1 - EDGE_SHARE) * np.exp(-(beta / SPREAD_ACROSS_M) ** 2)


def along_density(alpha: np.ndarray, peak: float, far: float = FAR_DENSITY) -> np.ndarray:
    """길 방향 밀도(명/㎡). 가운데는 peak, 먼 곳은 far."""
    bump = np.exp(-(alpha / SPREAD_ALONG_M) ** 2)
    return peak * bump + far * (1 - bump)


def walk_speed(rho: np.ndarray) -> np.ndarray:
    """밀도에 따른 보행 속도(m/s). 붐빌수록 느려지지만 꽉 차도 WALK_SLOW로 사람 사이를 빠져나간다."""
    return np.clip(1.5 - WALK_DROP * np.asarray(rho, float), WALK_SLOW, WALK_FAST)


def simulate_walkers(rng: np.random.Generator) -> tuple[np.ndarray, np.ndarray]:
    """지나가는 사람들의 (길 방향 α, 폭 방향 β)를 프레임마다 계산한다. 모양은 각각 (프레임 수, 인원 수)."""
    width = 2 * HALF_ACROSS_M
    flux = WALKER_FAR_DENSITY / 2 * float(walk_speed(FAR_DENSITY)) * width * float(
        across_shape(np.linspace(-HALF_ACROSS_M, HALF_ACROSS_M, 200)).mean())      # 방향마다 초당 들어오는 인원
    span = PREROLL_S + DURATION_S
    # 들어오는 시각과 폭 방향 자리를 고르게 편다 (완전 무작위로 뽑으면 우연히 뭉친 무리가 셀 밀도를 크게 흔든다)
    grid_b = np.linspace(-HALF_ACROSS_M, HALF_ACROSS_M, 2000)
    cdf = np.cumsum(across_shape(grid_b))
    cdf /= cdf[-1]
    starts, dirs, betas = [], [], []
    for direction in (1, -1):
        n = int(round(flux * span))
        starts.append((np.arange(n) + rng.uniform(0.2, 0.8, n)) / n * span - PREROLL_S)
        quantile = (np.arange(n) * 0.6180339887 + rng.random()) % 1.0
        b = np.interp(quantile, cdf, grid_b) + rng.normal(0, 0.15, n)
        betas.append(np.clip(b - direction * LANE_SHIFT_M, -HALF_ACROSS_M, HALF_ACROSS_M))
        dirs.append(np.full(n, direction))
    start, direction, beta = np.concatenate(starts), np.concatenate(dirs), np.concatenate(betas)
    n = len(start)
    pace = rng.normal(1.0, 0.1, n).clip(0.75, 1.25)   # 사람마다 걸음 빠르기
    wander_amp, wander_w = rng.uniform(0.0, 0.35, n), rng.uniform(0.2, 0.5, n)
    wander_ph = rng.uniform(0, 2 * np.pi, n)
    alpha = -direction * SPAWN_M
    out_a = np.empty((DURATION_S * FPS, n))
    out_b = np.empty((DURATION_S * FPS, n))
    dt = 1 / FPS
    for step in range(int(-PREROLL_S * FPS), DURATION_S * FPS):
        t = step * dt
        b_now = beta + wander_amp * np.sin(wander_w * t + wander_ph)
        rho = along_density(alpha, float(knot_value(max(t, 0.0)))) * across_shape(b_now)
        alpha = alpha + np.where(start <= t, direction * pace * walk_speed(rho) * dt, 0.0)
        if step >= 0:
            out_a[step], out_b[step] = alpha, b_now
    return out_a, out_b


def simulate_lanes(rng: np.random.Generator) -> tuple[np.ndarray, np.ndarray]:
    """가장자리 통로를 따라 빠져나가는 사람들의 (α, β)를 프레임마다 계산한다. 모양은 각각 (프레임 수, 인원 수).

    간격과 속도가 고르므로 셀에 들어 있는 인원이 거의 일정하다. 그래서 셀 평균 속도가 흔들리지 않는다.
    """
    t = np.arange(DURATION_S * FPS) / FPS
    reach = SPAWN_M + LANE_SPEED * DURATION_S
    alphas, betas = [], []
    for side in (-1, 1):                              # 폭 방향 음수 쪽은 카메라 쪽으로, 양수 쪽은 먼 쪽으로 걷는다
        direction = -side
        for lane_beta in LANE_BETAS:
            n = int(reach * 2 / LANE_GAP_M)
            start = -direction * reach + direction * (np.arange(n) * LANE_GAP_M + rng.uniform(0, LANE_GAP_M))
            start = start + rng.normal(0, 0.12, n)
            sway = 0.1 * np.sin(rng.uniform(0.3, 0.6, n) * t[:, None] + rng.uniform(0, 2 * np.pi, n))
            alphas.append(start + direction * LANE_SPEED * t[:, None] + sway)
            betas.append(side * lane_beta + rng.normal(0, 0.1, n)
                         + 0.12 * np.sin(rng.uniform(0.3, 0.6, n) * t[:, None] + rng.uniform(0, 2 * np.pi, n)))
    return np.concatenate(alphas, axis=1), np.concatenate(betas, axis=1)


def walker_share(alpha: np.ndarray, beta: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """지나가는 사람이 차지하는 밀도(길 가운데 기준)를 초 단위로 다듬어 (가운데, 먼 곳) 프레임별로 돌려준다."""
    weight = 1 / across_shape(beta)
    lat = np.abs(beta) < 3.0
    mid = (weight * (lat & (np.abs(alpha) < 2.5))).sum(axis=1) / (5.0 * 6.0)
    far = (weight * (lat & (np.abs(alpha) > 8) & (np.abs(alpha) < 14))).sum(axis=1) / (12.0 * 6.0)
    kernel = np.ones(3 * FPS) / (3 * FPS)
    smooth = [np.convolve(np.pad(v, 3 * FPS, mode="edge"), kernel, mode="same")[3 * FPS:-3 * FPS] for v in (mid, far)]
    return smooth[0], smooth[1]


def final_layout(rng: np.random.Generator, peak: float, far: float) -> np.ndarray:
    """머무는 사람들의 끝 시각 배치 (길 방향 α, 폭 방향 β, 단위 m).

    목표 밀도에 비례해 자리를 뽑되, 서로 겹치지 않게 최소 간격(밀도가 높을수록 좁다)을 지킨다.
    """
    box = np.array([HALF_ALONG_M, HALF_ACROSS_M])
    grid_a, grid_b = np.meshgrid(np.linspace(-box[0], box[0], 400), np.linspace(-box[1], box[1], 400))
    open_floor = (np.abs(grid_b) < LANE_CLEAR[0]) | (np.abs(grid_b) > LANE_CLEAR[1])
    n_target = int((along_density(grid_a, peak, far) * across_shape(grid_b) * open_floor).mean() * 4 * box[0] * box[1])
    pts: list[np.ndarray] = []
    grid: dict[tuple[int, int], list[int]] = {}
    while len(pts) < n_target:
        p = rng.uniform(-box, box)
        r = float(along_density(p[0], peak, far) * across_shape(p[1]))
        if LANE_CLEAR[0] < abs(p[1]) < LANE_CLEAR[1] or rng.random() > r / max(peak, far):
            continue
        key = (int(p[0] // 0.7), int(p[1] // 0.7))
        near = [j for da in (-1, 0, 1) for db in (-1, 0, 1) for j in grid.get((key[0] + da, key[1] + db), [])]
        if near and np.min(np.linalg.norm(np.array([pts[j] for j in near]) - p, axis=1)) < 0.62 / np.sqrt(r):
            continue
        grid.setdefault(key, []).append(len(pts))
        pts.append(p)
    return np.array(pts)


def simulate_stayers(layout: np.ndarray, peaks: np.ndarray, fars: np.ndarray) -> np.ndarray:
    """머무는 사람들의 길 방향 자리를 프레임마다 계산한다 (폭 방향 자리는 그대로). 모양은 (프레임 수, 인원 수).

    인원마다 가운데부터 자기 자리까지의 누적 인원이 늘 같도록 자리를 정한다.
    그래서 가운데 밀도가 오르는 만큼 바깥 사람들이 안으로 조금씩 밀려든다.
    """
    axis = np.arange(0, 160, 0.02)
    mass = np.interp(np.abs(layout[:, 0]), axis, np.cumsum(along_density(axis, peaks[-1], fars[-1])) * 0.02)
    along = np.stack([np.interp(mass, np.cumsum(along_density(axis, p, f)) * 0.02, axis)
                      for p, f in zip(peaks, fars)])
    return along * np.sign(layout[:, 0])


class Scene:
    """구역 설정(호모그래피·바닥 다각형·셀)과 시뮬레이션 좌표축."""

    def __init__(self, cfg: dict[str, object], size: tuple[int, int]) -> None:
        self.h = np.array(cfg["H_img_to_ground"])
        self.size = size
        self.poly = np.asarray(cfg["walkable_polygon_px"], np.float32)
        self.cells = build_cells(self.h, cfg["walkable_polygon_px"], size, CELL_M)
        ground = image_to_ground(self.h, self.poly.astype(float))
        self.origin = np.floor(ground.min(axis=0) / CELL_M) * CELL_M
        self.index = {(c["row"], c["col"]): i for i, c in enumerate(self.cells)}
        self.areas = np.array([c["walkable_area_m2"] for c in self.cells])
        a0, a1 = image_to_ground(self.h, np.array(AXIS_PX, float))
        self.u = (a1 - a0) / np.linalg.norm(a1 - a0)
        self.w = np.array([-self.u[1], self.u[0]])
        # 가운데는 CENTER_PX가 들어 있는 셀의 한가운데로 맞춘다 (그 셀이 가장 붐비게)
        g = image_to_ground(self.h, [CENTER_PX])[0]
        self.center = (np.floor((g - self.origin) / CELL_M) + 0.5) * CELL_M + self.origin

    def to_ground(self, alpha: np.ndarray, beta: np.ndarray) -> np.ndarray:
        """(길 방향, 폭 방향) 자리를 지면 좌표(m)로 바꾼다."""
        return self.center + alpha[..., None] * self.u + beta[..., None] * self.w

    def cell_of(self, ground: np.ndarray, px: np.ndarray) -> np.ndarray:
        """인원마다 들어 있는 셀 번호(meta.cells 순서). 셀 밖이거나 바닥 다각형 밖이면 -1."""
        rc = np.floor((ground - self.origin) / CELL_M).astype(int)
        out = np.full(len(ground), -1)
        for k, (col, row) in enumerate(rc):
            i = self.index.get((row, col))
            if i is not None and cv2.pointPolygonTest(self.poly, (float(px[k, 0]), float(px[k, 1])), False) >= 0:
                out[k] = i
        return out


def simulate(scene: Scene, rng: np.random.Generator) -> np.ndarray:
    """세 무리를 합쳐 프레임마다 인원 지면 좌표를 계산한다. 돌려주는 값: (프레임 수, 인원 수, 2) m."""
    t = np.arange(DURATION_S * FPS) / FPS
    walk_a, walk_b = simulate_walkers(rng)
    mid, far = walker_share(walk_a, walk_b)
    peaks = np.maximum(knot_value(t) - mid, 0.3)          # 머무는 사람이 채울 몫 = 목표 − 지나가는 사람
    fars = np.maximum(FAR_DENSITY - far, 0.3)
    layout = final_layout(rng, float(peaks[-1]), float(fars[-1]))
    stay_a = simulate_stayers(layout, peaks, fars)
    lane_a, lane_b = simulate_lanes(rng)
    alpha = np.concatenate([walk_a, lane_a, stay_a], axis=1)
    beta = np.concatenate([walk_b, lane_b, np.broadcast_to(layout[:, 1], stay_a.shape)], axis=1)
    pos = scene.to_ground(alpha, beta)
    # 난류: 곳마다 파장 2.5~4.5 m, 주기 2.2~3.6 초의 파동 4개로 군중이 함께 출렁인다
    target = np.stack([along_density(a, float(k)) for a, k in zip(alpha, knot_value(t))]) * across_shape(beta)
    for t0, t1, a0, b0, radius, sparse_only in TURBULENCE:
        gain_t = np.clip((t - t0) / 0.8, 0, 1) * np.clip((t1 - t) / 0.8, 0, 1)
        gain_x = np.exp(-((alpha - a0) ** 2 + (beta - b0) ** 2) / radius ** 2)
        if sparse_only:
            gain_x = gain_x * np.clip((TURB_SPARSE_BELOW - target) / 0.4, 0, 1)
        for _ in range(4):
            ang, lam, period = rng.uniform(0, 2 * np.pi), rng.uniform(2.5, 4.5), rng.uniform(2.2, 3.6)
            q = 2 * np.pi / lam * np.array([np.cos(ang), np.sin(ang)])
            push = rng.uniform(0, 2 * np.pi)
            wave = np.sin(alpha * q[0] + beta * q[1] + rng.uniform(0, 2 * np.pi) - 2 * np.pi / period * t[:, None])
            pos = pos + (TURB_AMP_M * gain_t[:, None] * gain_x * wave)[..., None] * np.array([np.cos(push), np.sin(push)])
    return pos


def measure(scene: Scene, pos: np.ndarray, px: np.ndarray) -> list[dict[str, object]]:
    """인원 위치에서 초마다 셀 밀도·흐름 값을 세어 timeline frames를 만든다.

    밀도는 그 초 앞뒤 0.4초 안 5장의 평균, 속도는 앞뒤 0.5초 사이 이동 거리로 구한다.
    속도 분산은 셀 평균 속도의 최근 VAR_WINDOW_S초 값이 그 평균에서 벗어난 정도다 (표본 3개부터).
    """
    n_frames, n_cells = len(pos), len(scene.cells)
    cell_idx = np.stack([scene.cell_of(pos[f], px[f]) for f in range(n_frames)])
    along = (pos - scene.center) @ scene.u
    mean_hist = np.full((DURATION_S, n_cells, 2), np.nan)
    frames = []
    for t in range(DURATION_S):
        f0 = t * FPS
        sample = np.clip(f0 + np.array([-12, -6, 0, 6, 12]), 0, n_frames - 1)
        counts = np.mean([np.bincount(cell_idx[f][cell_idx[f] >= 0], minlength=n_cells) for f in sample], axis=0)
        dens = np.round(counts / scene.areas, 2)
        fa, fb = max(f0 - FPS // 2, 0), min(f0 + FPS // 2, n_frames - 1)
        vel = (pos[fb] - pos[fa]) / ((fb - fa) / FPS)
        here = cell_idx[f0]
        states = []
        for i, c in enumerate(scene.cells):
            d = float(dens[i])
            v = vel[here == i]
            if d == 0 or len(v) == 0:
                states.append({"cell_id": c["cell_id"], "density": d, "vx": None, "vy": None, "speed_var": None,
                               "pressure": 0.0, "counterflow": None, "density_pred_60s": None})
                continue
            mean_v = v.mean(axis=0)
            mean_hist[t, i] = mean_v
            window = mean_hist[max(t - VAR_WINDOW_S + 1, 0):t + 1, i]
            window = window[np.isfinite(window[:, 0])]
            var = round(float(((window - window.mean(axis=0)) ** 2).sum(axis=1).mean()), 4) if len(window) >= 3 else None
            counter = round(float(np.mean(v @ mean_v < 0)), 4) if np.linalg.norm(mean_v) >= 0.05 else None
            states.append({"cell_id": c["cell_id"], "density": d,
                           "vx": round(float(mean_v[0]), 2) + 0.0, "vy": round(float(mean_v[1]), 2) + 0.0,
                           "speed_var": var, "pressure": None if var is None else round(d * var, 4),
                           "counterflow": counter, "density_pred_60s": None})
        # 경계 유입: 구역 위아래 끝(가운데에서 4 m 넘는 곳)에서 움직이는 사람 중 안쪽으로 향하는 비율
        edge = (here >= 0) & (np.abs(along[f0]) > 4.0) & (np.linalg.norm(vel, axis=1) > 0.1)
        inward = np.einsum("ij,ij->i", vel[edge], scene.center - pos[f0][edge]) > 0
        frames.append({"t": t, "inflow_ratio": round(float(inward.mean()), 4) if edge.sum() >= 3 else None,
                       "count": round(float(counts.sum()), 2), "cells": states})
    return frames


def expected_grades(scene: Scene, frames: list[dict[str, object]]) -> list[int]:
    """서버 판정 규칙(application.yml 기본값)을 흉내 내 초별 구역 등급(0 정상 ~ 3 심각)을 미리 본다.

    올림만 본다: 셀 관측 등급 = 밀도 등급과 (불안정이면 심각) 중 높은 쪽, 최근 2개가 모두 현재보다 높으면 올린다.
    불안정 = 밀도 3 이상이고 압력이 0.02를 넘는 초가 3초 연속.
    """
    n = len(scene.cells)
    grade, streak = np.zeros(n, int), np.zeros(n, int)
    prev = np.zeros(n, int)
    out = []
    for fr in frames:
        obs = np.zeros(n, int)
        for i, c in enumerate(fr["cells"]):
            hot = c["density"] >= 3.0 and c["pressure"] is not None and c["pressure"] > 0.02
            streak[i] = streak[i] + 1 if hot else 0
            obs[i] = 3 if streak[i] >= 3 else sum(c["density"] >= th for th in (3.0, 4.0, 5.0))
        up = np.minimum(obs, prev)
        grade = np.where(up > grade, up, grade)
        prev = obs
        out.append(int(grade[scene.areas >= 2.0].max()))
    return out


def background(video: str, n_samples: int = 45) -> np.ndarray:
    """영상에서 고르게 뽑은 프레임의 중앙값으로 사람 없는 배경을 만든다."""
    cap = cv2.VideoCapture(video)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    shots = []
    for f in np.linspace(0, total - 1, n_samples).astype(int):
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(f))
        ok, frame = cap.read()
        if ok:
            shots.append(frame)
    stack = np.stack(shots)
    out = np.empty_like(shots[0])
    for y in range(0, stack.shape[1], 120):
        out[y:y + 120] = np.median(stack[:, y:y + 120], axis=0)
    return out


def caption(text: str, width: int) -> tuple[np.ndarray, np.ndarray]:
    """한글 자막 띠를 (색 BGR, 투명도) 배열로 만든다."""
    font = ImageFont.truetype(FONT, 30)
    img = Image.new("RGBA", (width, 56), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    box = draw.textbbox((0, 0), text, font=font)
    draw.rounded_rectangle((12, 6, box[2] + 44, 52), 10, fill=(15, 18, 25, 185))
    draw.text((28, 9), text, font=font, fill=(255, 255, 255, 255))
    arr = np.asarray(img).astype(np.float32)
    return arr[..., 2::-1], arr[..., 3:] / 255


def render(scene: Scene, bg: np.ndarray, pos: np.ndarray, px: np.ndarray, scale: np.ndarray,
           frames: list[dict[str, object]], out: Path, rng: np.random.Generator) -> None:
    """배경 위에 인원(그림자·몸·머리)과 머리 점을 그려 H.264 mp4로 저장한다. 가까운 사람이 먼 사람을 가린다.

    걷는 사람은 걸음에 맞춰 몸이 좌우로 조금 흔들린다 (그림에만 넣고 위치 값에는 넣지 않는다).
    """
    n = pos.shape[1]
    shirts = np.array([(60, 60, 70), (200, 200, 205), (40, 45, 90), (120, 80, 50), (70, 110, 150), (90, 90, 95),
                       (150, 160, 175), (50, 70, 60), (60, 60, 160), (190, 170, 140), (110, 60, 90)], np.uint8)
    shirt = shirts[rng.integers(0, len(shirts), n)].astype(int) + rng.integers(-18, 18, (n, 3))
    pants = np.array([(45, 40, 40), (80, 60, 45), (60, 60, 65), (110, 95, 80)])[rng.integers(0, 4, n)]
    hair = np.array([(25, 25, 30), (35, 40, 55), (20, 20, 20), (60, 70, 90)])[rng.integers(0, 4, n)]
    build = rng.uniform(0.9, 1.1, n)
    step_phase = rng.uniform(0, 2 * np.pi, n)
    speed = np.linalg.norm(np.gradient(pos, 1 / FPS, axis=0), axis=2)
    draw_poly = scene.poly.copy()
    draw_poly[draw_poly[:, 1] >= bg.shape[0], 1] = bg.shape[0] + 400   # 발이 화면 아래에 있어도 상체는 보인다
    draw_poly[draw_poly[:, 0] <= 0, 0] = -200
    writer = cv2.VideoWriter(str(out), cv2.VideoWriter_fourcc(*"avc1"), FPS, (bg.shape[1], bg.shape[0]))
    if not writer.isOpened():
        raise RuntimeError(f"영상 파일을 열 수 없다: {out}")
    for f in range(len(pos)):
        img = bg.copy()
        shadow = np.zeros(bg.shape[:2], np.uint8)
        show = [k for k in np.argsort(px[f][:, 1])
                if cv2.pointPolygonTest(draw_poly, (float(px[f][k, 0]), float(px[f][k, 1])), False) >= 0]
        for k in show:
            x, y, s = px[f][k, 0], px[f][k, 1], scale[f][k] * build[k]
            cv2.ellipse(shadow, (int(x + 0.12 * s), int(y)), (int(0.30 * s), max(int(0.11 * s), 1)), 0, 0, 360, 255, -1)
        img = (img * (1 - 0.38 * cv2.GaussianBlur(shadow, (9, 9), 0)[..., None] / 255)).astype(np.uint8)
        heads = []
        for k in show:
            x, y, s = px[f][k, 0], px[f][k, 1], scale[f][k] * build[k]
            hh = PERSON_H_M * HEIGHT_FACTOR * s
            sway = 0.035 * s * min(speed[f, k] / 0.6, 1.0) * np.sin(2 * np.pi * 1.8 * f / FPS + step_phase[k])
            cv2.ellipse(img, (int(x), int(y - 0.25 * hh)), (max(int(0.13 * s), 1), max(int(0.27 * hh), 1)), 0, 0, 360,
                        tuple(int(v) for v in pants[k]), -1, cv2.LINE_AA)
            body = (int(x + 0.6 * sway), int(y - 0.66 * hh)), (max(int(0.195 * s), 1), max(int(0.25 * hh), 1))
            cv2.ellipse(img, *body, 0, 0, 360, tuple(int(v) for v in np.clip(shirt[k], 0, 255)), -1, cv2.LINE_AA)
            cv2.ellipse(img, *body, 0, 0, 360, (25, 25, 28), 1, cv2.LINE_AA)
            head = (int(x + sway), int(y - hh))
            cv2.circle(img, head, max(int(0.125 * s), 2), tuple(int(v) for v in hair[k]), -1, cv2.LINE_AA)
            heads.append((head, s))
        for head, s in heads:                                          # P2PNet 결과 그림처럼 머리마다 빨간 점
            cv2.circle(img, head, int(np.clip(0.035 * s, 2, 4)), (0, 0, 255), -1, cv2.LINE_AA)
        count = frames[min(f // FPS, len(frames) - 1)]["count"]
        color, alpha = caption(f"시뮬레이션 영상 (합성) · 빨간 점 = 머리 위치 · 구역 인원 {count:.0f}명", bg.shape[1])
        img[:56] = (img[:56] * (1 - alpha) + color * alpha).astype(np.uint8)
        writer.write(img)
    writer.release()


def main() -> None:
    """시뮬레이션을 돌려 영상과 timeline.json을 저장하고 초별 최대 밀도·압력·예상 등급을 출력한다."""
    ap = argparse.ArgumentParser()
    ap.add_argument("--homography", required=True)
    ap.add_argument("--video", required=True, help="배경을 뽑을 실제 영상")
    ap.add_argument("--out-video", required=True)
    ap.add_argument("--out-timeline", required=True)
    ap.add_argument("--no-video", action="store_true", help="timeline만 만든다 (값 확인용)")
    args = ap.parse_args()

    cfg = json.loads(Path(args.homography).read_text(encoding="utf-8"))
    scene = Scene(cfg, (1920, 1080))
    pos = simulate(scene, np.random.default_rng(SEED))
    px = np.stack([ground_to_image(scene.h, p) for p in pos])
    frames = measure(scene, pos, px)

    video_id = Path(args.out_video).stem
    vid = video_id.lower().replace("_", "-")
    timeline = validate_timeline({
        "schema_version": SCHEMA_VERSION,
        "meta": {
            "zone_id": f"zone-{vid}", "camera_id": f"cam-{vid}", "video_id": video_id,
            "duration_s": DURATION_S, "interval_s": 1, "cell_size_m": CELL_M,
            "models": {"counter": "simulation", "flow": "simulation", "predictor": "none"},
            "prediction": {"history_s": 30, "horizon_s": 60},
            "cells": scene.cells,
        },
        "frames": frames,
    })
    out_tl = Path(args.out_timeline)
    out_tl.parent.mkdir(parents=True, exist_ok=True)
    out_tl.write_text(json.dumps(timeline, ensure_ascii=False), encoding="utf-8")
    print(f"인원 {pos.shape[1]}명, 셀 {len(scene.cells)}개 → {out_tl}")
    grades = expected_grades(scene, frames)
    for fr, grade in zip(frames, grades):
        big = [c for c, a in zip(fr["cells"], scene.areas) if a >= 2.0]
        top = max(big, key=lambda c: c["density"])
        dense = max([(c["pressure"] or 0) for c in big if c["density"] >= 3.0] or [0])
        sparse = max([(c["pressure"] or 0) for c in big if c["density"] < 3.0] or [0])
        print(f"t={fr['t']:2d} 인원={fr['count']:6.1f} 최대밀도={top['density']:.2f} 압력(밀도3↑)={dense:.4f} "
              f"압력(밀도3↓)={sparse:.4f} 유입={fr['inflow_ratio']} 등급={'정상 주의 경계 심각'.split()[grade]}")
    print("예상 등급:", "".join(str(g) for g in grades))
    if args.no_video:
        return
    side = np.stack([ground_to_image(scene.h, p + scene.w) for p in pos])
    scale = np.linalg.norm(side - px, axis=2)        # 그 자리에서 1 m가 몇 픽셀인가
    out_v = Path(args.out_video)
    out_v.parent.mkdir(parents=True, exist_ok=True)
    render(scene, background(args.video), pos, px, scale, frames, out_v, np.random.default_rng(SEED + 1))
    print(f"영상 → {out_v}")


if __name__ == "__main__":
    main()
