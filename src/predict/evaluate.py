"""예측 정확도 백테스트: 관측 프레임끼리 "과거 → 미래"로 예측을 검증한다.

    python -m src.predict.evaluate --input data/processed/timeline.json \\
                                   --horizons 30 60 120 --output data/processed/eval.json

관측 프레임 i 를 시작점으로 horizon 초 뒤의 예측을 만들고, 그 시점에 가장 가까운 관측 프레임 j 와 비교한다.
- 정답(truth)은 j 의 화각 안(NaN 아님) 셀만 쓴다. 화각 밖의 실제 값은 알 수 없으므로 평가하지 않는다.
- 기준선(persistence) = 이동 없이 시작 시점 밀도를 그대로 쓰는 "정지 가정". 모델이 이보다 좋아야 의미가 있다.
- "화각 밖→안" 지표: 시작 시점엔 화각 밖이었다가 정답 시점에 화각 안에서 관측된 셀만 따로 본다.
  이 모듈의 존재 이유(화각 밖 예측)를 직접 재는 값이다.
※ 지금 샘플 데이터는 합성이라 점수 자체에는 의미가 없다. 실제 영상 기반 timeline 이 생기면 같은 명령으로 평가한다.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from typing import Dict, List, Optional, Sequence

import numpy as np

from .config import PredictConfig, load_config
from .io import assert_not_raw, load_timeline
from .model import FlowExtrapolationPredictor
from .schema import Timeline, parse_iso


@dataclass
class HorizonMetrics:
    horizon_s: float
    n_samples: int                         # (시작 프레임, 구역) 쌍 개수
    n_cells: int                           # 평가에 쓴 셀 수
    mae: float                             # 모델 평균절대오차 (명/m²)
    rmse: float
    persist_mae: float                     # 기준선(정지 가정)
    persist_rmse: float
    skill: Optional[float]                 # 1 - rmse/persist_rmse (양수면 기준선보다 좋음)
    outside_n_cells: int                   # 화각 밖→안 셀 수
    outside_mae: Optional[float]
    outside_persist_mae: Optional[float]
    count_rel_err: float                   # 화각 안 영역 인원합의 평균 상대오차
    persist_count_rel_err: float


class _Acc:
    def __init__(self) -> None:
        self.n_samples = 0
        self.err = []        # 모델 오차 배열들
        self.perr = []       # 기준선 오차 배열들
        self.oerr = []       # 화각 밖→안 셀 모델 오차
        self.operr = []
        self.crel = []
        self.pcrel = []


def _rel(pred_sum: float, truth_sum: float) -> float:
    return abs(pred_sum - truth_sum) / max(truth_sum, 1e-9)


def evaluate(
    timeline: Timeline,
    config: PredictConfig,
    horizons_s: Sequence[float],
    tol_s: Optional[float] = None,
) -> List[HorizonMetrics]:
    """horizons_s 별 지표. 정답이 될 관측 프레임이 없는 horizon 은 결과에서 빠진다."""
    obs = [f for f in timeline.frames if f.kind == "observed"]
    if len(obs) < 2:
        raise ValueError("평가에는 관측 프레임이 2개 이상 필요하다")
    secs = np.array([parse_iso(f.t).timestamp() for f in obs])
    if np.any(np.diff(secs) <= 0):
        raise ValueError("관측 프레임이 시간순(오름차순)이어야 한다")
    tol = tol_s if tol_s is not None else 0.5 * float(np.min(np.diff(secs)))

    metas: Dict[str, object] = {z.zone_id: z for z in timeline.zones}
    predictor = FlowExtrapolationPredictor(config)
    horizons = sorted(set(float(h) for h in horizons_s))
    acc = {h: _Acc() for h in horizons}

    for i, f0 in enumerate(obs):
        for zf0 in f0.zones:
            meta = metas.get(zf0.zone_id)
            if meta is None:
                continue
            preds = {p.horizon_s: p for p in predictor.predict(meta, zf0, horizons)}
            base = predictor.initial_density(zf0)
            was_visible = np.isfinite(zf0.density)

            for h in horizons:
                dt = secs[i + 1:] - secs[i]
                if dt.size == 0:
                    continue
                k = int(np.argmin(np.abs(dt - h)))
                if abs(dt[k] - h) > tol:
                    continue
                zf1 = next((z for z in obs[i + 1 + k].zones if z.zone_id == zf0.zone_id), None)
                if zf1 is None:
                    continue
                truth = zf1.density
                tv = np.isfinite(truth)
                if not tv.any():
                    continue

                e = preds[h].density[tv] - truth[tv]
                pe = base[tv] - truth[tv]
                a = acc[h]
                a.n_samples += 1
                a.err.append(e)
                a.perr.append(pe)
                out = tv & ~was_visible
                if out.any():
                    a.oerr.append(preds[h].density[out] - truth[out])
                    a.operr.append(base[out] - truth[out])
                t_sum = float(truth[tv].sum())
                a.crel.append(_rel(float(preds[h].density[tv].sum()), t_sum))
                a.pcrel.append(_rel(float(base[tv].sum()), t_sum))

    results: List[HorizonMetrics] = []
    for h in horizons:
        a = acc[h]
        if a.n_samples == 0:
            continue
        e, pe = np.concatenate(a.err), np.concatenate(a.perr)
        rmse, prmse = float(np.sqrt(np.mean(e ** 2))), float(np.sqrt(np.mean(pe ** 2)))
        oe = np.concatenate(a.oerr) if a.oerr else np.array([])
        ope = np.concatenate(a.operr) if a.operr else np.array([])
        results.append(
            HorizonMetrics(
                horizon_s=h,
                n_samples=a.n_samples,
                n_cells=int(e.size),
                mae=float(np.mean(np.abs(e))),
                rmse=rmse,
                persist_mae=float(np.mean(np.abs(pe))),
                persist_rmse=prmse,
                skill=(1.0 - rmse / prmse) if prmse > 1e-12 else None,
                outside_n_cells=int(oe.size),
                outside_mae=float(np.mean(np.abs(oe))) if oe.size else None,
                outside_persist_mae=float(np.mean(np.abs(ope))) if ope.size else None,
                count_rel_err=float(np.mean(a.crel)),
                persist_count_rel_err=float(np.mean(a.pcrel)),
            )
        )
    return results


def format_table(rows: Sequence[HorizonMetrics]) -> str:
    def f(v: Optional[float], d: int = 3) -> str:
        return "-" if v is None else "{:.{}f}".format(v, d)

    head = "horizon  표본  셀수 | RMSE(모델/정지) 스킬 | MAE(모델/정지) | 화각밖→안 MAE(모델/정지) [셀] | 인원 상대오차(모델/정지)"
    lines = [head, "-" * len(head)]
    for r in rows:
        lines.append(
            "{:>5.0f}s {:>5d} {:>5d} | {:>6s}/{:<6s} {:>6s} | {:>6s}/{:<6s} | {:>6s}/{:<6s} [{}] | {:>5.1%}/{:<5.1%}".format(
                r.horizon_s, r.n_samples, r.n_cells,
                f(r.rmse), f(r.persist_rmse), f(r.skill, 2),
                f(r.mae), f(r.persist_mae),
                f(r.outside_mae), f(r.outside_persist_mae), r.outside_n_cells,
                r.count_rel_err, r.persist_count_rel_err,
            )
        )
    return "\n".join(lines)


def main(argv: Optional[Sequence[str]] = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--input", required=True, help="관측 프레임이 여러 개인 timeline.json")
    ap.add_argument("--config", default=None, help="설정 YAML (기본: src/predict/config.yaml)")
    ap.add_argument("--horizons", type=float, nargs="+", default=None, help="평가할 horizon(초). 기본: 설정의 horizons_s")
    ap.add_argument("--tol", type=float, default=None, help="정답 프레임 매칭 허용 오차(초). 기본: 최소 프레임 간격의 절반")
    ap.add_argument("--output", default=None, help="지표 JSON 저장 경로 (data/raw/ 는 불가)")
    args = ap.parse_args(argv)

    cfg = load_config(args.config)
    horizons = args.horizons if args.horizons else cfg.horizons_s
    rows = evaluate(load_timeline(args.input), cfg, horizons, args.tol)
    if not rows:
        print("평가할 수 있는 horizon 이 없다: 프레임 간격/개수를 확인하세요 (요청 horizon={}).".format(list(horizons)))
        return
    print(format_table(rows))
    if args.output:
        assert_not_raw(args.output)
        with open(args.output, "w", encoding="utf-8") as fp:
            json.dump({"config": asdict(cfg), "horizons": [asdict(r) for r in rows]}, fp, ensure_ascii=False, indent=2)
        print("저장 완료: {}".format(args.output))


if __name__ == "__main__":
    main()
