"""60초 예측 정확도 백테스트 (E6): 예측기들을 같은 timeline 에서 비교한다.

    python -m src.predict.evaluate --input data/processed/timeline/E04_070.json \\
                                   --predictors persistence linear flow --output data/processed/eval.json

시각 t 에서 최근 history_s 초만 보고 만든 예측을 t + horizon_s 의 실제 밀도와 비교한다.
- 시작 시각 t 는 history_s - 1 이상, 영상 끝에서 horizon_s 초 전까지다. 영상 마지막 60초는 정답이 없어 오차 계산에서 뺀다
  (예측값 자체는 timeline 에 저장된다).
- 기준선은 현재값 유지(persistence)다. 스킬 = 1 - RMSE / persistence RMSE (양수면 기준선보다 좋다).
- 기획서 3.3: 예측에는 합격 기준을 두지 않고 비교 결과를 그대로 공개한다.
- 지표는 두 벌이다: 모든 셀, 그리고 보행 면적 eval_min_cell_area_m2(기본 2㎡) 이상 셀만(*_core). 작은 셀의 오탐 잡음이
  오차를 부풀리므로 구역 등급과 같은 기준으로 따로 본다 (결정 2026-11-11 #4).
- timeline 에 속도(vx, vy)가 전혀 없으면 flow 는 persistence 와 같은 값이라 평가에서 빼고 경고한다.
※ 샘플 데이터(src.predict.sample)는 합성이라 점수 자체에는 의미가 없다. 실제 영상 기반 timeline 으로 같은 명령을 쓴다.
"""
from __future__ import annotations

import argparse
import json
import warnings
from dataclasses import asdict, dataclass, replace
from typing import List, Optional, Sequence

import numpy as np

from .config import PREDICTOR_NAMES, PredictConfig, load_config
from .io import assert_not_raw, load_timeline
from .model import (
    NO_VELOCITY_MESSAGE, CellLayout, has_velocity, make_predictor, require_unit_interval, to_arrays,
)
from .schema import Timeline


@dataclass
class PredictorMetrics:
    """예측기 하나의 E6 지표."""

    predictor: str
    n_frames: int                  # 평가에 쓴 시작 시각 t 개수
    n_cells: int                   # 셀-시각 표본 수
    mae: float                     # 평균절대오차 (명/㎡)
    rmse: float
    skill: Optional[float]         # 1 - rmse / persistence_rmse. persistence 자신은 0
    count_rel_err: float           # 구역 인원 합(밀도 × 보행 면적)의 평균 상대오차
    # 보행 면적이 min_area_m2 이상인 셀만 모은 지표. 작은 셀은 오탐 1명에도 밀도가 튀어 오차를 부풀린다
    # (결정 2026-11-11 #4: 구역 등급도 2㎡ 이상 셀만 쓴다). 해당 셀이 없으면 None.
    min_area_m2: float = 0.0
    n_cells_core: int = 0
    mae_core: Optional[float] = None
    rmse_core: Optional[float] = None
    skill_core: Optional[float] = None   # 1 - rmse_core / persistence 의 rmse_core


def _rel(pred_sum: float, truth_sum: float) -> float:
    """합계의 상대오차."""
    return abs(pred_sum - truth_sum) / max(truth_sum, 1e-9)


def _rmse(err: np.ndarray) -> float:
    """오차 배열의 RMSE."""
    return float(np.sqrt(np.mean(err ** 2)))


def _skill(rmse: float, base_rmse: Optional[float]) -> Optional[float]:
    """기준선(persistence) 대비 스킬. 기준선 오차가 0 에 가까우면 정의할 수 없어 None."""
    if base_rmse is None or base_rmse <= 1e-12:
        return None
    return 1.0 - rmse / base_rmse


def evaluate(
    timeline: Timeline, config: PredictConfig, predictors: Sequence[str] = PREDICTOR_NAMES
) -> List[PredictorMetrics]:
    """predictors 각각의 지표를 계산한다. 길이가 history_s + horizon_s 보다 짧으면 ValueError.

    - timeline 에 속도(vx, vy)가 전혀 없으면 flow 는 persistence 와 똑같은 값이 나와 비교가 무의미하다.
      그래서 평가에서 빼고 경고한다. flow 만 요청했다면 ValueError.
    - 표의 기본 지표는 모든 셀, *_core 지표는 보행 면적 config.eval_min_cell_area_m2 이상인 셀만 쓴다.
    """
    require_unit_interval(timeline.meta)
    hs, hz = config.history_s, config.horizon_s
    dens, vx, vy = to_arrays(timeline)
    total = dens.shape[0]
    t_first, t_last = hs - 1, total - 1 - hz
    if t_last < t_first:
        raise ValueError("평가에는 프레임이 {}개 이상 필요하다 (history_s {} + horizon_s {}), 현재 {}개".format(
            hs + hz, hs, hz, total))

    layout = CellLayout.from_meta(timeline.meta)
    area = layout.area_m2
    core = area >= config.eval_min_cell_area_m2
    names = list(predictors)
    if "flow" in names and not has_velocity(vx, vy):
        names = [n for n in names if n != "flow"]
        if not names:
            raise ValueError(NO_VELOCITY_MESSAGE)
        warnings.warn("속도(vx, vy)가 전혀 없어 flow 를 평가에서 뺐다 (persistence 와 같은 값이 나온다). "
                      "남은 예측기: {}".format(", ".join(names)), UserWarning, stacklevel=2)
    models = {n: make_predictor(replace(config, predictor=n)) for n in names}
    base = make_predictor(replace(config, predictor="persistence"))

    errs = {n: [] for n in names}          # 셀별 오차 배열들
    rels = {n: [] for n in names}
    base_errs: List[np.ndarray] = []
    for t in range(t_first, t_last + 1):
        hist = dens[t - hs + 1:t + 1]                    # t 까지의 기록만 쓴다
        truth = dens[t + hz]
        t_sum = float((truth * area).sum())
        base_errs.append(base.predict(layout, hist, vx[t], vy[t]) - truth)
        for n in names:
            pred = models[n].predict(layout, hist, vx[t], vy[t])
            errs[n].append(pred - truth)
            rels[n].append(_rel(float((pred * area).sum()), t_sum))

    base = np.stack(base_errs)                              # (평가 시각 수, 셀 수)
    prmse = _rmse(base)
    prmse_core = _rmse(base[:, core]) if core.any() else None
    results: List[PredictorMetrics] = []
    for n in names:
        e = np.stack(errs[n])
        rmse = _rmse(e)
        ec = e[:, core]
        has_core = bool(core.any())
        rmse_core = _rmse(ec) if has_core else None
        results.append(PredictorMetrics(
            predictor=n,
            n_frames=t_last - t_first + 1,
            n_cells=int(e.size),
            mae=float(np.mean(np.abs(e))),
            rmse=rmse,
            skill=_skill(rmse, prmse),
            count_rel_err=float(np.mean(rels[n])),
            min_area_m2=config.eval_min_cell_area_m2,
            n_cells_core=int(ec.size),
            mae_core=float(np.mean(np.abs(ec))) if has_core else None,
            rmse_core=rmse_core,
            skill_core=_skill(rmse_core, prmse_core) if rmse_core is not None else None,
        ))
    return results


def format_table(rows: Sequence[PredictorMetrics]) -> str:
    """결과를 표 문자열로 만든다."""
    def f(v: Optional[float], d: int = 3) -> str:
        return "-" if v is None else "{:.{}f}".format(v, d)

    min_area = rows[0].min_area_m2 if rows else 0.0
    head = ("예측기        프레임   셀표본 |    MAE    RMSE  스킬(vs persistence) | 인원 상대오차"
            " | {:.1f}㎡↑ 셀표본    MAE    RMSE  스킬").format(min_area)
    lines = [head, "-" * len(head)]
    for r in rows:
        lines.append("{:<12s} {:>6d} {:>8d} | {:>6s} {:>7s} {:>10s}           | {:>8.1%} | {:>10d} {:>6s} {:>7s} {:>5s}".format(
            r.predictor, r.n_frames, r.n_cells, f(r.mae), f(r.rmse), f(r.skill, 2), r.count_rel_err,
            r.n_cells_core, f(r.mae_core), f(r.rmse_core), f(r.skill_core, 2)))
    return "\n".join(lines)


def main(argv: Optional[Sequence[str]] = None) -> None:
    """CLI 진입점."""
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--input", required=True, help="timeline.json (history_s + horizon_s 초 이상)")
    ap.add_argument("--config", default=None, help="설정 YAML (기본: src/predict/config.yaml)")
    ap.add_argument("--predictors", nargs="+", choices=PREDICTOR_NAMES, default=list(PREDICTOR_NAMES),
                    help="비교할 예측기 (기본: 전부)")
    ap.add_argument("--output", default=None, help="지표 JSON 저장 경로 (data/raw/ 는 불가)")
    args = ap.parse_args(argv)

    cfg = load_config(args.config)
    rows = evaluate(load_timeline(args.input), cfg, args.predictors)
    print(format_table(rows))
    if args.output:
        assert_not_raw(args.output)
        with open(args.output, "w", encoding="utf-8") as fp:
            json.dump({"config": asdict(cfg), "results": [asdict(r) for r in rows]}, fp, ensure_ascii=False, indent=2)
        print("저장 완료: {}".format(args.output))


if __name__ == "__main__":
    main()
