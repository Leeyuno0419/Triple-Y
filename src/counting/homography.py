"""영상 바닥 4점과 실제 지면 좌표(m)로 호모그래피를 구하고 격자를 겹쳐 확인한다.

사용 예 (G0 확인):
    python -m src.counting.homography --video data/processed/g0/E04_022.mp4 \
        --frame 100 --world "0,0;1.2,0;1.2,1.2;0,1.2" --out infra/homography/E04_022.json

창이 뜨면 --world 순서대로 바닥 위 4점을 클릭하고 아무 키나 누른다.
결과로 행렬 JSON(--out)과 2m 격자를 겹친 확인용 이미지가 저장된다.
확인용 이미지는 CCTV 프레임이 그대로 들어가므로 git 밖(data/processed/homography/)에 둔다.
4점은 화면 앞쪽과 먼 쪽에 걸친 큰 사각형으로 잡는다. 작게 잡으면 원근이 잡히지 않는다.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2
import numpy as np

PREVIEW_DIR = Path(__file__).resolve().parents[2] / "data" / "processed" / "homography"


def read_frame(video: str, frame: int) -> np.ndarray:
    """영상에서 지정한 번호의 프레임 1장을 읽는다."""
    cap = cv2.VideoCapture(video)
    cap.set(cv2.CAP_PROP_POS_FRAMES, frame)
    ok, img = cap.read()
    cap.release()
    if not ok:
        raise ValueError(f"프레임을 읽지 못했다: {video} #{frame}")
    return img


def pick_points(img: np.ndarray, n: int = 4) -> np.ndarray:
    """창에서 n개 점을 클릭받아 (n, 2) 픽셀 좌표로 돌려준다."""
    pts: list[tuple[int, int]] = []
    view = img.copy()

    def on_click(event: int, x: int, y: int, *_: object) -> None:
        if event == cv2.EVENT_LBUTTONDOWN and len(pts) < n:
            pts.append((x, y))
            cv2.circle(view, (x, y), 6, (0, 0, 255), -1)
            cv2.putText(view, str(len(pts)), (x + 8, y - 8), 0, 1, (0, 0, 255), 2)
            cv2.imshow("pick", view)

    cv2.namedWindow("pick", cv2.WINDOW_NORMAL)
    cv2.setMouseCallback("pick", on_click)
    cv2.imshow("pick", view)
    while len(pts) < n:
        cv2.waitKey(50)
    cv2.waitKey(0)
    cv2.destroyAllWindows()
    return np.array(pts, dtype=np.float64)


def compute_homography(img_pts: np.ndarray, world_pts: np.ndarray) -> np.ndarray:
    """영상 좌표(px) → 지면 좌표(m) 3×3 행렬을 구한다."""
    h, _ = cv2.findHomography(img_pts, world_pts)
    return h


def draw_ground_grid(img: np.ndarray, h: np.ndarray, cell_m: float,
                     extent_m: float) -> np.ndarray:
    """지면의 cell_m 간격 격자를 영상 위에 겹쳐 그린다. 바닥과 맞으면 H가 맞다."""
    inv = np.linalg.inv(h)
    out = img.copy()
    ticks = np.arange(-extent_m, extent_m + 1e-9, cell_m)
    for a in ticks:
        for line in (np.array([[a, b] for b in ticks]), np.array([[b, a] for b in ticks])):
            px = cv2.perspectiveTransform(line.reshape(-1, 1, 2), inv).reshape(-1, 2)
            for p, q in zip(px[:-1], px[1:]):
                if np.all(np.abs([*p, *q]) < 1e5):
                    cv2.line(out, tuple(map(int, p)), tuple(map(int, q)), (0, 255, 0), 2)
    return out


def main() -> None:
    """4점 클릭 → 행렬 저장 → 격자 확인 이미지 저장."""
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", required=True)
    ap.add_argument("--frame", type=int, default=100)
    ap.add_argument("--world", required=True, help='"x,y;x,y;x,y;x,y" 미터 단위')
    ap.add_argument("--out", required=True)
    ap.add_argument("--cell", type=float, default=2.0)
    args = ap.parse_args()

    img = read_frame(args.video, args.frame)
    world = np.array([[float(v) for v in p.split(",")] for p in args.world.split(";")])
    img_pts = pick_points(img, len(world))
    h = compute_homography(img_pts, world)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "video": Path(args.video).stem,
        "frame": args.frame,
        "image_points_px": img_pts.tolist(),
        "world_points_m": world.tolist(),
        "H_img_to_ground": h.tolist(),
    }, indent=2), encoding="utf-8")
    check = PREVIEW_DIR / f"{out.stem}.jpg"
    check.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(check), draw_ground_grid(img, h, args.cell, 20))
    print(f"저장: {out}, 확인 이미지: {check}")


if __name__ == "__main__":
    main()
