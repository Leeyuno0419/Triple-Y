"""E2 정답 만들기: 프레임마다 사람 머리를 클릭해 셀별 인원을 센다.

    python -m src.counting.label_e2 --homography infra/homography/E04_039.json \
        --video data/processed/g1/E04_039.mp4

조작: 왼쪽 클릭 = 머리 추가, 오른쪽 클릭 = 가까운 점 삭제,
      Space/Enter = 저장 후 다음, U = 마지막 점 취소, Q = 그만(이어서 가능)
보이는 머리를 구역 안팎 상관없이 모두 클릭한다. 구역 안 판정은 AI와 같은 머리 높이 보정으로 한다.
AI 결과는 보여 주지 않는다(정답이 AI 쪽으로 쏠리지 않게).
클릭 좌표는 저장하지 않고 셀별 인원만 저장한다. 이미 저장된 프레임은 건너뛴다.
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import cv2
import numpy as np

from src.counting.cells import build_cells, image_to_ground
from src.counting.run_density import count_cells

ROOT = Path(__file__).resolve().parents[2]
MARGIN, DISPLAY_W = 60, 1600


def label_times(duration_s: int, n: int) -> list[int]:
    """영상 전체에 고르게 퍼진 n개 시각(초)."""
    return [int((i + 0.5) * duration_s / n) for i in range(n)]


def main() -> None:
    """프레임을 차례로 띄워 클릭을 받고, 셀별 인원을 CSV에 한 줄씩 저장한다."""
    ap = argparse.ArgumentParser()
    ap.add_argument("--homography", required=True)
    ap.add_argument("--video", required=True)
    ap.add_argument("--n", type=int, default=30)
    args = ap.parse_args()

    cfg = json.loads(Path(args.homography).read_text(encoding="utf-8"))
    h_head = np.array(cfg["head_plane"]["H_head_img_to_ground"])
    origin = tuple(cfg["cell_origin_m"])
    cap = cv2.VideoCapture(args.video)
    fps = cap.get(cv2.CAP_PROP_FPS)
    size = (int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)))
    cells = build_cells(np.array(cfg["H_img_to_ground"]), cfg["walkable_polygon_px"], size,
                        origin_m=origin)
    polys = [(np.array(c["image_polygon"]) * size).astype(np.int32) for c in cells]

    allpts = np.vstack(polys)
    x0, y0 = np.maximum(allpts.min(axis=0) - MARGIN, 0)
    x1, y1 = np.minimum(allpts.max(axis=0) + MARGIN, size)
    s = DISPLAY_W / (x1 - x0)

    out = ROOT / "outputs" / "e2" / f"{cfg['video']}_gt.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    done = set()
    if out.exists():
        done = {int(r["t"]) for r in csv.DictReader(open(out, encoding="utf-8"))}
    else:
        with open(out, "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(["t", "zone_count", "clicked"] + [c["cell_id"] for c in cells])

    times = label_times(int(cap.get(cv2.CAP_PROP_FRAME_COUNT) / fps), args.n)
    pts: list[tuple[float, float]] = []

    def on_mouse(event: int, x: int, y: int, *_: object) -> None:
        if event == cv2.EVENT_LBUTTONDOWN:
            pts.append((x / s + x0, y / s + y0))
        elif event == cv2.EVENT_RBUTTONDOWN and pts:
            d = [np.hypot(px - (x / s + x0), py - (y / s + y0)) for px, py in pts]
            if min(d) < 25:
                pts.pop(int(np.argmin(d)))

    cv2.namedWindow("E2", cv2.WINDOW_NORMAL)
    cv2.setMouseCallback("E2", on_mouse)
    for k, t in enumerate(times, 1):
        if t in done:
            continue
        cap.set(cv2.CAP_PROP_POS_FRAMES, round(t * fps))
        frame = cap.read()[1]
        pts.clear()
        while True:
            view = frame.copy()
            for p in polys:
                cv2.polylines(view, [p], True, (255, 255, 0), 1)
            for px, py in pts:
                cv2.circle(view, (int(px), int(py)), 5, (0, 0, 255), -1)
                cv2.circle(view, (int(px), int(py)), 6, (255, 255, 255), 1)
            view = cv2.resize(view[y0:y1, x0:x1], None, fx=s, fy=s)
            cv2.putText(view, f"[{k}/{len(times)}] t={t}s  heads={len(pts)}   "
                        "L-click add | R-click delete | U undo | SPACE save+next | Q quit",
                        (10, 30), 0, 0.75, (0, 0, 255), 2)
            cv2.imshow("E2", view)
            key = cv2.waitKey(30) & 0xFF
            if key in (ord("u"), ord("U")) and pts:
                pts.pop()
            elif key in (32, 13):
                ground = image_to_ground(h_head, np.array(pts)) if pts else np.zeros((0, 2))
                counts = count_cells(ground, cells, origin, 2.0)
                with open(out, "a", newline="", encoding="utf-8") as f:
                    csv.writer(f).writerow([t, int(counts.sum()), len(pts)] + counts.tolist())
                break
            elif key in (ord("q"), ord("Q")):
                cv2.destroyAllWindows()
                print(f"중단: {out} (다시 실행하면 이어서)")
                return
    cv2.destroyAllWindows()
    print(f"완료: {out}")


if __name__ == "__main__":
    main()
