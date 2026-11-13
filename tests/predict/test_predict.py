import numpy as np
import pytest

from predict_helpers import blob_series
from src.predict.config import PredictConfig, load_config
from src.predict.extrapolate import advect_density
from src.predict.io import assert_not_raw, load_timeline, save_timeline
from src.predict.model import (
    CellLayout, FlowAdvectionPredictor, LinearTrendPredictor, PersistencePredictor,
    fill_predictions, has_velocity, make_predictor, to_arrays,
)


# --------------------------------------------------------------------------- #
# 설정
# --------------------------------------------------------------------------- #
def test_default_config_loads_with_spec_values():
    cfg = load_config()
    assert (cfg.history_s, cfg.horizon_s) == (30, 60)
    assert cfg.predictor == "persistence"
    assert cfg.eval_min_cell_area_m2 == 2.0        # 구역 등급과 같은 기준 (결정 2026-11-11 #4)


@pytest.mark.parametrize("bad", [dict(predictor="nope"), dict(history_s=1), dict(horizon_s=0),
                                 dict(scheme="nope"), dict(step_s=0), dict(cfl_max=1.5),
                                 dict(eval_min_cell_area_m2=-1.0)])
def test_invalid_config_rejected(bad):
    with pytest.raises(ValueError):
        PredictConfig(**bad)


# --------------------------------------------------------------------------- #
# 예측기
# --------------------------------------------------------------------------- #
def _layout(make_timeline, rows=3, cols=20, area=None):
    return CellLayout.from_meta(make_timeline(np.zeros((1, rows, cols)), area=area).meta)


def _hist(dens):
    """(T, rows, cols) → (T, N)"""
    return dens.reshape(dens.shape[0], -1)


def test_persistence_returns_current_value(make_timeline):
    dens = np.random.RandomState(0).rand(30, 2, 3)
    pred = PersistencePredictor(PredictConfig()).predict(_layout(make_timeline, 2, 3), _hist(dens), None, None)
    assert np.allclose(pred, dens[-1].ravel())


def test_linear_extends_a_straight_line_exactly(make_timeline):
    steps = 30
    dens = np.stack([np.full((2, 2), 1.0 + 0.01 * t) for t in range(steps)])
    pred = LinearTrendPredictor(PredictConfig()).predict(_layout(make_timeline, 2, 2), _hist(dens), None, None)
    assert np.allclose(pred, 1.0 + 0.01 * (steps - 1 + 60))


def test_linear_never_goes_negative(make_timeline):
    dens = np.stack([np.full((1, 2), 1.0 - 0.03 * t) for t in range(30)])   # 빠르게 줄어드는 추세
    pred = LinearTrendPredictor(PredictConfig()).predict(_layout(make_timeline, 1, 2), _hist(dens), None, None)
    assert (pred == 0.0).all()


def test_flow_moves_crowd_and_conserves_people(make_timeline):
    dens = blob_series(30)                                      # 덩어리는 마지막 시각에 col ≈ 4.9
    area = np.full((3, 20), 4.0); area[0] = 3.2                 # 행마다 보행 면적이 다르다
    layout = _layout(make_timeline, area=area)
    cfg = PredictConfig(predictor="flow", flow_decay_tau_s=0.0)
    n = layout.row.size
    vx = np.full(n, 0.2)                                        # 0.2 m/s ÷ 2 m = 0.1 셀/초 → 60초에 6칸
    pred = FlowAdvectionPredictor(cfg).predict(layout, _hist(dens), vx, np.zeros(n)).reshape(3, 20)

    cols = np.arange(20)
    centroid = lambda g: float((g[1] * cols).sum() / g[1].sum())
    assert centroid(pred) - centroid(dens[-1]) == pytest.approx(6.0, abs=0.7)
    assert (pred * area).sum() == pytest.approx((dens[-1] * area).sum(), rel=1e-6)   # 인원 보존(면적 가중)


def test_flow_without_velocity_equals_persistence(make_timeline):
    dens = blob_series(30)
    layout = _layout(make_timeline)
    nan = np.full(layout.row.size, np.nan)
    pred = FlowAdvectionPredictor(PredictConfig(predictor="flow")).predict(layout, _hist(dens), nan, nan)
    assert np.allclose(pred, dens[-1].ravel())


def test_has_velocity_false_only_when_everything_is_null():
    nan = np.full((5, 3), np.nan)
    assert not has_velocity(nan, nan)
    some = nan.copy()
    some[2, 1] = 0.1
    assert has_velocity(some, nan) and has_velocity(nan, some)     # 하나라도 있으면 True


def test_fill_predictions_rejects_flow_when_timeline_has_no_velocity(make_timeline):
    tl = make_timeline(blob_series(100))                           # 속도 전부 null
    with pytest.raises(ValueError, match="속도"):
        fill_predictions(tl, make_predictor(PredictConfig(predictor="flow")))
    for name in ("persistence", "linear"):                         # 속도가 필요 없는 예측기는 그대로 된다
        fill_predictions(tl, make_predictor(PredictConfig(predictor=name)))


# --------------------------------------------------------------------------- #
# timeline 에 예측 채우기
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("name", ["persistence", "linear", "flow"])
def test_fill_predictions_nulls_before_history_and_valid_after(make_timeline, tmp_path, name):
    tl = make_timeline(blob_series(100), vx=0.2, vy=0.0)
    cfg = PredictConfig(predictor=name)
    out = fill_predictions(tl, make_predictor(cfg))

    first = [f.cells[0].density_pred_60s for f in out.frames]
    assert all(v is None for v in first[:29]) and all(v is not None for v in first[29:])
    assert out.meta.models.predictor == name
    assert (out.meta.prediction.history_s, out.meta.prediction.horizon_s) == (30, 60)
    assert all(c.density_pred_60s is None for c in tl.frames[50].cells)      # 입력은 변경되지 않음

    save_timeline(out, tmp_path / "out.json")                                # 규격 검증 통과 + 저장
    back = load_timeline(tmp_path / "out.json")
    assert back.frames[60].cells[5].density_pred_60s == pytest.approx(out.frames[60].cells[5].density_pred_60s, abs=0.01)


@pytest.mark.parametrize("name", ["persistence", "linear", "flow"])
def test_prediction_at_t_never_uses_future_frames(make_timeline, name):
    a = blob_series(100)
    b = a.copy(); b[41:] = 9.0                                  # t=41 이후만 다르다
    out_a = fill_predictions(make_timeline(a, vx=0.2, vy=0.0), make_predictor(PredictConfig(predictor=name)))
    out_b = fill_predictions(make_timeline(b, vx=0.2, vy=0.0), make_predictor(PredictConfig(predictor=name)))
    for t in range(0, 41):
        pa = [c.density_pred_60s for c in out_a.frames[t].cells]
        pb = [c.density_pred_60s for c in out_b.frames[t].cells]
        assert pa == pb, "t={} 의 예측이 미래 값에 영향을 받았다".format(t)
    assert [c.density_pred_60s for c in out_a.frames[60].cells] != [c.density_pred_60s for c in out_b.frames[60].cells]


def test_only_one_second_interval_supported(make_timeline):
    tl = make_timeline(blob_series(40), interval_s=2)
    with pytest.raises(ValueError):
        fill_predictions(tl, make_predictor(PredictConfig()))


def test_to_arrays_maps_null_to_nan(make_timeline):
    dens, vx, vy = to_arrays(make_timeline(np.ones((2, 1, 2))))
    assert dens.shape == (2, 2) and np.isnan(vx).all() and np.isnan(vy).all()


def test_save_refuses_spec_violation(make_timeline, tmp_path):
    tl = make_timeline(blob_series(40))
    tl.frames[10].cells[0].density_pred_60s = 1.0               # t < 29 에서 예측값이 있으면 위반
    with pytest.raises(ValueError):
        save_timeline(tl, tmp_path / "bad.json")


def test_raw_directory_is_protected(tmp_path):
    with pytest.raises(PermissionError):
        assert_not_raw(tmp_path / "data" / "raw" / "timeline.json")
    assert_not_raw(tmp_path / "data" / "processed" / "timeline.json")


# --------------------------------------------------------------------------- #
# 이류 방식 비교 (TVD vs 1차 upwind)
# --------------------------------------------------------------------------- #
def test_advect_conserves_mass_with_closed_flow():
    d = np.zeros((5, 8)); d[2, 2] = 1.0
    u = np.full_like(d, 0.5); v = np.zeros_like(d)
    out, outflow = advect_density(d, u, v, dt=4.0)
    assert outflow == pytest.approx(0.0, abs=1e-9)
    assert out.sum() == pytest.approx(d.sum())
    assert out[2, 4:].sum() > out[2, :4].sum()  # 동쪽으로 이동


def test_advect_reports_outflow_and_balances_mass():
    d = np.zeros((3, 4)); d[1, 3] = 1.0
    u = np.full_like(d, 1.0); v = np.zeros_like(d)
    out, outflow = advect_density(d, u, v, dt=2.0)
    assert outflow > 0
    assert out.sum() + outflow == pytest.approx(d.sum())
    assert (out >= 0).all()


def _gaussian_strip(cols=60, center=6.0, sigma=1.5, rows=5):
    x = np.arange(cols)
    row = np.exp(-((x - center) ** 2) / (2 * sigma ** 2))
    return np.tile(row, (rows, 1))


def _spread(row):
    """분포의 분산(칸²) — 값이 커질수록 많이 번진 것."""
    x = np.arange(row.size); mean = (row * x).sum() / row.sum()
    return float((row * (x - mean) ** 2).sum() / row.sum())


def test_tvd_spreads_much_less_than_upwind():
    d = _gaussian_strip()                                   # 초기 분산 = 1.5² = 2.25
    u = np.full_like(d, 0.4); v = np.zeros_like(d)          # 37.5초 → 15칸 이동
    up, _ = advect_density(d, u, v, dt=37.5, scheme="upwind")
    tvd, _ = advect_density(d, u, v, dt=37.5, scheme="tvd")
    growth_up = _spread(up[0]) - 2.25                       # 이론 수치확산 ≈ 7.5 (측정 7.5)
    growth_tvd = _spread(tvd[0]) - 2.25                     # 측정 ≈ 1.4
    assert growth_up == pytest.approx(7.5, abs=0.5)         # 1차 방식이 이론대로 번지는지(기준선)
    assert growth_tvd < 0.3 * growth_up                     # TVD 는 번짐이 1/3 미만
    assert tvd.max() > up.max() + 0.15                      # 정점도 더 높게 유지
    assert abs(np.argmax(tvd[0]) - (6 + 15)) <= 1           # 위치 정확
    assert tvd.sum() == pytest.approx(d.sum())              # 격자 안에 있는 동안 총량 동일


@pytest.mark.parametrize("scheme", ["tvd", "upwind"])
def test_schemes_conserve_mass_and_stay_nonnegative(scheme):
    rng = np.random.RandomState(0)
    d = rng.rand(7, 9) * 3.0
    u = rng.uniform(-0.4, 0.4, d.shape); v = rng.uniform(-0.4, 0.4, d.shape)
    out, outflow = advect_density(d, u, v, dt=20.0, scheme=scheme)
    assert (out >= 0).all()
    assert out.sum() + outflow == pytest.approx(d.sum(), rel=1e-9)


def test_tvd_preserves_uniform_field_and_no_new_maxima():
    flat = np.full((6, 10), 2.0)
    u = np.full_like(flat, 0.2); v = np.full_like(flat, 0.1)
    out, _ = advect_density(flat, u, v, dt=5.0)
    assert out[1:-1, 2:-1].max() == pytest.approx(2.0, abs=1e-9)   # 안쪽은 균일 유지

    d = _gaussian_strip()
    out, _ = advect_density(d, np.full_like(d, 0.3), np.zeros_like(d), dt=30.0)
    assert out.max() <= d.max() + 1e-9                              # 새 극댓값(오버슈트) 없음


def test_invalid_scheme_rejected():
    with pytest.raises(ValueError):
        advect_density(np.ones((3, 3)), np.zeros((3, 3)), np.zeros((3, 3)), 1.0, scheme="nope")
