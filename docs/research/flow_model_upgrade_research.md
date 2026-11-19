# 흐름 추정기 개선 조사 (정확도·속도)

| 항목 | 내용 |
|---|---|
| 작성일 | 2026-11-18 |
| 작성 | 조영준 (Researcher, Claude 보조) |
| 목적 | 발표(11-20, 11-26) 전에 흐름 추정을 더 정확하고 빠르게 할 수 있는지 사실로 확인한다 |
| 기준 | `main` `24537bb` + 로컬 계획 커밋 `558a47d` (`fix/flow-sparse-cell-noise`) |
| 측정 | 읽기 전용 CPU 벤치마크, `data/raw/aihub_71850/halloween_fri/E05_035.mp4` (1920×1080, 30 fps, 1847프레임). 스크립트는 부록 A·B |
| 계획 | `docs/plans/flow_model_upgrade_plan.md` |

## 0. 요약
1. **추정기를 바꾸는 것보다 프레임 간격(`gap_frames`)을 늘리는 것이 정확도에 더 크게 듣는다.** 지금은 연속 프레임(Δt = 1/30초)을 쓴다. 정지 배경 잡음은 쌍마다 약 0.2 px로 거의 일정해서, 간격을 6프레임으로 늘리면 프레임당 잡음이 약 1/4로 준다(Farneback 1080p: 신호/잡음 6.6 → 22.3). 시간은 그대로다.
2. 설계 문서는 원래 Δt = 0.2초(6프레임)였다(`docs/proposal-detail.md:297`). 구현은 `gap_frames=1` 기본값을 쓴다(`src/flow/run_flow.py:64`, `src/counting/analyze.py:56` 호출에 인자 없음).
3. **Farneback 반해상도(960×540)는 1쌍 0.98초 → 0.26초(3.8배 빠름)**다. 같은 간격에서는 원본보다 잡음이 2배지만, 간격 6과 함께 쓰면 지금(원본·간격 1)보다 신호/잡음이 2.0배 좋다(6.6 → 13.0).
4. DIS MEDIUM은 4배 빠르고 사진 오차는 조금 낮지만 정지 배경 잡음이 Farneback의 4배다. DIS FAST·ULTRAFAST는 더 빠르지만 잡음이 크다. torchvision RAFT small은 CPU에서 3.3초/쌍이고 프록시 지표도 가장 나빴다.
5. 흐름 단계는 전체 분석 시간의 3~17%다. 인원 추정이 83~97%다. 흐름을 4배 빠르게 해도 E04_039 전체 629초 중 약 80초만 준다.

## 1. 현재 구현 (코드로 확인)
- 추정기: `src/flow/estimators.py:28~45` `FarnebackEstimator`. `cv2.calcOpticalFlowFarneback(prev, next, None, 0.5, 3, 15, 3, 5, 1.2, 0)` (pyr_scale 0.5, levels 3, winsize 15, iterations 3, poly_n 5, poly_sigma 1.2), 원본 해상도 회색조. `name = "farneback-cv2"`.
- 같은 파일에 `DisEstimator`(`:48~65`, 기본 MEDIUM, `name = "dis-cv2-preset{n}"`)와 `RaftEstimator`(`:68~137`, torchvision, 작업 해상도 544×960, 원본 px로 되돌림)가 **이미 `main`에 있다.** `feat/flow-finetune`의 어댑터 커밋 `f304050`이 `main`에 병합되어 있고, `git diff origin/main...feat/flow-finetune --stat`은 비어 있다. 다시 가져올 코드는 없다.
- 흐름 단계: `src/flow/run_flow.py:55~70` `analyze_video(..., estimator, *, heads, h_head, cell_origin_m, gap_frames=1, noise_var=None, window_s=30.0, min_heads=1, patch_radius_px=6, inflow_min_heads=0)`.
  - 1초마다 `round(t·fps)` 프레임과 그 뒤 `gap_frames` 프레임 한 쌍을 잰다(`:203~219`). dt = `gap_frames / fps`(`:221`).
  - `gap_frames`는 1 이상 `floor(fps)` 미만 정수다(`:106~107`, `:140~144`).
  - 흐름장은 `sample_head_flow(flow, pts, patch_radius_px)`(`src/flow/ground.py:44~84`)로 머리마다 반경 6 px 패치 중앙값만 읽고 바로 버린다(`run_flow.py:217~219`).
  - `meta.models.flow = f"{estimator.name} head-r{patch_radius_px}"`(`:154~156`). 테스트 `tests/flow/test_run_flow.py:281`이 `"farneback-cv2 head-r6"`를 단언한다. 이 문자열을 해석하는 코드는 없다(`fix_flow_sparse_cell_noise_plan.md` 0.1절).
- 통합 스크립트: `src/counting/analyze.py:25` `from src.flow.estimators import FarnebackEstimator`, `:56~58` `analyze_video(Path(args.video), out, out, FarnebackEstimator(), heads=heads, h_head=..., cell_origin_m=...)`. `gap_frames`·`min_heads`를 넘기지 않는다. 이유노 님 파일이다.
- 머리 점은 메모리로만 넘기고 저장하지 않는다(`analyze.py:9`, `:59`, `CLAUDE.md`). 그래서 **흐름만 다시 돌리려 해도 인원 추정(P2PNet)부터 다시 돌려야 한다.** 이 PC에는 P2PNet 가중치가 없다.
- 기존 테스트: `tests/flow/test_estimators.py`는 합성 질감을 (+3, −2) px 옮겨 Farneback·DIS 내부 중앙값이 0.5 px 안인지 본다(`:56~77`). RAFT는 1.0 px(`:80~`).

## 2. 분석 시간 (기존 기록, `outputs/e8/*_analysis_time.json`)

| 영상 | 길이 | 인원 추정 | 흐름 | 전체 | 흐름 비중 | 흐름 1쌍당 |
|---|---|---|---|---|---|---|
| E04_039 | 180초 | 522.0초 | 106.8초 | 629.0초 | 17% | 0.59초 |
| E05_035 | 61초 | 1120.1초 | 34.2초 | 1154.5초 | 3% | 0.56초 |
| E05_038 | 60초 | 1058.8초 | 33.8초 | 1092.7초 | 3% | 0.56초 |

- CPU: "Intel64 Family 6 Model 94 Stepping 3" (6세대 i 계열). 장치 cpu.
- 흐름 단계 1쌍당 0.56~0.59초는 이번 벤치마크의 Farneback 원본 0.98초/쌍보다 짧다. 원인은 (확인 필요)다. 분석 당시 해상도·스레드 상태가 달랐을 수 있다. 아래 비교는 **같은 프로세스 안의 상대 비율**로 읽는다.
- 디코딩 하한: E05_035 1847프레임을 `grab()`으로 넘기고 초당 2장만 `retrieve()`하면 3.8초(부록 A). 흐름 단계 34.2초 중 디코딩은 약 4초다.

## 3. 후보 (문헌·설치 상태)

| 후보 | 공개 정확도 | CPU 시간 (공개) | 설치 | 라이선스 | 비고 |
|---|---|---|---|---|---|
| Farneback (현재) | 공식 EPE 없음 | 공개 수치 없음 | 불필요 | OpenCV Apache-2.0 | `pretrained_models_research.md:43` |
| OpenCV DIS | TUB CrowdFlow 고전 방법 중 DIS4 평균 EPE 0.784로 가장 정확 [21] | 1280×720 DIS4 1.70초, DIS2 0.28초 (i9-7980XE) [21] | 불필요 | OpenCV Apache-2.0 | `pretrained_models_research.md:72, 112`. 프리셋과 DIS4·DIS2 대응은 (확인 필요) |
| torchvision RAFT small | Sintel train final EPE 3.279 (`C_T_V2`) [M2] | 공개 CPU 수치 없음 | 설치됨 (torchvision 0.29.1, `requirements.txt:8`). 가중치 `raft_small_C_T_V2-01064c6d.pth` 캐시 있음 | BSD-3 | `pretrained_models_research.md:74` |
| torchvision RAFT large | Sintel train final EPE 2.716 [M2] | 공개 CPU 수치 없음 | 가중치 내려받기 필요 (캐시 없음) | BSD-3 | 이번 측정 제외 |
| SEA-RAFT | Sintel·KITTI 상위 (`pretrained_models_research.md` 1절) | 공개 CPU 수치 없음 | pip 패키지 없음. 저장소 복제 + 가중치 내려받기 | 코드 BSD-3 | 동결 전 범위 밖 |
| OpenCV contrib (`cv2.optflow`: DeepFlow, PCAFlow, DualTVL1 등) | — | — | `cv2.optflow` 없음 (`opencv-python` 5.0.0, contrib 아님) | Apache-2.0 | 쓰려면 `opencv-contrib-python`으로 바꿔야 한다. 측정 제외 |

- 환경(이번 측정): `crowdsight` conda 환경, Python `C:\Users\Woori\anaconda3\envs\crowdsight\python.exe`, numpy 2.4.6, opencv 5.0.0 (스레드 8), torch 2.14.1+cpu (스레드 4), torchvision 있음.

## 4. 벤치마크 방법
- 쌍: E05_035의 t = 0, 6, …, 54초(10개). 시작 프레임 `round(t·30)`과 그 뒤 `gap` 프레임. 파이프라인과 같다.
- 시간: 회색조 변환·축소·확대를 포함한 `estimate` 1회의 중앙값(첫 쌍 예열 뒤). 역방향 흐름과 지표 계산은 시간에 넣지 않았다.
- 반해상도: `cv2.resize(..., fx=0.5, INTER_AREA)`로 줄여 흐름을 구하고, 원본 크기로 선형 확대한 뒤 값을 2배 한다(원본 px 단위).
- 마스크 (`infra/homography/E05_035.json` `walkable_polygon_px`):
  - 걷는 곳 = 다각형 안.
  - 정지 배경 = 다각형 **밖**이고, 두 프레임 절대 차를 σ 3 가우시안으로 흐린 값이 1 미만인 화소(평균 103.7만 화소). 실제 움직임이 없다고 보는 곳이다.
  - 움직인 곳 = 다각형 안이고 흐린 절대 차가 4 이상인 화소(평균 17.2만 화소). 사람이 움직인 곳이다.
- 지표 (정답 흐름이 없으므로 모두 프록시):
  - (a) 정지 배경 |흐름| 중앙값·p95 [px]: 낮을수록 잡음이 작다. 셀 속도 분산과 압력의 잡음 바닥에 바로 들어간다.
  - (b) 사진 오차: 다음 프레임을 흐름으로 당겨(`cv2.remap`) 이전 프레임과의 평균 절대 회색조 차. 걷는 곳·움직인 곳 각각. 낮을수록 좋다. 흐름 0일 때 값을 참고로 둔다. **주의**: Farneback·DIS는 밝기 보존을 직접 최소화하므로 이 지표가 고전 방법에 유리하다.
  - (c) 전후 일관성: 정방향 흐름 f와 역방향 흐름 b로 |f(x) + b(x + f(x))|. 움직인 곳의 중앙값과 1 px 넘는 비율.
  - 간격 비교(부록 B): 프레임당 값(|흐름| / gap)으로 바꿔 움직인 곳 신호 중앙값, 정지 배경 p95, 신호/잡음 = 신호 / 정지 p95, 사진 오차 / 흐름 0 사진 오차.
- 머리 점이 없어 머리 패치 표본(`sample_head_flow`)은 재지 못했다. 움직인 곳 마스크가 머리·몸 화소의 대리다.

## 5. 결과

### 5.1 후보별 (간격 1, 부록 A)

| 후보 | 시간/쌍 (초) | 사진 오차 걷는 곳 | 사진 오차 움직인 곳 | 정지 \|흐름\| 중앙 (px) | 정지 p95 (px) | 전후 불일치 중앙 (px) | 전후 불일치 > 1 px |
|---|---|---|---|---|---|---|---|
| 흐름 0 (참고) | 0 | 4.12 | 14.36 | 0 | 0 | — | — |
| **Farneback 원본 (현재)** | 0.981 | 2.50 | 6.66 | **0.003** | **0.181** | **0.032** | 0.020 |
| Farneback 반해상도 | 0.271 | 2.85 | 7.76 | 0.043 | 0.367 | 0.030 | 0.007 |
| Farneback 반해상도 levels 4·winsize 11 | 0.274 | 2.71 | 7.31 | 0.042 | 0.407 | 0.048 | 0.013 |
| DIS ULTRAFAST 원본 | 0.031 | 2.80 | 7.74 | 0.138 | 0.770 | 0.165 | 0.047 |
| DIS FAST 원본 | 0.059 | 2.86 | 8.12 | 0.069 | 0.415 | 0.103 | 0.016 |
| DIS MEDIUM 원본 | 0.242 | **2.40** | **6.50** | 0.085 | 0.720 | 0.103 | 0.040 |
| DIS FAST 반해상도 | 0.036 | 3.42 | 9.89 | 0.058 | 0.255 | 0.111 | 0.004 |
| DIS MEDIUM 반해상도 | 0.070 | 2.87 | 8.13 | 0.071 | 0.407 | 0.101 | 0.014 |
| RAFT small 544×960, 반복 12 | 3.284 | 3.87 | 11.83 | 0.148 | 0.402 | 0.194 | 0.043 |
| RAFT small 544×960, 반복 6 | 2.275 | 3.99 | 11.77 | 0.175 | 0.485 | 0.284 | 0.060 |

- 간격 1에서는 **현재 Farneback 원본이 잡음(a)·전후 일관성(c)에서 가장 좋다.** 사진 오차(b)는 DIS MEDIUM 원본이 조금 낮다(6.50 vs 6.66, 2%).
- RAFT small은 CPU에서 3.3초/쌍(현재의 3.3배 느림)이고, 움직인 곳 사진 오차 11.8이 흐름 0(14.4)에 가깝다. 30 fps 연속 프레임의 1 px 안팎 움직임을 544×960 축소에서 잘 못 잡는 것으로 보인다(해석, 가정). 지금 조건에서는 후보가 아니다.

### 5.2 간격별 (부록 B, 프레임당 단위)

| 후보 | gap | 시간/쌍 (초) | 움직인 곳 신호 중앙 (px/프레임) | 정지 p95 (px/프레임) | 신호/잡음 | 사진 오차 / 흐름 0 |
|---|---|---|---|---|---|---|
| **Farneback 원본 (현재)** | **1** | 0.991 | 1.190 | 0.181 | **6.6** | 0.50 |
| Farneback 원본 | 2 | 0.998 | 1.108 | 0.099 | 11.2 | 0.45 |
| Farneback 원본 | 3 | 0.963 | 1.030 | 0.071 | 14.5 | 0.44 |
| Farneback 원본 | 6 | 1.143 | 0.946 | 0.043 | 22.3 | 0.48 |
| Farneback 반해상도 | 1 | 0.256 | 1.162 | 0.367 | 3.2 | 0.58 |
| Farneback 반해상도 | 2 | 0.253 | 1.085 | 0.195 | 5.6 | 0.53 |
| Farneback 반해상도 | 3 | 0.258 | 1.016 | 0.135 | 7.5 | 0.52 |
| **Farneback 반해상도** | **6** | **0.289** | 0.983 | 0.075 | **13.0** | 0.56 |
| DIS MEDIUM 원본 | 1 | 0.223 | 1.112 | 0.720 | 1.5 | 0.49 |
| DIS MEDIUM 원본 | 2 | 0.234 | 1.065 | 0.417 | 2.6 | 0.42 |
| DIS MEDIUM 원본 | 3 | 0.226 | 1.024 | 0.285 | 3.6 | 0.40 |
| DIS MEDIUM 원본 | 6 | 0.259 | 1.003 | 0.163 | 6.1 | 0.41 |
| DIS FAST 원본 | 1 | 0.046 | 0.954 | 0.415 | 2.3 | 0.60 |
| DIS FAST 원본 | 2 | 0.047 | 0.912 | 0.235 | 3.9 | 0.55 |
| DIS FAST 원본 | 3 | 0.048 | 0.900 | 0.170 | 5.3 | 0.53 |

- 정지 배경 잡음은 **쌍당 px로 거의 일정**하다(Farneback 원본 0.18·0.20·0.21·0.26 px). 그래서 프레임당 잡음(= 속도 잡음)은 대략 1/gap로 준다.
- 움직인 곳 신호는 gap이 커질수록 조금 준다(1.19 → 0.95 px/프레임). 원인은 둘 중 하나다: (가) gap 1의 잡음이 크기를 부풀린다, (나) gap이 크면 큰 이동·가림으로 과소 추정한다. 이 측정만으로는 가를 수 없다 (확인 필요). 마스크를 gap 1 차이로 정했으므로 gap이 크면 사람이 마스크 밖으로 나간 부분도 있다.
- 사진 오차 비율은 gap 2~6에서 gap 1과 같거나 낮다. 큰 간격에서 흐름이 무너지는 징후는 보이지 않는다.
- 시간은 gap과 거의 무관하다.

### 5.3 m/s로 환산 (대략)
- E05_035 머리 평면 행렬(`head_plane.H_head_img_to_ground`)로 x = 930 px에서 1 px당 지면 거리를 재면: y = 1000에서 가로 0.0067·세로 0.0079 m, y = 600에서 0.0095·0.0157 m, y = 200에서 0.0161·0.0451 m다. 대표값을 0.015 m/px로 본다(가정).
- 정지 p95 0.181 px/프레임 × 30 fps × 0.015 m/px ≈ **0.08 m/s** (현재, 화면 위쪽 세로 방향은 약 0.25 m/s). Farneback 반해상도 gap 6은 0.075 × 30 × 0.015 ≈ **0.03 m/s**. 머리 패치 중앙값(169화소)과 셀 평균이 이를 더 줄인다.
- 셀 압력 기준 0.02 m²/s²는 ρ = 1에서 속도 표준편차 약 0.14 m/s다. 먼 쪽(화면 위) 셀에서는 현재 잡음이 이 크기에 닿을 수 있다(해석, 가정). 저밀도 오경보(`fix_flow_sparse_cell_noise_plan.md` 0.3절)의 주원인은 그 문서대로 머리 수 부족이고, 간격을 늘리는 것은 보조 효과다.

## 6. 해석
- 추정기를 DIS·RAFT로 바꾸는 것은 근거가 약하다. 빠른 DIS는 잡음이 크고, RAFT는 CPU에서 느리고 이 조건에서 지표도 나쁘다.
- **가장 싸고 확실한 정확도 개선은 `gap_frames`를 늘리는 것**이다. 코드는 이미 있고(`run_flow.py:64`, 테스트 `test_gap_two_frames_divides_by_gap_over_fps`), 설계값(0.2초)과도 맞는다.
- **속도 개선은 반해상도 Farneback**이다. 원본 대비 3.4~3.8배 빠르다. 같은 gap에서는 잡음이 2배지만 gap 6과 묶으면 지금보다 잡음이 절반 이하다.
- 흐름 단계를 빠르게 해도 전체 분석은 인원 추정이 지배한다. 발표에서 "빠르게"는 흐름 단계 시간으로 말해야 정확하다.
- 한계: 영상 1개(E05_035), 10쌍, 프록시 지표만이다. 머리 패치·셀 단위 결과(속도 이상치, 압력 분포)는 재분석 뒤에야 볼 수 있다. E04_039·E05_038 영상은 이 PC에 없다.

## 7. 확인 필요
- `outputs/e8` 흐름 1쌍 0.56초와 이번 0.98초의 차이 원인.
- gap이 클 때 신호가 줄어드는 원인(5.2절 (가)/(나)). 걷는 사람 실측 속도(1.2~1.4 m/s)와 셀 평균 속력 분포를 재분석 뒤 비교하면 가를 수 있다.
- 밀집 장면(E04_039, ρ 3 이상)에서 gap 6의 가림 영향. E04_039 영상이 있어야 잰다.
- DIS 프리셋과 TUB CrowdFlow DIS4·DIS2의 대응(`pretrained_models_research.md:220`).

## 부록 A. 후보별 벤치마크 (`%TEMP%/flowbench/bench_flow.py`)
실행: `C:\Users\Woori\anaconda3\envs\crowdsight\python.exe %TEMP%\flowbench\bench_flow.py <저장소 경로>` (약 6분)

```python
"""읽기 전용 흐름 추정기 벤치마크 (E05_035, 머리 점 없이 프록시 지표)."""
import json, sys, time
import cv2, numpy as np, torch

ROOT = sys.argv[1]
VIDEO = f"{ROOT}/data/raw/aihub_71850/halloween_fri/E05_035.mp4"
CFG = json.load(open(f"{ROOT}/infra/homography/E05_035.json", encoding="utf-8"))
sys.path.insert(0, ROOT)
from src.flow.estimators import RaftEstimator  # noqa: E402

TS = list(range(0, 60, 6))  # 10쌍, 파이프라인과 같은 (round(t*fps), +1) 쌍
GAP = 1
np.random.seed(0); torch.manual_seed(0)

def gray(b): return cv2.cvtColor(b, cv2.COLOR_BGR2GRAY)

def fb(scale, levels=3, win=15, iters=3, poly_n=5, sigma=1.2):
    def f(a, b):
        ga, gb = gray(a), gray(b)
        if scale != 1:
            ga = cv2.resize(ga, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
            gb = cv2.resize(gb, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
        fl = cv2.calcOpticalFlowFarneback(ga, gb, None, 0.5, levels, win, iters, poly_n, sigma, 0)
        return up(fl, a.shape, scale)
    return f

def dis(preset, scale):
    d = cv2.DISOpticalFlow_create(preset)
    def f(a, b):
        ga, gb = gray(a), gray(b)
        if scale != 1:
            ga = cv2.resize(ga, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
            gb = cv2.resize(gb, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
        return up(d.calc(ga, gb, None), a.shape, scale)
    return f

def up(fl, shape, scale):
    if scale == 1: return fl.astype(np.float32)
    h, w = shape[:2]
    fl = cv2.resize(fl, (w, h), interpolation=cv2.INTER_LINEAR) / scale
    return fl.astype(np.float32)

def raft(size, hw, it):
    r = RaftEstimator(size=size, device="cpu", work_hw=hw, num_flow_updates=it)
    return r.estimate

CANDS = {
    "FB full (현재)": fb(1.0),
    "FB half": fb(0.5),
    "FB half L4 w11": fb(0.5, levels=4, win=11),
    "DIS ULTRAFAST full": dis(cv2.DISOPTICAL_FLOW_PRESET_ULTRAFAST, 1.0),
    "DIS FAST full": dis(cv2.DISOPTICAL_FLOW_PRESET_FAST, 1.0),
    "DIS MEDIUM full": dis(cv2.DISOPTICAL_FLOW_PRESET_MEDIUM, 1.0),
    "DIS FAST half": dis(cv2.DISOPTICAL_FLOW_PRESET_FAST, 0.5),
    "DIS MEDIUM half": dis(cv2.DISOPTICAL_FLOW_PRESET_MEDIUM, 0.5),
    "RAFT small 544x960 it12": raft("small", (544, 960), 12),
    "RAFT small 544x960 it6": raft("small", (544, 960), 6),
}

# 프레임 쌍 읽기
cap = cv2.VideoCapture(VIDEO); fps = cap.get(cv2.CAP_PROP_FPS)
pairs = []
for t in TS:
    n = int(round(t * fps)); cap.set(cv2.CAP_PROP_POS_FRAMES, n)
    ok1, a = cap.read(); ok2, b = cap.read()
    assert ok1 and ok2; pairs.append((a, b))
cap.release()
H, W = pairs[0][0].shape[:2]
walk = np.zeros((H, W), np.uint8)
cv2.fillPoly(walk, [np.array(CFG["walkable_polygon_px"], np.int32)], 1)
walk = walk.astype(bool)
yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)

def warp(img, fl):  # next를 흐름으로 당겨 prev 자리로
    return cv2.remap(img, xx + fl[..., 0], yy + fl[..., 1], cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)

masks = []
for a, b in pairs:
    ga, gb = gray(a).astype(np.float32), gray(b).astype(np.float32)
    d = cv2.GaussianBlur(np.abs(ga - gb), (0, 0), 3)
    static = (~walk) & (d < 1.0)       # 걷는 곳 밖 + 거의 안 바뀐 화소
    moving = walk & (d >= 4.0)          # 걷는 곳 안 + 바뀐 화소 (사람이 움직인 곳)
    masks.append((static, moving))

def zero_err(): # 흐름 0일 때 사진 오차 (참고)
    out = []
    for (a, b), (_, mv) in zip(pairs, masks):
        e = np.abs(gray(a).astype(np.float32) - gray(b).astype(np.float32))
        out.append((e[walk].mean(), e[mv].mean()))
    return np.mean(out, axis=0)

rows = []
z = zero_err()
rows.append(dict(name="흐름 0 (참고)", t=0, photo_walk=z[0], photo_move=z[1], static_med=0, static_p95=0, fb_med=float("nan"), fb_bad=float("nan")))
for name, f in CANDS.items():
    f(*pairs[0])  # 예열
    ts, pw, pm, sm, sp, fm, fbad = [], [], [], [], [], [], []
    for (a, b), (st, mv) in zip(pairs, masks):
        t0 = time.perf_counter(); fl = f(a, b); ts.append(time.perf_counter() - t0)
        bw = f(b, a)
        ga, gb = gray(a).astype(np.float32), gray(b).astype(np.float32)
        e = np.abs(warp(gb, fl) - ga)
        pw.append(e[walk].mean()); pm.append(e[mv].mean())
        mag = np.linalg.norm(fl, axis=2)
        sm.append(np.median(mag[st])); sp.append(np.percentile(mag[st], 95))
        bwx = cv2.remap(bw, xx + fl[..., 0], yy + fl[..., 1], cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
        c = np.linalg.norm(fl + bwx, axis=2)
        fm.append(np.median(c[mv])); fbad.append((c[mv] > 1.0).mean())
    rows.append(dict(name=name, t=np.median(ts), photo_walk=np.mean(pw), photo_move=np.mean(pm),
                     static_med=np.mean(sm), static_p95=np.mean(sp), fb_med=np.mean(fm), fb_bad=np.mean(fbad)))
    print(name, f"{rows[-1]['t']:.3f}s", flush=True)

# 디코딩 하한: 영상 전체 grab + 쓰는 프레임 retrieve (파이프라인과 같은 방식)
cap = cv2.VideoCapture(VIDEO); t0 = time.perf_counter(); n = 0
while cap.grab():
    if n % 30 in (0, 1): cap.retrieve()
    n += 1
dec = time.perf_counter() - t0; cap.release()

print(f"\ncv2 {cv2.__version__} threads {cv2.getNumThreads()}, torch {torch.__version__} threads {torch.get_num_threads()}")
print(f"masks: static px mean {np.mean([s.sum() for s,_ in masks]):.0f}, moving px mean {np.mean([m.sum() for _,m in masks]):.0f}")
print(f"decode {n} frames (grab all, retrieve 2/s): {dec:.1f}s")
# (표 출력 생략: 5.1절 표와 같은 열)
```

출력 원문(요약): `cv2 5.0.0 threads 8, torch 2.14.1+cpu threads 4` / `masks: static px mean 1037442, moving px mean 172497` / `decode 1847 frames (grab all, retrieve 2/s): 3.8s`.

## 부록 B. 간격별 벤치마크 (`%TEMP%/flowbench/bench_gap.py`)
실행: `... bench_gap.py <저장소 경로>` (gap 1·2·3, 약 3분). gap 6은 같은 스크립트에서 프레임을 7장 읽고 `GAPS = (6,)`, 후보를 Farneback 원본·반해상도·DIS MEDIUM으로 줄여 돌렸다(`bench_gap6.py`).

```python
"""gap_frames(1·2·3)별 신호 대 잡음 비교. 읽기 전용."""
import json, sys, time
import cv2, numpy as np
ROOT = sys.argv[1]
VIDEO = f"{ROOT}/data/raw/aihub_71850/halloween_fri/E05_035.mp4"
CFG = json.load(open(f"{ROOT}/infra/homography/E05_035.json", encoding="utf-8"))
TS = list(range(0, 60, 6))
def gray(b): return cv2.cvtColor(b, cv2.COLOR_BGR2GRAY)
def sc(g, s): return g if s == 1 else cv2.resize(g, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
def up(fl, shape, s):
    if s == 1: return fl
    return cv2.resize(fl, (shape[1], shape[0]), interpolation=cv2.INTER_LINEAR) / s
def fb(s):
    return lambda a, b: up(cv2.calcOpticalFlowFarneback(sc(a, s), sc(b, s), None, 0.5, 3, 15, 3, 5, 1.2, 0), a.shape, s)
def dis(p, s):
    d = cv2.DISOpticalFlow_create(p)
    return lambda a, b: up(d.calc(sc(a, s), sc(b, s), None), a.shape, s)
C = {"FB full": fb(1), "FB half": fb(0.5), "DIS MEDIUM full": dis(cv2.DISOPTICAL_FLOW_PRESET_MEDIUM, 1),
     "DIS FAST full": dis(cv2.DISOPTICAL_FLOW_PRESET_FAST, 1)}
cap = cv2.VideoCapture(VIDEO); fps = cap.get(5); fr = []
for t in TS:
    cap.set(cv2.CAP_PROP_POS_FRAMES, int(round(t * fps)))
    fr.append([gray(cap.read()[1]) for _ in range(4)])
cap.release()
H, W = fr[0][0].shape
walk = np.zeros((H, W), np.uint8); cv2.fillPoly(walk, [np.array(CFG["walkable_polygon_px"], np.int32)], 1); walk = walk.astype(bool)
yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
for name, f in C.items():
    f(fr[0][0], fr[0][1])
    for gap in (1, 2, 3):
        tt, sig, noi, rel = [], [], [], []
        for g in fr:
            a, b = g[0], g[gap]
            d = cv2.GaussianBlur(np.abs(a.astype(np.float32) - g[1].astype(np.float32)), (0, 0), 3)
            st = (~walk) & (d < 1.0); mv = walk & (d >= 4.0)  # 마스크는 gap 1 기준으로 고정
            t0 = time.perf_counter(); fl = f(a, b); tt.append(time.perf_counter() - t0)
            m = np.linalg.norm(fl, axis=2) / gap
            sig.append(np.median(m[mv])); noi.append(np.percentile(m[st], 95))
            wb = cv2.remap(b, xx + fl[..., 0], yy + fl[..., 1], cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE).astype(np.float32)
            e = np.abs(wb - a.astype(np.float32))[mv].mean(); e0 = np.abs(b.astype(np.float32) - a.astype(np.float32))[mv].mean()
            rel.append(e / e0)
        print(f"| {name} | {gap} | {np.median(tt):.3f} | {np.mean(sig):.3f} | {np.mean(noi):.3f} | {np.mean(sig)/np.mean(noi):.1f} | {np.mean(rel):.2f} |", flush=True)
```

## 변경 이력
| 날짜 | 내용 |
|---|---|
| 2026-11-18 | 첫 작성. 후보 10개 간격 1 벤치마크, 간격 1·2·3·6 비교 |
