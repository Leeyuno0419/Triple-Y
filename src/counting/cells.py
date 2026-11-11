"""호모그래피와 바닥 다각형으로 2m 셀 목록(timeline.json meta.cells)을 만든다.

셀 격자는 지면 좌표(m)에서 나누고, 각 셀의 네 꼭짓점을 영상 좌표로 되돌려 image_polygon을 만든다.
규격상 image_polygon은 0~1 안이어야 하므로 꼭짓점이 영상 밖으로 나가는 셀은 뺀다.
"""
from __future__ import annotations

import cv2
import numpy as np


def ground_to_image(h: np.ndarray, pts: np.ndarray) -> np.ndarray:
    """지면 좌표(m) 점들을 영상 좌표(px)로 바꾼다. h는 영상→지면 행렬."""
    return cv2.perspectiveTransform(
        np.asarray(pts, float).reshape(-1, 1, 2), np.linalg.inv(h)).reshape(-1, 2)


def image_to_ground(h: np.ndarray, pts: np.ndarray) -> np.ndarray:
    """영상 좌표(px) 점들을 지면 좌표(m)로 바꾼다."""
    return cv2.perspectiveTransform(np.asarray(pts, float).reshape(-1, 1, 2), h).reshape(-1, 2)


def build_cells(h: np.ndarray, walkable_px: list[list[float]], img_size: tuple[int, int],
                cell_m: float = 2.0, min_area_m2: float = 1.0, samples: int = 20,
                origin_m: tuple[float, float] | None = None) -> list[dict[str, object]]:
    """보행 가능 영역을 덮는 셀 목록을 만든다.

    walkable_px는 영상 위 바닥 다각형, img_size는 (가로, 세로) 픽셀이다.
    보행 면적은 셀 안에 samples×samples 점을 찍어 다각형 안 비율로 구한다.
    면적이 min_area_m2보다 작은 자투리 셀은 뺀다. 몇 명만 있어도 밀도가 크게 튀기 때문이다.
    origin_m은 격자 시작점(지면 m)이다. 없으면 바닥 영역을 덮도록 cell_m 배수로 내림한다.
    영상 끝에 걸쳐 빠지는 셀이 생기면 시작점을 영상 끝에 맞춘다.
    """
    w, h_px = img_size
    poly = np.asarray(walkable_px, np.float32).reshape(-1, 1, 2)
    ground = image_to_ground(h, np.asarray(walkable_px, float))
    if origin_m is None:
        x0, y0 = np.floor(ground.min(axis=0) / cell_m) * cell_m
    else:
        x0, y0 = origin_m
    n_cols = int(np.ceil((ground[:, 0].max() - x0) / cell_m))
    n_rows = int(np.ceil((ground[:, 1].max() - y0) / cell_m))
    if n_rows > 100 or n_cols > 100:
        raise ValueError(f"격자가 너무 크다 ({n_rows}×{n_cols}). cell_id는 행·열 2자리까지다")

    offs = (np.arange(samples) + 0.5) / samples
    grid = np.stack(np.meshgrid(offs, offs), -1).reshape(-1, 2)
    cells = []
    for r in range(n_rows):
        for c in range(n_cols):
            gx, gy = x0 + c * cell_m, y0 + r * cell_m
            corners = ground_to_image(h, [[gx, gy], [gx + cell_m, gy],
                                          [gx + cell_m, gy + cell_m], [gx, gy + cell_m]])
            if not np.all((corners >= 0) & (corners <= [w, h_px])):
                continue
            px = ground_to_image(h, [gx, gy] + grid * cell_m)
            inside = [cv2.pointPolygonTest(poly, (float(x), float(y)), False) >= 0 for x, y in px]
            area = float(np.mean(inside)) * cell_m ** 2
            if area < min_area_m2:
                continue
            cells.append({
                "cell_id": f"c-{r:02d}{c:02d}",
                "row": r,
                "col": c,
                "walkable_area_m2": round(area, 2),
                "image_polygon": [[round(float(x) / w, 4), round(float(y) / h_px, 4)] for x, y in corners],
            })
    return cells
