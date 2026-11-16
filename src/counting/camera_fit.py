"""사람 머리·발 쌍으로 카메라를 맞춰 바닥·머리 높이 평면 행렬을 만든다 (바닥 기준 사각형이 없는 영상용).

    python -m src.counting.camera_fit --config infra/homography/E05_035.json
    python -m src.counting.camera_fit --config infra/homography/E05_038.json \
        --pick-video data/processed/g1/E05_038.mp4      # 머리·발 쌍을 클릭으로 받은 뒤 맞춤

구역 설정 파일의 camera_fit.inputs(사람 머리·발 픽셀 쌍, 같은 크기 노면 글자 2개, 직선 노면선)를 읽어
카메라(초점거리, 내려다보는 각, 좌우 각, 높이)를 최소제곱으로 맞추고, 결과 행렬을 같은 파일에 쓴다.
- 머리·발 쌍: 발 위치에서 머리 중심 높이(head_h_m)만큼 올린 점이 머리 픽셀에 오도록 한다. 축척(카메라 높이)이 여기서 정해진다.
- 노면 글자: 두 글자의 가로·세로가 바닥에서 같은 길이가 되도록 한다. 원근(기울기)을 잡는다.
- 노면선: 점들이 바닥에서 한 직선(길 방향)에 오도록 한다. 바닥 좌표의 y축을 길 방향에 맞춘다.
가정: 렌즈 왜곡 없음, 화면 중심이 광축, 좌우 기울기(roll) 0.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2
import numpy as np
from scipy.optimize import least_squares

W_MARK = 200.0  # 노면 조건 가중치. 픽셀 잔차(수~수십)와 크기를 맞춘다


def camera(p: np.ndarray, img_size: tuple[int, int]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """매개변수 (f, 내려다보는 각, 좌우 각, 카메라 높이)로 K, R, 카메라 위치를 만든다. 바닥 좌표: x 오른쪽, y 길 안쪽, z 위."""
    f, pitch, yaw, cam_h = p
    fwd = np.array([np.sin(yaw) * np.cos(pitch), np.cos(yaw) * np.cos(pitch), -np.sin(pitch)])
    right = np.array([np.cos(yaw), -np.sin(yaw), 0.0])
    rot = np.stack([right, np.cross(fwd, right), fwd])
    k = np.array([[f, 0, img_size[0] / 2], [0, f, img_size[1] / 2], [0, 0, 1]])
    return k, rot, np.array([0.0, 0.0, cam_h])


def plane_homography(p: np.ndarray, img_size: tuple[int, int], z: float) -> np.ndarray:
    """높이 z(m) 평면의 영상 픽셀 → 바닥 좌표(m) 3×3 행렬."""
    k, rot, c = camera(p, img_size)
    proj = k @ np.c_[rot, -rot @ c]
    h = np.linalg.inv(np.c_[proj[:, 0], proj[:, 1], proj[:, 2] * z + proj[:, 3]])
    return h / h[2, 2]


def _to_plane(p: np.ndarray, img_size: tuple[int, int], uv: np.ndarray, z: float = 0.0) -> np.ndarray:
    """픽셀 점들을 높이 z 평면 위 (x, y)로 옮긴다."""
    pts = np.c_[uv, np.ones(len(uv))] @ plane_homography(p, img_size, z).T
    return pts[:, :2] / pts[:, 2:]


def _project(p: np.ndarray, img_size: tuple[int, int], xyz: np.ndarray) -> np.ndarray:
    """3차원 점들을 영상 픽셀로 투영한다."""
    k, rot, c = camera(p, img_size)
    x = (k @ (rot @ (xyz - c).T)).T
    return x[:, :2] / x[:, 2:]


def residuals(p: np.ndarray, inputs: dict[str, object], img_size: tuple[int, int]) -> np.ndarray:
    """머리 픽셀 오차(px)와 노면 조건 오차(가중)를 이어 붙인다."""
    pairs = np.array(inputs["head_feet_pairs_px"], float)
    feet = _to_plane(p, img_size, pairs[:, 2:])
    head = _project(p, img_size, np.c_[feet, np.full(len(feet), inputs["head_h_m"])])
    r = list((head - pairs[:, :2]).ravel())
    if inputs.get("same_size_glyphs_px"):
        g1, g2 = (_to_plane(p, img_size, np.array(g, float)) for g in inputs["same_size_glyphs_px"])
        for a, b in ((0, 1), (0, 3)):  # 가로(위 변), 세로(왼 변)
            r.append(W_MARK * (np.linalg.norm(g1[b] - g1[a]) / np.linalg.norm(g2[b] - g2[a]) - 1))
    if inputs.get("road_line_px"):  # 없으면 좌우 각은 시작값(0)으로 남는다. 밀도에는 영향 없음
        line_x = _to_plane(p, img_size, np.array(inputs["road_line_px"], float))[:, 0]
        r += list(W_MARK * (line_x - line_x.mean()))
    return np.array(r)


def fit_camera(inputs: dict[str, object], img_size: tuple[int, int]) -> np.ndarray:
    """여러 시작값에서 최소제곱을 돌려 오차가 가장 작은 카메라 매개변수를 고른다."""
    best = None
    for f0 in (900, 1300, 1800, 2400):
        for pitch0 in (0.6, 0.9, 1.2):
            s = least_squares(residuals, [f0, pitch0, 0.0, 6.0], args=(inputs, img_size),
                              bounds=([300, 0.1, -0.6, 2], [5000, 1.55, 0.6, 30]))
            if best is None or s.cost < best.cost:
                best = s
    return best.x


def head_heights(p: np.ndarray, inputs: dict[str, object], img_size: tuple[int, int]) -> list[float]:
    """맞춘 카메라로 사람마다 머리 중심 높이를 역산한다 (검증용, 평균이 head_h_m 근처여야 함)."""
    zs = np.linspace(0.5, 2.5, 401)
    out = []
    for hx, hy, fx, fy in inputs["head_feet_pairs_px"]:
        ft = _to_plane(p, img_size, np.array([[fx, fy]], float))[0]
        px = _project(p, img_size, np.c_[np.tile(ft, (len(zs), 1)), zs])
        out.append(round(float(zs[np.argmin(np.linalg.norm(px - [hx, hy], axis=1))]), 2))
    return out


def pick_pairs(video: str, times: list[float], display_w: int = 1600) -> list[list[float]]:
    """영상 프레임을 띄워 사람마다 머리 중심 → 두 발 가운데를 차례로 클릭받는다.

    조작: 왼쪽 클릭 = 점 추가(머리, 발 번갈아), U = 마지막 점 취소, Space = 다음 프레임, Q = 끝.
    똑바로 서 있고 발이 보이는 사람만 찍는다. 화면 위·아래(먼 곳·가까운 곳)에 고루 퍼지게 찍어야 각도가 잡힌다.
    """
    cap = cv2.VideoCapture(video)
    fps = cap.get(cv2.CAP_PROP_FPS)
    pairs: list[list[float]] = []
    for k, t in enumerate(times, 1):
        cap.set(cv2.CAP_PROP_POS_FRAMES, round(t * fps))
        frame = cap.read()[1]
        s = display_w / frame.shape[1]
        pts: list[tuple[float, float]] = []
        cv2.namedWindow("pairs", cv2.WINDOW_NORMAL)
        cv2.setMouseCallback("pairs", lambda e, x, y, *_: pts.append((x / s, y / s))
                             if e == cv2.EVENT_LBUTTONDOWN else None)
        while True:
            view = frame.copy()
            for i, (x, y) in enumerate(pts):
                cv2.circle(view, (int(x), int(y)), 6, (0, 0, 255) if i % 2 == 0 else (0, 255, 0), -1)
                if i % 2:
                    cv2.line(view, tuple(map(int, pts[i - 1])), (int(x), int(y)), (0, 255, 255), 2)
            view = cv2.resize(view, None, fx=s, fy=s)
            nxt = "HEAD (red)" if len(pts) % 2 == 0 else "FEET (green)"
            cv2.putText(view, f"[{k}/{len(times)}] t={t}s  people={len(pairs) + len(pts) // 2}  next: {nxt}   "
                        "U undo | SPACE next frame | Q finish", (10, 30), 0, 0.75, (0, 0, 255), 2)
            cv2.imshow("pairs", view)
            key = cv2.waitKey(30) & 0xFF
            if key in (ord("u"), ord("U")) and pts:
                pts.pop()
            elif key in (32, ord("q"), ord("Q")):
                pairs += [[round(a[0]), round(a[1]), round(b[0]), round(b[1])] for a, b in zip(pts[::2], pts[1::2])]
                break
        if key in (ord("q"), ord("Q")):
            break
    cv2.destroyAllWindows()
    return pairs


def main() -> None:
    """구역 설정 파일의 입력으로 카메라를 맞추고 행렬·검증값을 같은 파일에 쓴다.

    --pick-video를 주면 먼저 클릭 창을 띄워 머리·발 쌍을 받아 입력에 저장한다(설정 파일이 없으면 새로 만든다).
    """
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--size", default="1920x1080")
    ap.add_argument("--pick-video", help="머리·발 쌍을 클릭으로 받을 영상")
    ap.add_argument("--pick-times", default="5,20,35,50", help="클릭할 프레임 시각(초), 쉼표로 구분")
    args = ap.parse_args()

    path = Path(args.config)
    size = tuple(int(v) for v in args.size.split("x"))
    if path.exists():
        cfg = json.loads(path.read_text(encoding="utf-8"))
    else:
        cfg = {"video": path.stem, "camera_fit": {"inputs": {"head_h_m": 1.55}}}
    inputs = cfg["camera_fit"]["inputs"]
    if args.pick_video:
        times = [float(v) for v in args.pick_times.split(",")]
        inputs["head_feet_pairs_px"] = pick_pairs(args.pick_video, times)
        inputs["head_feet_pairs_note"] = f"머리 중심 x, y, 두 발 가운데 x, y. {args.pick_times}초 프레임에서 수작업 클릭"
        path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"클릭 {len(inputs['head_feet_pairs_px'])}명 저장")
    p = fit_camera(inputs, size)
    heights = head_heights(p, inputs, size)
    loo = [fit_camera({**inputs, "head_feet_pairs_px": inputs["head_feet_pairs_px"][:i] +
                       inputs["head_feet_pairs_px"][i + 1:]}, size)[3] for i in range(len(heights))]
    glyphs = [_to_plane(p, size, np.array(g, float)) for g in inputs.get("same_size_glyphs_px", [])]
    cfg["camera_fit"]["result"] = {
        "focal_px": round(float(p[0]), 1), "pitch_deg": round(float(np.degrees(p[1])), 2),
        "yaw_deg": round(float(np.degrees(p[2])), 2), "camera_height_m": round(float(p[3]), 3),
        "head_px_err_median": round(float(np.median(np.linalg.norm(
            residuals(p, inputs, size)[:2 * len(heights)].reshape(-1, 2), axis=1))), 1),
        "head_h_each_m": heights,
        "camera_height_leave_one_out_m": [round(float(min(loo)), 2), round(float(max(loo)), 2)],
        "glyph_w_h_m": [[round(float(np.linalg.norm(g[1] - g[0])), 2), round(float(np.linalg.norm(g[3] - g[0])), 2)]
                        for g in glyphs],
    }
    cfg["H_img_to_ground"] = plane_homography(p, size, 0.0).tolist()
    cfg["head_plane"] = {"effective_head_h_m": inputs["head_h_m"],
                         "H_head_img_to_ground": plane_homography(p, size, inputs["head_h_m"]).tolist()}
    path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(cfg["camera_fit"]["result"], ensure_ascii=False))


if __name__ == "__main__":
    main()
