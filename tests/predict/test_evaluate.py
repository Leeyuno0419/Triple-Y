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
    rows = _by_name(evaluate(tl, CFG, ["persistence", "linear"]))   # 속도가 없는 timeline 이라 flow 는 빼고 요청
    assert rows["persistence"].rmse == 0.0 and rows["persistence"].skill is None
    assert rows["linear"].rmse == pytest.approx(0.0, abs=1e-9)  # 변화가 없으면 직선도 평평


def test_linear_wins_on_steady_trend(make_timeline):
    dens = np.stack([np.full((2, 2), 1.0 + 0.01 * t) for t in range(100)])
    rows = _by_name(evaluate(make_timeline(dens), CFG, ["persistence", "linear"]))
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
    assert "2.0㎡↑" in text                                      # 큰 셀 지표 열 머리글에 기준 면적이 보인다


# --------------------------------------------------------------------------- #
# 속도가 없는 timeline 에서의 flow
# --------------------------------------------------------------------------- #
def test_flow_is_dropped_with_warning_when_timeline_has_no_velocity(make_timeline):
    tl = make_timeline(blob_series(100))                         # 속도 전부 null
    with pytest.warns(UserWarning, match="flow"):
        rows = evaluate(tl, CFG)
    assert [r.predictor for r in rows] == ["persistence", "linear"]


def test_flow_only_request_without_velocity_is_rejected(make_timeline):
    with pytest.raises(ValueError, match="속도"):
        evaluate(make_timeline(blob_series(100)), CFG, ["flow"])


def test_flow_is_kept_without_warning_when_velocity_exists(make_timeline, recwarn):
    rows = evaluate(make_timeline(blob_series(100), vx=0.2, vy=0.0), CFG)
    assert "flow" in [r.predictor for r in rows]
    assert not [w for w in recwarn if issubclass(w.category, UserWarning)]


# --------------------------------------------------------------------------- #
# 보행 면적이 작은 셀을 뺀 지표 (*_core)
# --------------------------------------------------------------------------- #
def _noisy_small_cell_timeline(make_timeline):
    """(0,0) 셀만 면적 1㎡(기준 2㎡ 미만)이고 밀도가 출렁인다. 나머지 셀은 일정하다."""
    dens = np.full((100, 2, 2), 1.5)
    dens[:, 0, 0] = 0.5 + 0.5 * (np.arange(100) % 7)             # 7초 주기 (60초와 나누어떨어지지 않아 60초 뒤가 달라진다)
    area = np.full((2, 2), 4.0)
    area[0, 0] = 1.0
    return make_timeline(dens, area=area)


def test_core_metrics_exclude_small_noisy_cells(make_timeline):
    r = evaluate(_noisy_small_cell_timeline(make_timeline), CFG, ["persistence"])[0]
    assert r.n_cells == r.n_frames * 4                           # 전체 지표는 4셀 모두
    assert r.n_cells_core == r.n_frames * 3                      # 큰 셀 지표는 면적 ≥ 2㎡ 인 3셀만
    assert r.rmse > 0.5                                          # 작은 셀의 출렁임이 전체 오차를 부풀린다
    assert r.rmse_core == pytest.approx(0.0, abs=1e-12)          # 큰 셀은 일정하므로 오차 0
    assert r.min_area_m2 == 2.0


def test_core_skill_is_none_when_baseline_core_error_is_zero(make_timeline):
    rows = _by_name(evaluate(_noisy_small_cell_timeline(make_timeline), CFG, ["persistence", "linear"]))
    assert rows["persistence"].skill_core is None               # 기준선 오차 0 → 스킬 정의 불가
    assert rows["persistence"].skill == pytest.approx(0.0)       # 전체 지표는 기준선이므로 0


def test_core_metrics_use_configured_threshold(make_timeline):
    cfg = PredictConfig(flow_decay_tau_s=0.0, eval_min_cell_area_m2=0.5)   # 1㎡ 셀도 포함
    r = evaluate(_noisy_small_cell_timeline(make_timeline), cfg, ["persistence"])[0]
    assert r.n_cells_core == r.n_cells
    assert r.rmse_core == pytest.approx(r.rmse)


def test_core_metrics_are_none_when_no_cell_is_large_enough(make_timeline):
    cfg = PredictConfig(flow_decay_tau_s=0.0, eval_min_cell_area_m2=100.0)
    r = evaluate(_noisy_small_cell_timeline(make_timeline), cfg, ["persistence"])[0]
    assert r.n_cells_core == 0 and r.mae_core is None and r.rmse_core is None and r.skill_core is None
    assert "-" in format_table([r])                              # 표에는 '-' 로 나온다
