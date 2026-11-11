"""E2: 수작업 정답(label_e2)과 P2PNet 구역 인원을 비교해 밀도 오차를 잰다.

    python -m src.counting.eval_e2 --homography infra/homography/E04_039.json \
        --video data/processed/g1/E04_039.mp4

정답 프레임을 3개 중 1개(조정용 10장)와 나머지(판정용 20장)로 나눈다.
조정용의 보정 전 상대오차로 축소 배율·판정 기준을 고르고, 판정용으로 E2를 판정한다.
같은 프레임으로 고르고 판정하면 결과가 부풀려지기 때문이다.
보정 계수 k(정답 합 / 예측 합)는 참고로만 적는다. 조정용 10장으로 k까지 고르면 과적합된다(판정용 27.5%→31.0%).
--avg N이면 정답 시각 앞뒤 0.4초 안의 N장을 세어 평균한다. 장마다 가려지는 사람이 달라 생기는 들쭉날쭉함을 줄인다.
지표: 프레임별 구역 밀도 상대오차 |예측-정답|/정답의 평균. 정답 3명 미만 프레임은 비율이 크게 튀어
상대오차에서 빼고, 대신 인원 절대오차(MAE)로 따로 보고한다.
"""
from __future__ import annotations

import argparse
import csv
import itertools
import json
from pathlib import Path

import cv2
import numpy as np

from src.counting.cells import build_cells, image_to_ground
from src.counting.eval_e1 import WEIGHTS, head_candidates, load_p2pnet
from src.counting.run_density import count_cells

ROOT = Path(__file__).resolve().parents[2]
SCALES, THRESHOLDS = (0.25, 0.3, 0.35, 0.4, 0.5), (0.2, 0.3, 0.4, 0.5)
MIN_GT = 3
WINDOW_S = 0.4


def metrics(pred: np.ndarray, gt: np.ndarray) -> dict[str, float]:
    """구역 인원 예측·정답으로 상대오차(정답 MIN_GT명 이상)와 MAE를 낸다."""
    ok = gt >= MIN_GT
    rel = np.abs(pred[ok] - gt[ok]) / gt[ok]
    return {"rel_err": float(rel.mean()) if ok.any() else float("nan"),
            "n_rel": int(ok.sum()), "mae": float(np.abs(pred - gt).mean()),
            "bias": float((pred - gt).mean())}


def main() -> None:
    """설정값 격자를 조정용으로 고르고 판정용 결과를 표로 저장한다."""
    ap = argparse.ArgumentParser()
    ap.add_argument("--homography", required=True)
    ap.add_argument("--video", required=True)
    ap.add_argument("--avg", type=int, default=1, help="정답 시각마다 평균할 프레임 수")
    args = ap.parse_args()

    cfg = json.loads(Path(args.homography).read_text(encoding="utf-8"))
    h_head = np.array(cfg["head_plane"]["H_head_img_to_ground"])
    origin = tuple(cfg["cell_origin_m"])
    rows = list(csv.DictReader(open(ROOT / "outputs" / "e2" / f"{cfg['video']}_gt.csv", encoding="utf-8")))
    times = np.array([int(r["t"]) for r in rows])
    gt = np.array([int(r["zone_count"]) for r in rows])

    cap = cv2.VideoCapture(args.video)
    fps = cap.get(cv2.CAP_PROP_FPS)
    size = (int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)))
    cells = build_cells(np.array(cfg["H_img_to_ground"]), cfg["walkable_polygon_px"], size,
                        origin_m=origin)
    model = load_p2pnet(WEIGHTS)

    offsets = np.linspace(-WINDOW_S, WINDOW_S, args.avg) if args.avg > 1 else np.zeros(1)
    pred = {}  # (scale, th) -> 정답 시각별 구역 인원 (avg장 평균)
    for i, t in enumerate(times):
        for off in offsets:
            cap.set(cv2.CAP_PROP_POS_FRAMES, round((t + off) * fps))
            frame = cap.read()[1]
            for sc in SCALES:
                cand, scores = head_candidates(model, frame, sc)  # 배율마다 한 번만 추론
                for th in THRESHOLDS:
                    pts = cand[scores > th]
                    n = count_cells(image_to_ground(h_head, pts), cells, origin, 2.0).sum() if len(pts) else 0
                    pred.setdefault((sc, th), np.zeros(len(times)))[i] += n / len(offsets)
        print(f"t={t}s 정답 {gt[i]}명", flush=True)

    tune = np.arange(len(times)) % 3 == 0
    k = {c: gt[tune].sum() / max(v[tune].sum(), 1) for c, v in pred.items()}
    raw = {c: metrics(v[tune], gt[tune]) for c, v in pred.items()}
    best = min(raw, key=lambda c: raw[c]["rel_err"])
    test = metrics(pred[best][~tune], gt[~tune])
    ok = test["rel_err"] <= 0.2

    tag = f"_avg{args.avg}" if args.avg > 1 else ""
    lines = [f"# E2 {cfg['video']} (프레임 평균 {args.avg}장, ±{WINDOW_S if args.avg > 1 else 0}초)", "",
             f"정답 {len(times)}프레임 (조정용 {tune.sum()} / 판정용 {(~tune).sum()}), "
             f"상대오차는 정답 {MIN_GT}명 이상 프레임만, 목표 ≤ 20%", "",
             "## 조정용: 설정값별 (보정 전 상대오차로 선택)", "",
             "| 축소 배율 | 판정 기준 | 상대오차 | MAE(명) | 치우침(명) | 참고: k |",
             "|---|---|---|---|---|---|"]
    for c in sorted(pred):
        mark = " ←" if c == best else ""
        lines.append(f"| {c[0]} | {c[1]} | {raw[c]['rel_err']:.1%}{mark} | {raw[c]['mae']:.2f} | "
                     f"{raw[c]['bias']:+.2f} | {k[c]:.2f} |")
    lines += ["", f"## 판정용: 배율 {best[0]}, 기준 {best[1]}", "",
              f"- 구역 밀도 상대오차 **{test['rel_err']:.1%}** ({test['n_rel']}프레임) → "
              f"**{'통과' if ok else '미통과'}**",
              f"- 구역 인원 MAE {test['mae']:.2f}명, 치우침 {test['bias']:+.2f}명 (음수 = 적게 셈)", ""]
    out = ROOT / "outputs" / "e2" / f"{cfg['video']}_e2{tag}.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    (ROOT / "outputs" / "e2" / f"{cfg['video']}_e2{tag}_best.json").write_text(json.dumps(
        {"avg_frames": args.avg, "window_s": WINDOW_S, "scale": best[0], "threshold": best[1],
         "test_rel_err": round(test["rel_err"], 4), "test_mae": round(test["mae"], 3),
         "passed": bool(ok)}, indent=2), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
