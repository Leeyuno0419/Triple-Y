import json

import numpy as np
import pytest

from src.predict.config import PredictConfig, load_config
from src.predict.extrapolate import advect_density, extend_density_outside_view, fill_flow_outside_view
from src.predict.io import append_predictions, assert_not_raw, save_timeline
from src.predict.model import FlowExtrapolationPredictor
from src.predict.schema import (
    Bounds, Frame, Timeline, ZoneFrame, ZoneMeta, timeline_from_dict, timeline_to_dict,
)


def _meta(rows=5, cols=8):
    return ZoneMeta("Z01", "test", Bounds(37.0, 127.0, 37.001, 127.001), rows, cols, 10.0)


def test_default_config_loads():
    assert load_config().horizons_s


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


def test_fill_flow_extends_from_visible_region():
    visible = np.zeros((4, 6), bool); visible[:, :3] = True
    u = np.where(visible, 1.0, np.nan); v = np.where(visible, 0.0, np.nan)
    uf, vf = fill_flow_outside_view(u, v, visible, decay=0.9)
    assert np.isfinite(uf).all() and (uf[:, 3:] > 0).all()
    assert uf[0, 3] > uf[0, 5]  # 멀어질수록 감쇠


def test_predictor_moves_crowd_into_unobserved_cells():
    meta = _meta()
    dens = np.full((5, 8), np.nan); dens[:, :4] = 0.0; dens[2, 3] = 2.0   # 화각: 왼쪽 4열
    flow_u = np.where(np.isfinite(dens), 0.5, np.nan); flow_v = np.where(np.isfinite(dens), 0.0, np.nan)
    zf = ZoneFrame("Z01", dens, flow_u, flow_v, count=2.0 * meta.cell_area_m2)

    cfg = PredictConfig(horizons_s=[30.0, 60.0], flow_decay_tau_s=0.0, prior_mode="constant")
    preds = FlowExtrapolationPredictor(cfg).predict(meta, zf, cfg.horizons_s)

    assert [p.horizon_s for p in preds] == [30.0, 60.0]
    p30 = preds[0]
    assert p30.extrapolated[:, 4:].all() and not p30.extrapolated[:, :4].any()
    assert p30.density[:, 4:].sum() > 0  # 화각 밖으로 인파가 넘어감
    total0 = 2.0 * meta.cell_area_m2
    assert p30.count + p30.outflow_count == pytest.approx(total0)


def test_timeline_roundtrip_and_append_predictions(tmp_path):
    meta = _meta()
    dens = np.full((5, 8), np.nan); dens[:, :4] = 0.5
    zf = ZoneFrame("Z01", dens, np.full((5, 8), 0.2), np.zeros((5, 8)), count=10.0)
    tl = Timeline("0.1", [meta], [Frame("2026-11-10T09:00:00+09:00", "observed", [zf])])

    tl2 = timeline_from_dict(json.loads(json.dumps(timeline_to_dict(tl))))
    assert np.isnan(tl2.frames[0].zones[0].density[0, 7])

    cfg = PredictConfig(horizons_s=[30.0, 60.0])
    out = append_predictions(tl2, FlowExtrapolationPredictor(cfg), cfg.horizons_s)
    kinds = [f.kind for f in out.frames]
    assert kinds == ["observed", "predicted", "predicted"]
    assert out.frames[1].t.startswith("2026-11-10T09:00:30")
    assert len(tl2.frames) == 1  # 입력은 변경되지 않음

    save_timeline(out, tmp_path / "out.json")
    assert (tmp_path / "out.json").exists()


def test_raw_directory_is_protected(tmp_path):
    with pytest.raises(PermissionError):
        assert_not_raw(tmp_path / "data" / "raw" / "timeline.json")
    assert_not_raw(tmp_path / "data" / "processed" / "timeline.json")


# --------------------------------------------------------------------------- #
# 이류 방식 비교 (TVD vs 1차 upwind)
# --------------------------------------------------------------------------- #
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


# --------------------------------------------------------------------------- #
# 화각 밖 초기 밀도 연장
# --------------------------------------------------------------------------- #
def _half_view(rows=5, cols=10, view_cols=5, value=4.0):
    visible = np.zeros((rows, cols), bool); visible[:, :view_cols] = True
    dens = np.where(visible, value, np.nan)
    return dens, visible


def test_extend_density_decays_with_distance_and_keeps_visible():
    dens, visible = _half_view()
    out = extend_density_outside_view(dens, visible, decay=0.5, max_cells=3)
    assert (out[:, :5] == 4.0).all()                                   # 화각 안은 그대로
    assert out[2, 5] == pytest.approx(2.0)                             # 경계 4.0 × 0.5
    assert out[2, 6] == pytest.approx(1.0)
    assert out[2, 7] == pytest.approx(0.5)
    assert (out[:, 8:] == 0.0).all()                                   # max_cells(3) 밖은 사전값
    assert np.isfinite(out).all()


def test_extend_density_respects_floor_and_empty_view():
    dens, visible = _half_view(value=0.0)
    out = extend_density_outside_view(dens, visible, decay=0.8, max_cells=2, floor=0.3)
    assert np.allclose(out[:, 5:], 0.3)                  # 연장값이 floor 미만이면 floor
    nothing = extend_density_outside_view(np.full((3, 3), np.nan), np.zeros((3, 3), bool), floor=0.2)
    assert (nothing == 0.2).all()


def test_extend_mode_keeps_more_than_constant_at_boundary():
    meta = _meta(rows=5, cols=10)
    dens, visible = _half_view(rows=5, cols=10, view_cols=5, value=4.0)
    flow_u = np.where(visible, 0.05, np.nan); flow_v = np.where(visible, 0.0, np.nan)
    zf = ZoneFrame("Z01", dens, flow_u, flow_v, count=4.0 * 25 * meta.cell_area_m2)
    kw = dict(horizons_s=[30.0], flow_decay_tau_s=0.0)
    ext = FlowExtrapolationPredictor(PredictConfig(prior_mode="extend", **kw)).predict(meta, zf, [30.0])[0]
    con = FlowExtrapolationPredictor(PredictConfig(prior_mode="constant", **kw)).predict(meta, zf, [30.0])[0]
    assert ext.density.max() > con.density.max()                       # 경계 절벽이 사라져 정점 유지
    assert ext.count > con.count                                       # 추정 인원이 더해진다
    assert ext.density[:, :5].min() > con.density[:, :5].min() - 1e-9
    # 어느 쪽이든 질량은 보존(격자 안 + 유출)
    area = meta.cell_area_m2
    init_ext = extend_density_outside_view(dens, visible, 0.8, 3).sum() * area
    assert ext.count + ext.outflow_count == pytest.approx(init_ext)


def test_invalid_prior_config_rejected():
    for bad in (dict(prior_mode="nope"), dict(extend_decay=1.5), dict(extend_max_cells=-1),
                dict(prior_density=-0.1)):
        with pytest.raises(ValueError):
            PredictConfig(**bad)


def test_invalid_scheme_rejected():
    with pytest.raises(ValueError):
        advect_density(np.ones((3, 3)), np.zeros((3, 3)), np.zeros((3, 3)), 1.0, scheme="nope")
    with pytest.raises(ValueError):
        PredictConfig(scheme="nope")
