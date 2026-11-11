"""tests/predict 공용 합성 데이터 도우미."""
import numpy as np


def blob_series(steps: int, rows: int = 3, cols: int = 20, start: float = 2.0,
                speed_cells_per_s: float = 0.1, sigma: float = 1.2, peak: float = 2.0) -> np.ndarray:
    """덩어리가 +col 방향으로 일정 속도로 이동하는 (steps, rows, cols) 밀도."""
    x = np.arange(cols)
    out = np.zeros((steps, rows, cols))
    for t in range(steps):
        out[t] = peak * np.exp(-((x - (start + speed_cells_per_s * t)) ** 2) / (2 * sigma ** 2))
    return out
