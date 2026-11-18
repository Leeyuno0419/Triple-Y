"""ML 60초 예측 (ml_forecast, synthetic, train_forecast, MLPredictor) 테스트."""
from dataclasses import replace

import numpy as np
import pytest

from src.predict.config import PredictConfig
from src.predict.ml_forecast import (
    ForecastBundle, build_windows, compute_features, feature_names, linear_baseline, load_bundle, make_xy,
    save_bundle,
)
from src.predict.model import LinearTrendPredictor, fill_predictions, make_predictor
from src.predict.synthetic import make_synthetic_density, make_synthetic_series
from src.predict.train_forecast import make_model, score, split_series

N_LAGS = 10


# --------------------------------------------------------------------------- #
# 피처
# --------------------------------------------------------------------------- #
def test_feature_count_matches_names():
    w = np.random.default_rng(0).random((3, 5, 30))
    assert compute_features(w, N_LAGS).shape == (3, 5, len(feature_names(N_LAGS)))


def test_constant_window_has_zero_change_features():
    f = compute_features(np.full((1, 30), 2.5), N_LAGS)[0]
    names = feature_names(N_LAGS)
    assert f[names.index("cur")] == 2.5
    for k in names[1:]:
        assert f[names.index(k)] == pytest.approx(0.0), k


def test_rising_window_has_positive_slope_and_diffs():
    f = compute_features(np.arange(30, dtype=float)[None] * 0.1, N_LAGS)[0]    # 1초에 0.1 씩 오른다
    names = feature_names(N_LAGS)
    assert f[names.index("slope_short")] == pytest.approx(0.1)
    assert f[names.index("slope_full")] == pytest.approx(0.1)
    assert f[names.index("diff_3s")] == pytest.approx(0.3)                      # 지금 − 3초 전
    assert f[names.index("mean_minus_cur")] < 0                                 # 평균이 지금보다 낮다


def test_too_short_window_rejected():
    with pytest.raises(ValueError):
        compute_features(np.zeros((1, N_LAGS - 1)), N_LAGS)


# --------------------------------------------------------------------------- #
# 학습 표본: 미래 값이 입력에 새어 들어가지 않는다
# --------------------------------------------------------------------------- #
def test_build_windows_input_ends_at_t_and_target_is_t_plus_horizon():
    dens = np.arange(200, dtype=float)[:, None]                  # 값 = 시각
    win, target = build_windows(dens, history_s=30, horizon_s=60)
    assert win.shape == (111, 1, 30) and target.shape == (111, 1)
    for i in (0, 50, 110):
        t = i + 29
        assert win[i, 0, -1] == t and win[i, 0, 0] == t - 29     # 입력은 t-29..t 만
        assert target[i, 0] == t + 60                            # 정답은 t+60


def test_build_windows_too_short_raises():
    with pytest.raises(ValueError):
        build_windows(np.zeros((89, 2)), 30, 60)


def test_make_xy_target_is_delta_and_lin_matches_predictor():
    dens = np.random.default_rng(1).random((150, 3))
    X, y, cur, lin = make_xy([dens], 30, 60, N_LAGS)
    assert X.shape == (61 * 3, N_LAGS + 4) and y.shape == cur.shape == lin.shape == (61 * 3,)
    win, target = build_windows(dens, 30, 60)
    assert np.allclose(cur + y, target.reshape(-1))              # 정답 = 지금 + 변화량
    lp = LinearTrendPredictor(PredictConfig(predictor="linear"))
    expect = np.stack([lp.predict(None, win[i].T, None, None) for i in range(win.shape[0])]).reshape(-1)
    assert np.allclose(lin, expect)                              # 직선 추세 기준선이 기존 예측기와 같다


# --------------------------------------------------------------------------- #
# 합성 데이터 · 분할
# --------------------------------------------------------------------------- #
def test_synthetic_is_reproducible_nonnegative_and_rounded():
    a = make_synthetic_density(np.random.default_rng(3), 3, 4, 300)
    b = make_synthetic_density(np.random.default_rng(3), 3, 4, 300)
    assert a.shape == (300, 12) and np.array_equal(a, b)
    assert (a >= 0).all() and np.allclose(a, np.round(a, 2))
    assert a.max() > 1.0                                         # 파동이 실제로 나타난다
    s1, s2 = make_synthetic_series(2, seed=7, duration_s=200), make_synthetic_series(2, seed=7, duration_s=200)
    assert all(np.array_equal(x, y) for x, y in zip(s1, s2)) and not np.array_equal(s1[0], s1[1])


@pytest.mark.parametrize("n", [3, 5, 24])
def test_split_series_partitions_without_overlap(n):
    tr, va, te = split_series(n, seed=42)
    assert sorted(tr + va + te) == list(range(n))
    assert tr and va and te
    assert split_series(n, seed=42) == (tr, va, te)              # 같은 seed 면 같은 분할


def test_split_series_needs_three():
    with pytest.raises(ValueError):
        split_series(2, seed=0)


# --------------------------------------------------------------------------- #
# 저장 · MLPredictor · timeline 연동
# --------------------------------------------------------------------------- #
@pytest.fixture
def model_file(tmp_path):
    """작은 합성 데이터로 Ridge 를 빠르게 학습해 저장하고 경로를 돌려준다."""
    series = make_synthetic_series(4, seed=0, rows=2, cols=3, duration_s=400)
    X, y, _, _ = make_xy(series, 30, 60, N_LAGS, stride=5)
    meta = {"kind": "ridge", "n_lags": N_LAGS, "history_s": 30, "horizon_s": 60, "trained_on": "synthetic"}
    path = tmp_path / "m.joblib"
    save_bundle(ForecastBundle(make_model("ridge", 10.0, 0).fit(X, y), meta), path)
    return path


def test_bundle_roundtrip_predicts_nonnegative_per_cell(model_file):
    bundle = load_bundle(model_file)
    hist = np.abs(np.random.default_rng(5).normal(2.0, 0.5, (30, 7)))
    pred = bundle.predict(hist)
    assert pred.shape == (7,) and (pred >= 0).all() and np.isfinite(pred).all()


def test_missing_model_file_gives_hint(tmp_path):
    with pytest.raises(FileNotFoundError, match="train_forecast"):
        load_bundle(tmp_path / "none.joblib")


def _series(steps=100, rows=2, cols=3):
    t = np.arange(steps, dtype=float)[:, None, None]
    return np.clip(1.0 + 0.02 * t + 0.3 * np.sin(t / 7.0), 0, None) * np.ones((steps, rows, cols))


def test_ml_predictor_fills_timeline_like_other_predictors(make_timeline, model_file):
    cfg = PredictConfig(predictor="ml", model_path=str(model_file))
    out = fill_predictions(make_timeline(_series()), make_predictor(cfg))
    first = [f.cells[0].density_pred_60s for f in out.frames]
    assert all(v is None for v in first[:29]) and all(v is not None and v >= 0 for v in first[29:])
    assert out.meta.models.predictor == "ml-ridge-synthetic"     # 어떤 데이터로 학습했는지 남는다
    assert (out.meta.prediction.history_s, out.meta.prediction.horizon_s) == (30, 60)


def test_ml_prediction_at_t_never_uses_future_frames(make_timeline, model_file):
    cfg = PredictConfig(predictor="ml", model_path=str(model_file))
    a = _series()
    b = a.copy(); b[41:] = 9.0                                   # t=41 이후만 다르다
    out_a = fill_predictions(make_timeline(a), make_predictor(cfg))
    out_b = fill_predictions(make_timeline(b), make_predictor(cfg))
    for t in range(0, 41):
        assert [c.density_pred_60s for c in out_a.frames[t].cells] == [c.density_pred_60s for c in out_b.frames[t].cells]
    assert [c.density_pred_60s for c in out_a.frames[60].cells] != [c.density_pred_60s for c in out_b.frames[60].cells]


@pytest.mark.parametrize("change", [dict(history_s=20), dict(horizon_s=30)])
def test_ml_predictor_rejects_config_mismatch(model_file, change):
    cfg = replace(PredictConfig(predictor="ml", model_path=str(model_file)), **change)
    with pytest.raises(ValueError, match="다시 학습"):
        make_predictor(cfg)


def test_score_mae_rmse():
    s = score(np.array([1.0, 2.0, 5.0]), np.array([1.0, 4.0, 2.0]))
    assert s.mae == pytest.approx(5 / 3) and s.rmse == pytest.approx(np.sqrt(13 / 3))
