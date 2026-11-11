import numpy as np
import pytest

from predict_helpers import blob_series
from src.predict.config import PredictConfig
from src.predict.evaluate import evaluate, format_table

CFG = PredictConfig(flow_decay_tau_s=0.0)


def _by_name(rows):
    return {r.predictor: r for r in rows}


def test_flow_beats_persistence_on_moving_blob(make_timeline):
    tl = make_timeline(blob_series(100), vx=0.2, vy=0.0)        # 0.1 셀/초로 이동, 속도 정보 있음
    rows = _by_name(evaluate(tl, CFG))
    assert rows["persistence"].skill == pytest.approx(0.0)
    assert rows["flow"].skill is not None and rows["flow"].skill > 0.5
    assert rows["flow"].rmse < rows["persistence"].rmse
    assert rows["flow"].mae < rows["persistence"].mae


def test_frame_count_excludes_last_horizon_and_initial_history(make_timeline):
    tl = make_timeline(blob_series(100), vx=0.2, vy=0.0)
    r = evaluate(tl, CFG, ["persistence"])[0]
    assert r.n_frames == 100 - 30 - 60 + 1                      # t = 29 .. 39
    assert r.n_cells == r.n_frames * 3 * 20


def test_perfect_persistence_gives_no_skill(make_timeline):
    tl = make_timeline(np.full((100, 2, 2), 1.5))
    rows = _by_name(evaluate(tl, CFG))
    assert rows["persistence"].rmse == 0.0 and rows["persistence"].skill is None
    assert rows["linear"].rmse == pytest.approx(0.0, abs=1e-9)  # 변화가 없으면 직선도 평평


def test_linear_wins_on_steady_trend(make_timeline):
    dens = np.stack([np.full((2, 2), 1.0 + 0.01 * t) for t in range(100)])
    rows = _by_name(evaluate(make_timeline(dens), CFG))
    assert rows["linear"].rmse == pytest.approx(0.0, abs=1e-9)
    assert rows["persistence"].rmse > 0.5                       # 60초 × 0.01 = 0.6 만큼 틀린다


def test_too_short_timeline_is_rejected(make_timeline):
    tl = make_timeline(blob_series(89), vx=0.2, vy=0.0)         # history 30 + horizon 60 = 90 미만
    with pytest.raises(ValueError):
        evaluate(tl, CFG)
    evaluate(make_timeline(blob_series(90), vx=0.2, vy=0.0), CFG)   # 90 이면 평가 가능


def test_only_one_second_interval_supported(make_timeline):
    with pytest.raises(ValueError):
        evaluate(make_timeline(blob_series(100), interval_s=2), CFG)


def test_format_table_renders_rows(make_timeline):
    text = format_table(evaluate(make_timeline(blob_series(100), vx=0.2, vy=0.0), CFG))
    assert "RMSE" in text and "persistence" in text and "flow" in text
