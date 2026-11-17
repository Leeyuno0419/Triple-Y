"""머신러닝 60초 예측의 공통 부품: 피처 계산, 학습 표본 만들기, 모델 저장·불러오기.

학습(train_forecast.py)과 실시간 예측(model.MLPredictor)이 같은 피처 함수를 쓴다.
둘이 어긋나면 학습 때와 다른 입력이 모델에 들어가 결과가 조용히 틀어지므로 피처 계산은 이 파일 한 곳에만 둔다.

예측 방식 (한 셀의 이야기)
    1. 최근 history_s 초(기본 30초)의 밀도 기록을 본다.
    2. 거기서 "지금 밀도, 최근 몇 초 전과의 차이, 오르는/내리는 속도(추세), 평균, 흔들림"을 뽑는다. (피처)
    3. 모델은 "60초 뒤 밀도 − 지금 밀도" 의 변화량만 맞힌다. 모델이 헛짚어도 '현재값 유지'에서 크게 벗어나지 않는다.
    4. 예측 = 지금 밀도 + 변화량 (0 미만이면 0). 모든 셀이 같은 모델 하나를 같이 쓴다.

주의: 저장 파일(.joblib)은 pickle 이라 신뢰할 수 없는 파일을 열면 코드가 실행될 수 있다. 우리가 직접 학습한 파일만 쓴다.
"""
from __future__ import annotations

import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple, Union

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view

REPO_ROOT = Path(__file__).resolve().parents[2]
PathLike = Union[str, Path]

DEFAULT_N_LAGS = 10   # 최근 몇 초의 값을 직접 입력으로 쓸지 (사용자 요청: 최근 5~10개)


# --------------------------------------------------------------------------- #
# 피처
# --------------------------------------------------------------------------- #
def feature_names(n_lags: int) -> List[str]:
    """피처 이름 목록. compute_features 의 열 순서와 같다."""
    if n_lags < 2:
        raise ValueError("n_lags 는 2 이상이어야 한다")
    return (
        ["cur"]                                              # 지금 밀도
        + ["diff_{}s".format(k) for k in range(1, n_lags)]   # 지금 − k초 전 (양수면 최근에 올랐다)
        + ["slope_short", "slope_full", "mean_minus_cur", "std_full"]
    )


def _ols_slope(w: np.ndarray) -> np.ndarray:
    """마지막 축(시간)을 따라 최소제곱 직선의 기울기를 구한다. 단위: 밀도/초."""
    steps = w.shape[-1]
    x = np.arange(steps, dtype=float)
    xc = x - x.mean()
    return (w * xc).sum(axis=-1) / float((xc ** 2).sum())


def compute_features(windows: np.ndarray, n_lags: int) -> np.ndarray:
    """밀도 기록 창에서 피처를 만든다.

    windows: (..., T) 마지막 축이 시간(오래된 → 최근), T >= n_lags. 앞쪽 축은 자유(셀, 시각 등).
    반환값 : (..., F) F = n_lags + 4
    """
    w = np.asarray(windows, dtype=float)
    if w.shape[-1] < n_lags:
        raise ValueError("입력 기록이 n_lags({})보다 짧다: {}".format(n_lags, w.shape[-1]))
    cur = w[..., -1]
    recent = w[..., -n_lags:-1][..., ::-1]               # 1초 전, 2초 전, ... (n_lags-1 개)
    diffs = cur[..., None] - recent
    slope_short = _ols_slope(w[..., -n_lags:])           # 최근 n_lags 초의 오르내림 속도
    slope_full = _ols_slope(w)                           # 창 전체(예: 30초)의 오르내림 속도
    mean_minus_cur = w.mean(axis=-1) - cur
    std_full = w.std(axis=-1)
    extra = np.stack([slope_short, slope_full, mean_minus_cur, std_full], axis=-1)
    return np.concatenate([cur[..., None], diffs, extra], axis=-1)


# --------------------------------------------------------------------------- #
# 학습 표본
# --------------------------------------------------------------------------- #
def n_samples(total_steps: int, history_s: int, horizon_s: int) -> int:
    """길이 total_steps 초 기록에서 만들 수 있는 시작 시각 t 의 개수. 모자라면 0."""
    return max(0, total_steps - history_s - horizon_s + 1)


def build_windows(
    density: np.ndarray, history_s: int, horizon_s: int, stride: int = 1
) -> Tuple[np.ndarray, np.ndarray]:
    """밀도 (T, N) 기록에서 (입력 창, 60초 뒤 정답)을 모두 뽑는다.

    시각 t 의 입력은 density[t-history_s+1 .. t] 뿐이고 정답은 density[t+horizon_s] 다 (t 이후 값은 입력에 안 들어간다).
    반환값: windows (S, N, history_s), target (S, N). S 는 t 를 stride 간격으로 뽑은 개수.
    """
    d = np.asarray(density, dtype=float)
    count = n_samples(d.shape[0], history_s, horizon_s)
    if count == 0:
        raise ValueError("기록이 짧다: {}초 < history_s + horizon_s = {}초".format(d.shape[0], history_s + horizon_s))
    win = sliding_window_view(d, history_s, axis=0)[:count]          # (S, N, history_s), i 번째 창의 t = i + history_s - 1
    target = d[history_s - 1 + horizon_s:history_s - 1 + horizon_s + count]
    return win[::stride], target[::stride]


def make_xy(
    series: Sequence[np.ndarray], history_s: int, horizon_s: int, n_lags: int, stride: int = 1
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """여러 기록 (각각 (T_i, N_i))을 모아 (X, y, cur, lin) 로 만든다. 모든 셀·시각을 한 표로 합친다.

    X  : (M, F) 피처
    y  : (M,)   학습 정답 = 60초 뒤 밀도 − 지금 밀도 (변화량)
    cur: (M,)   지금 밀도 (예측값 = cur + 모델 출력 으로 되돌릴 때 쓴다. 정답 = cur + y)
    lin: (M,)   같은 창으로 계산한 '직선 추세' 예측 (비교용 기준선)
    """
    xs, ys, curs, lins = [], [], [], []
    for dens in series:
        win, target = build_windows(dens, history_s, horizon_s, stride)
        feats = compute_features(win, n_lags).reshape(-1, n_lags + 4)
        cur = win[..., -1].reshape(-1)
        xs.append(feats)
        ys.append(target.reshape(-1) - cur)
        curs.append(cur)
        lins.append(linear_baseline(win, horizon_s).reshape(-1))
    return np.concatenate(xs), np.concatenate(ys), np.concatenate(curs), np.concatenate(lins)


# --------------------------------------------------------------------------- #
# 기준선 (같은 창으로 계산해 모델과 공정하게 비교한다)
# --------------------------------------------------------------------------- #
def persistence_baseline(cur: np.ndarray) -> np.ndarray:
    """현재값 유지: 60초 뒤에도 지금과 같다."""
    return np.clip(cur, 0.0, None)


def linear_baseline(windows: np.ndarray, horizon_s: int) -> np.ndarray:
    """직선 추세: 창 전체에 최소제곱 직선을 맞춰 horizon_s 초 연장한다 (model.LinearTrendPredictor 와 같은 식)."""
    w = np.asarray(windows, dtype=float)
    steps = w.shape[-1]
    slope = _ols_slope(w)
    xm = (np.arange(steps, dtype=float) - (steps - 1)).mean()        # 현재 시각을 0 으로 둔 평균 위치
    at_now = w.mean(axis=-1) - slope * xm
    return np.clip(at_now + slope * horizon_s, 0.0, None)


# --------------------------------------------------------------------------- #
# 저장 · 불러오기
# --------------------------------------------------------------------------- #
@dataclass
class ForecastBundle:
    """학습된 모델과 그 모델을 쓰는 조건 (입력 기간·예측 시점·피처 수 등)."""

    model: Any                 # 학습된 sklearn 파이프라인 (표준화 + 회귀)
    meta: Dict[str, Any]       # history_s, horizon_s, n_lags, kind, trained_on, sklearn_version, 시험 점수 ...

    def predict(self, density_hist: np.ndarray) -> np.ndarray:
        """밀도 기록 (T, N) → 셀별 60초 뒤 밀도 (N,). 마지막 행이 현재 시각이다."""
        hist = np.asarray(density_hist, dtype=float)
        n_lags = int(self.meta["n_lags"])
        feats = compute_features(hist.T, n_lags)                     # (N, F): 셀마다 한 줄
        delta = self.model.predict(feats)                            # 모델은 '변화량'을 맞힌다
        return np.clip(hist[-1] + delta, 0.0, None)                  # 지금 + 변화량, 음수 인원은 없으니 0 으로


def save_bundle(bundle: ForecastBundle, path: PathLike) -> Path:
    """모델을 .joblib 로 저장한다 (폴더가 없으면 만든다). 가중치 파일은 git 에 올리지 않는다 (.gitignore)."""
    import joblib

    out = resolve_path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump({"model": bundle.model, "meta": bundle.meta}, out)
    return out


def load_bundle(path: PathLike) -> ForecastBundle:
    """저장된 모델을 불러온다. 파일이 없으면 학습 명령을 안내하는 FileNotFoundError 를 낸다."""
    import joblib
    import sklearn

    src = resolve_path(path)
    if not src.is_file():
        raise FileNotFoundError(
            "예측 모델 파일이 없다: {}\n먼저 학습한다: python -m src.predict.train_forecast".format(src))
    raw = joblib.load(src)
    bundle = ForecastBundle(model=raw["model"], meta=dict(raw["meta"]))
    saved = bundle.meta.get("sklearn_version")
    if saved and saved != sklearn.__version__:
        warnings.warn("모델은 scikit-learn {} 로 학습됐고 지금은 {} 다. 결과가 달라지면 다시 학습한다.".format(
            saved, sklearn.__version__))
    return bundle


def resolve_path(path: PathLike) -> Path:
    """상대 경로는 실행 위치가 아니라 저장소 루트 기준으로 해석한다 (어디서 실행해도 같은 파일을 쓰도록)."""
    p = Path(path)
    return p if p.is_absolute() else REPO_ROOT / p
