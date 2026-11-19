"""머리 점·정답 흐름 없이 흐름 설정을 비교하는 프레임 프록시 지표.

연구 문서(docs/research/flow_model_upgrade_research.md) 부록 A·B의
벤치마크를 함수로 옮겼다. 집계값만 내고 프레임·흐름장은 쓰지 않는다.
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import cv2
import numpy as np

from src.flow.estimators import FarnebackEstimator

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "outputs" / "flow_upgrade"


def photometric_ratio(
    prev_gray: np.ndarray, next_gray: np.ndarray, flow: np.ndarray,
    mask: np.ndarray,
) -> float:
    """next를 흐름으로 당겨 prev와 비교한 평균 절대 차 / 흐름 0일 때 값.

    마스크가 비거나 흐름 0 오차가 0이면 NaN이다. 낮을수록 좋다.
    """
    if not mask.any():
        return float("nan")
    a = prev_gray.astype(np.float32)
    b = next_gray.astype(np.float32)
    h, w = a.shape
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    warped = cv2.remap(
        b, xx + flow[..., 0], yy + flow[..., 1], cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_REPLICATE,
    )
    zero = float(np.abs(b - a)[mask].mean())
    if zero == 0:
        return float("nan")
    return float(np.abs(warped - a)[mask].mean()) / zero


def static_noise_p95(flow: np.ndarray, mask: np.ndarray, gap: int) -> float:
    """정지 마스크 화소의 |흐름|/gap 95백분위 [px/프레임]. 비면 NaN."""
    if not mask.any():
        return float("nan")
    mag = np.linalg.norm(flow, axis=2) / gap
    return float(np.percentile(mag[mask], 95))


def frame_masks(
    prev_gray: np.ndarray, next_gray: np.ndarray, walkable: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """(정지 배경, 움직인 곳) 마스크를 돌려준다.

    두 프레임 절대 차를 σ 3 가우시안으로 흐린 값이 1 미만이고 걷는 곳
    밖이면 정지, 4 이상이고 걷는 곳 안이면 움직인 곳이다 (연구 문서 4장).
    """
    diff = np.abs(
        prev_gray.astype(np.float32) - next_gray.astype(np.float32)
    )
    blur = cv2.GaussianBlur(diff, (0, 0), 3)
    walk = walkable.astype(bool)
    return (~walk) & (blur < 1.0), walk & (blur >= 4.0)


def parse_configs(text: str) -> list[tuple[str, float, int]]:
    """"fb:1:1,fb:0.5:6"을 [(설정 문자열, 배율, gap), ...]으로 바꾼다.

    추정기는 fb(Farneback)만 받는다. 형식이 다르면 ValueError다.
    """
    out = []
    for item in text.split(","):
        parts = item.strip().split(":")
        if len(parts) != 3 or parts[0] != "fb":
            raise ValueError(f"설정은 fb:배율:gap 형식이어야 한다: {item!r}")
        out.append((item.strip(), float(parts[1]), int(parts[2])))
    return out


def main() -> None:
    """설정별 시간/쌍·정지 p95·사진 오차 비율을 표로 찍고 JSON에 쓴다.

    쌍은 t = 0, 6, 12, …초의 (round(t·fps), +gap) 프레임이다(연구 문서
    4장). 마스크는 gap 1 차이로 정해 설정 사이에 같게 두고, 사진 오차는
    움직인 곳에서 잰다. 시간은 첫 쌍 예열 뒤 estimate 1회의 중앙값이다.
    집계값만 쓴다.
    """
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", required=True)
    ap.add_argument("--homography", required=True, help="구역 설정 파일")
    ap.add_argument("--configs", default="fb:1:1,fb:0.5:6")
    ap.add_argument("--pairs", type=int, default=10)
    ap.add_argument("--out", default=None,
                    help="기본: outputs/flow_upgrade/{video}_proxy.json")
    args = ap.parse_args()

    configs = parse_configs(args.configs)
    cfg = json.loads(Path(args.homography).read_text(encoding="utf-8"))
    max_gap = max(g for _, _, g in configs)
    cap = cv2.VideoCapture(args.video)
    if not cap.isOpened():
        raise ValueError(f"영상을 열 수 없다: {args.video}")
    fps = cap.get(cv2.CAP_PROP_FPS)
    if not (np.isfinite(fps) and fps > 0):
        cap.release()
        raise ValueError(f"영상 fps가 올바르지 않다: {fps}")
    groups = []
    for i in range(args.pairs):
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(round(6 * i * fps)))
        frames = [cap.read()[1] for _ in range(max_gap + 1)]
        if any(f is None for f in frames):
            break
        groups.append(frames)
    cap.release()
    if not groups:
        raise ValueError(f"프레임 쌍을 읽지 못했다: {args.video}")

    h, w = groups[0][0].shape[:2]
    walk = np.zeros((h, w), np.uint8)
    cv2.fillPoly(walk, [np.array(cfg["walkable_polygon_px"], np.int32)], 1)
    grays = [
        [cv2.cvtColor(f, cv2.COLOR_BGR2GRAY) for f in g] for g in groups
    ]
    masks = [frame_masks(g[0], g[1], walk.astype(bool)) for g in grays]

    rows = []
    for name, scale, gap in configs:
        est = FarnebackEstimator(scale=scale)
        est.estimate(groups[0][0], groups[0][gap])  # 예열
        times, noise, photo = [], [], []
        for frames, gray, (static, moving) in zip(groups, grays, masks):
            t0 = time.perf_counter()
            flow = est.estimate(frames[0], frames[gap])
            times.append(time.perf_counter() - t0)
            noise.append(static_noise_p95(flow, static, gap))
            photo.append(photometric_ratio(gray[0], gray[gap], flow, moving))
        row = {
            "config": name, "estimator": est.name, "gap_frames": gap,
            "seconds_per_pair": round(float(np.median(times)), 3),
            "static_p95_px_per_frame": round(float(np.nanmean(noise)), 3),
            "photometric_ratio": round(float(np.nanmean(photo)), 2),
        }
        rows.append(row)
        print(f"| {name} | {row['seconds_per_pair']:.3f} | "
              f"{row['static_p95_px_per_frame']:.3f} | "
              f"{row['photometric_ratio']:.2f} |", flush=True)

    stem = Path(args.video).stem
    out = Path(args.out) if args.out else OUT_DIR / f"{stem}_proxy.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    record = {"video": stem, "pairs": len(groups), "rows": rows}
    out.write_text(json.dumps(record, ensure_ascii=False, indent=2),
                   encoding="utf-8")
    print(f"저장: {out}")


if __name__ == "__main__":
    main()
