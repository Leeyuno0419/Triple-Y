"""E2 도구 테스트."""
import numpy as np

from src.counting.eval_e2 import metrics
from src.counting.label_e2 import label_times


def test_label_times_spread_evenly() -> None:
    """30개 시각이 영상 전체에 6초 간격으로 퍼진다."""
    t = label_times(180, 30)
    assert t[0] == 3 and t[-1] == 177 and len(set(np.diff(t))) == 1


def test_metrics_skips_small_gt_for_relative_error() -> None:
    """정답 3명 미만 프레임은 상대오차에서 빼고 MAE에는 넣는다."""
    m = metrics(np.array([0, 8, 12]), np.array([1, 10, 10]))
    assert m["n_rel"] == 2
    assert abs(m["rel_err"] - 0.2) < 1e-9          # (2/10 + 2/10) / 2
    assert abs(m["mae"] - 5 / 3) < 1e-9             # (1 + 2 + 2) / 3
    assert abs(m["bias"] - (-1 / 3)) < 1e-9         # (-1 - 2 + 2) / 3, 음수 = 적게 셈
