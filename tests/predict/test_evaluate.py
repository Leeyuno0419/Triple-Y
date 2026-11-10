import numpy as np
import pytest

from src.predict.config import PredictConfig
from src.predict.evaluate import evaluate, format_table
from src.predict.schema import Bounds, Frame, Timeline, ZoneFrame, ZoneMeta, shift_iso

T0 = "2026-11-10T09:00:00+09:00"
ROWS, COLS = 5, 20


def _blob(center, sigma=1.5, peak=2.0):
    x = np.arange(COLS)
    return np.tile(peak * np.exp(-((x - center) ** 2) / (2 * sigma ** 2)), (ROWS, 1))


def _timeline(n=4, step_s=10.0, speed=0.1, start=3.0, view_cols_first=None):
    """덩어리가 동쪽으로 speed 칸/초로 이동하는 합성 데이터.
    view_cols_first 를 주면 첫 프레임만 왼쪽 그 열 수까지만 화각 안이다."""
    meta = ZoneMeta("Z01", "test", Bounds(37.0, 127.0, 37.001, 127.001), ROWS, COLS, 10.0)
    frames = []
    for k in range(n):
        dens = _blob(start + speed * step_s * k)
        vis = np.ones((ROWS, COLS), bool)
        if k == 0 and view_cols_first is not None:
            vis[:, view_cols_first:] = False
        dens = np.where(vis, dens, np.nan)
        u = np.where(vis, speed, np.nan)
        v = np.where(vis, 0.0, np.nan)
        frames.append(Frame(shift_iso(T0, step_s * k), "observed", [ZoneFrame("Z01", dens, u, v, count=1.0)]))
    return Timeline("0.1", [meta], frames)


CFG = dict(flow_decay_tau_s=0.0, prior_mode="constant")


def test_model_beats_persistence_on_moving_blob():
    cfg = PredictConfig(horizons_s=[10.0, 20.0], **CFG)
    rows = evaluate(_timeline(), cfg, [10.0, 20.0])
    assert [r.horizon_s for r in rows] == [10.0, 20.0]
    for r in rows:
        assert r.skill is not None and r.skill > 0.5      # 이동을 따라가므로 정지 가정보다 훨씬 낫다
        assert r.rmse < r.persist_rmse
        assert r.count_rel_err <= r.persist_count_rel_err + 1e-9   # 덩어리가 격자 안에 있어 합은 둘 다 같다
    assert rows[0].n_samples == 3 and rows[1].n_samples == 2   # 4프레임: +10s 3쌍, +20s 2쌍


def test_horizon_without_truth_is_omitted():
    rows = evaluate(_timeline(), PredictConfig(horizons_s=[10.0], **CFG), [10.0, 300.0])
    assert [r.horizon_s for r in rows] == [10.0]


def test_outside_view_cells_are_scored_separately():
    # 첫 프레임은 왼쪽 12열만 보이고, 이후 프레임은 전체가 보인다 → 화각 밖→안 셀이 생긴다
    tl = _timeline(view_cols_first=12, start=9.0)
    cfg = PredictConfig(horizons_s=[20.0], **CFG)
    r = evaluate(tl, cfg, [20.0])[0]
    assert r.outside_n_cells > 0
    assert r.outside_mae is not None and r.outside_persist_mae is not None


def test_needs_two_observed_frames_and_sorted_time():
    with pytest.raises(ValueError):
        evaluate(_timeline(n=1), PredictConfig(**CFG), [10.0])
    tl = _timeline()
    tl.frames.reverse()
    with pytest.raises(ValueError):
        evaluate(tl, PredictConfig(**CFG), [10.0])


def test_format_table_renders_rows():
    rows = evaluate(_timeline(), PredictConfig(horizons_s=[10.0], **CFG), [10.0])
    text = format_table(rows)
    assert "10s" in text and "RMSE" in text
