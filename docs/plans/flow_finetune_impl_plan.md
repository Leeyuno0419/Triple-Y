# 흐름 모델 추가 학습 구현 계획 (flow finetune implementation plan)

## 문서 상태

| 항목 | 내용 |
|---|---|
| 작성일 | 2026-11-09 |
| 작성자 | 조영준 (Claude 작성 보조) |
| 상태 | 초안. 팀 검토 전이다 |
| 대상 | 흐름·군중 불안정 모듈(`src/flow/`) |
| 상위 문서 | `docs/plans/flow_finetune_plan.md`(이하 기획) |
| 근거 문서 | `docs/research/crowd_turbulence_research.md`(이하 난류 조사), `docs/research/pretrained_models_research.md`(이하 모델 조사) |
| 기준 문서 | `docs/proposal.md` 3.4, `docs/proposal-detail.md` 3.4·7.2.3~7.2.6 |

- 이 문서는 기획을 코드로 옮기는 방법이다. 기획의 결정을 다시 정하지 않는다.
- 기획에서 `[토론]`인 항목은 여기서도 `[토론]`이다. 팀 합의 전에는 코드의 기본값일 뿐이다.
- 현재 `src/flow/`, `src/counting/`, `src/predict/`는 비어 있다. `requirements.txt`에도 패키지가 없다. 아래 모듈과 코드는 모두 새로 만드는 것이다.
- 표기: `(가정)`, `[토론]`, `(확인 필요)`는 `docs/proposal-guide.md` 3장을 따른다.

---

## 1. 개요

### 1.1 목표

- 사전학습 RAFT로 셀 통계 파이프라인을 끝까지 돌린다 (G0, 11-10).
- 같은 파이프라인에 비지도 추가 학습 RAFT를 끼워 넣고 사전학습 모델과 비교한다 (G1, 11-13).
- 비교 결과로 흐름 추정기를 하나 고르고 `timeline.json` 흐름 필드를 낸다.

### 1.2 범위

| 포함 | 내용 |
|---|---|
| 흐름 추정기 | Farneback, DIS(OpenCV), torchvision RAFT(사전학습·추가 학습)를 같은 인터페이스로 감싼다 |
| 셀 통계 | 셀 평균 지면 속도 `V_c`, 시간 분산 불안정 `S_c`, 압력 `P_c`, 역방향 비율 `B_c`, 신뢰도 `Q_c` |
| 지면 변환 | 호모그래피로 px/프레임 → m/s |
| 노이즈 바닥 | 정지 구간 셀별 `Var_noise_c` 측정 (중간 1) |
| 단순 기준선 | 현재값 유지, 셀 단위 흐름 외삽 (중간 2) |
| 비지도 추가 학습 | torchvision RAFT, 광도 손실 + 평활 손실 + 가림 마스크 |
| 출력 | `timeline.json` 흐름 필드 (셀·구역 집계값만) |

### 1.3 범위 밖

- 증류·합성 지도 학습 코드: G1 채택 후 11-14~17에 따로 계획한다 (기획 4.2).
- 시계열 예측 모델: `src/predict/`(나예린) 담당이다. 이 문서는 입력 지표와 평가 연결만 다룬다.
- 경계 유입 경보, 판정·알림 API, WebSocket: 별도 작업이다.
- 정지·진행파 지표 `W_c`(난류 조사 6.3 A1): MVP 후보지만 이 학습 계획과 독립이다. 따로 계획한다.
- ptlflow 경유 모델(SEA-RAFT 등): 검증한 API가 없어 다루지 않는다 (모델 조사 5.4).

---

## 2. 모듈 구조

### 2.1 파일 목록 (제안) `[토론]`

| 파일 | 책임 (한 줄) | `torch` 필요 |
|---|---|---|
| `src/__init__.py`, `src/flow/__init__.py` | `python -m src.flow.xxx` 실행을 위한 패키지 표시 (확인 필요: 팀 import 규칙) | 아니오 |
| `src/flow/estimators.py` | Farneback·DIS·RAFT를 `estimate(prev, next) -> (H, W, 2) px` 하나로 감싼다 | RAFT만 |
| `src/flow/ground.py` | 호모그래피로 픽셀 변위를 지면 속도(m/s)로 바꾸고 픽셀별 셀 번호표를 만든다 | 아니오 |
| `src/flow/cells.py` | 픽셀 속도를 셀 통계(`V_c`, `Q_c`, `B_c`)로 줄이고 시간 분산 `S_c`를 갱신한다 | 아니오 |
| `src/flow/noise_floor.py` | 정지 구간 `V_c` 시계열로 셀별 `Var_noise_c`를 잰다 | 아니오 |
| `src/flow/baselines.py` | 현재값 유지·흐름 외삽 기준선과 오차(MAE)를 계산한다 | 아니오 |
| `src/flow/unsup_losses.py` | 역방향 비틀기, 광도·평활 손실, 앞뒤 일치 가림 마스크 | 예 |
| `src/flow/finetune.py` | 프레임 쌍 데이터셋과 비지도 추가 학습 루프, 체크포인트 저장 | 예 |
| `src/flow/timeline_flow.py` | 셀 통계를 `timeline.json` 흐름 필드 사전으로 바꾼다 | 아니오 |
| `src/flow/run_flow.py` | 영상 1개를 1Hz로 분석해 흐름 타임라인을 쓰는 실행 진입점 | 추정기에 따라 |
| `src/flow/eval_flow.py` | 추정기별 중간 1·2 지표와 G1 판정표를 만드는 실행 진입점 | 아니오 |
| `src/flow/configs/*.json` | 학습·분석 설정. 표준 라이브러리 `json`으로 읽는다 (YAML 패키지를 늘리지 않기 위해) | – |
| `tests/flow/test_*.py` | 3장 seam 테스트. 폴더 위치는 CLAUDE.md 구조에 없다 `[토론]` | 일부 |

- 구역 다각형·보행 가능 마스크·호모그래피는 `infra/`(이유노 담당)에서 읽기만 한다. 형식은 담당자와 정한다 `[토론]`.
- 셀 격자는 counting 모듈과 같아야 한다. 같은 호모그래피·원점·셀 크기를 공유한다 `[토론]`.
- 추상 클래스 계층, 플러그인 등록 같은 구조는 만들지 않는다. 추정기는 `Protocol` 하나로 충분하다.

### 2.2 `outputs/` 실험 기록 배치 (제안)

```
outputs/flow/
  runs.csv                     학습 1회 = 1행 (설정 요약 + 중간 1·2 결과)
  runs/<run_id>/
    config.json                학습 설정 전체 (데이터 목록, 해상도, 프레임 간격, 손실 가중치, 학습률, 반복 수, 시드)
    env.txt                    git 커밋 해시, pip freeze, GPU 이름
    train_log.csv              step, 손실 항목별 값, 학습률, 경과 시간
  eval/<estimator_name>/
    noise_floor.csv            셀별 Var_noise_c, 표본 수
    baseline.csv               기준선별 MAE, 표본 수
  g1_decision.csv              G1 판정표 (7.3)
```

- 가중치(`*.pth`)는 여기 두지 않는다. GPU 서버의 저장소 밖 경로에만 둔다 (6장).
- `*.log`는 `.gitignore` 대상이다. 그래서 학습 기록은 `train_log.csv`로 남긴다.
- `runs.csv` 열: `run_id`, `date`, `git_commit`, `model`, `train_videos`, `eval_videos`, `work_hw`, `crop_hw`, `frame_gap`, `photo_loss`, `w_smooth`, `lr`, `max_steps`, `seed`, `ckpt_path`, `noise_floor_median`, `noise_floor_p90`, `mae_persist`, `mae_advect`, `note`.

---

## 3. Seam(공개 경계)

- **seam**: 테스트가 붙는 공개 함수·인터페이스다. 내부 구현을 바꿔도 이 경계의 동작이 같으면 테스트가 통과해야 한다.
- 테스트 도구는 `pytest`다 (`requirements.txt`, 2026-11-09 승인).
- 테스트 폴더는 `tests/flow/`다. CLAUDE.md 폴더 구조에 추가하는 것은 팀 합의 후 한다 `[토론]`.
- 기대값은 코드와 독립인 근거(알려진 이동량·분산의 합성 입력, 손으로 계산한 값)에서 가져온다. 코드와 같은 식으로 다시 계산하지 않는다.

### 3.1 확정 seam (2026-11-09, 사용자 확정)

| 단계 | ID | seam | 확인하는 동작 |
|---|---|---|---|
| G0 | S1 | `FlowEstimator.estimate` | 아래 표 S1 |
| G0 | S4 | `cells.reduce_to_cells` | 아래 표 S4 |
| G0 | S5 | `cells.TemporalInstability.update` | 아래 표 S5 |
| G0 | S6 | `noise_floor.measure_noise_floor` | 아래 표 S6 |
| G0 | S10 | `timeline_flow.build_flow_cells` | 단위, `NaN` → `null`, 신뢰도 낮은 셀 비우기, 픽셀 배열이 들어가지 않는다. 필드 이름은 팀 합의 후 고정한다 |
| G0 | S11 | `run_flow.analyze_video` 통합 | 아래 표 S11. 지면 변환은 배율을 아는 임시 H로 이 안에서만 확인한다 |
| 2단계 | S7 | `baselines.persistence_forecast`, `baselines.advect_density`, `baselines.mae` | 동작만 확인한다: 균일 이동 시 질량 이동, 닫힌 벽에서 질량 보존, 음수 밀도 없음. CFL 분할 같은 내부 구현은 시험하지 않는다 |
| 2단계 | S8 | `unsup_losses.backward_warp`, 손실 전체 함수 | 경계 2개로 줄인다. 흐름 0이면 항등, 정수 이동의 정확한 비틀기, 같은 영상·일정한 흐름이면 손실 ≈ 0 |
| 2단계 | S9 | `finetune.train(cfg)` | 기본: 체크포인트 경로가 저장소 밖이다. `slow` 표시(CPU만): 합성 이동 쌍에서 손실 감소, 같은 시드 2회 결과 일치 |
| G1 | S12 | `eval_flow.g1_decision` | 기획 5.2 판정 규칙. 흐름을 전부 0으로 내는 추정기가 노이즈 바닥만으로 채택되지 않는다 (움직이는 셀 속력 확인) |
| 합의 후 | S2, S3 | `ground.ground_velocity`, `ground.build_cell_index` | 이유노 님과 호모그래피·셀 격자 형식을 합의한 뒤 추가한다 (D14) |

### 3.1.1 구현 현황과 임시 결정 (2026-11-09)

- S1·S4·S5·S6·S7·S8·S9·S10·S11·S12를 TDD로 구현하고 Reviewer 검토를 반영했다. `pytest tests/flow` 154개가 통과한다 (`crowdsight` 환경, CPU).
- S2·S3은 이유노 님과 호모그래피·셀 격자 형식을 합의한 뒤 만든다 (D14). 지금 `ground.py`에는 `ground_velocity`만 있다.
- 구현 중 정한 임시 결정이다. 모두 `(가정) [토론]`이며 코드 docstring에도 표시했다.

| 모듈 | 임시 결정 | 이유 |
|---|---|---|
| `cells.reduce_to_cells` | 주 흐름이 `min_speed`(0.05m/s) 미만인 셀의 역방향 비율 `B_c`는 NaN | 주 흐름 방향이 정의되지 않는다. 0으로 두면 반대 흐름 충돌을 놓친다 |
| `cells.TemporalInstability` | 노이즈 바닥이 NaN인 셀은 다른 셀 중앙값을 쓴다. 모두 NaN이면 0을 빼고 `noise_floor_available=False` | 0으로 바꾸면 잡음 빼기가 조용히 꺼진다 |
| `noise_floor`·`cells` | 두 성분이 모두 유한한 표본만 쓴다. 분산은 n으로 나눈다 | S5와 S6의 빼기가 맞아야 한다 |
| `noise_floor` | 정지 구간 전체 평균 기준이라 S5(30초 창 평균)보다 잡음을 약 3% 더 뺀다 (백색잡음, T=30) | MVP에서 허용 |
| `baselines.advect_density` | 화각 바깥 경계는 영경사 유입(가장자리 밀도 × 안쪽 속도) | 유출만 두면 일정한 통과 흐름이 사라지고 속도를 작게 추정한 모델이 유리해진다 |
| `baselines.advect_density` | 입력 밀도가 NaN인 셀은 출력도 NaN | 현재값 유지와 같은 셀로 평가한다 |
| `unsup_losses` | census는 UFlow처럼 회색조 ×255, 마스크를 `patch // 2`만큼 깎는다. robust 손실에서 상수 `0.01**0.4`를 빼 같은 영상이면 손실 0 | UFlow 원본(`uflow_utils.py`)과 대조. 기울기는 같다 |
| `timeline_flow` | `list[dict]`만 반환하고 `flow_estimator`는 파일 최상위에 한 번 쓴다. 반올림하지 않는다 | D3 결정 전 임시 |
| `run_flow` | `seconds`·`t`·`cells` 키, `rate_hz=1`, 밀도가 없으면 압력 null | 나예린 님과 형식 합의 필요 |
| `ground` | 동차 좌표 `w ≤ 1e-9`인 픽셀(지평선 위·카메라 뒤)은 NaN | 절대 기준이라 H 형식 합의 때 다시 정한다 |
| `finetune` | 좌우 뒤집기(확률 0.5)와 선택형 crop을 쓴다. 밝기 증강은 뺀다 | census가 밝기 변화를 대부분 흡수한다 |
| `finetune` | 영역 마스크가 없으면 오류. `allow_full_mask=True`로만 전체 화면 허용 | 정지 배경이 0 흐름 학습을 부른다 (기획 4.3) |
| `eval_flow.g1_decision` | 노이즈 바닥을 속력 비율 제곱으로 나눠 비교한다. 속력 비율 0.5~2.0만 허용, `mae_tol=0` | 흐름을 k배 줄이면 노이즈가 k²배 줄어 축소만으로 통과하는 함정 |
| `eval_flow.choose_fallback` | 두 지표 모두 1위인 추정기만 고른다. 아니면 None(팀이 고른다) | 조용한 동점 처리 방지 |

### 3.2 Planner 원안 (참고)

| ID | seam | 잡는 것 (catches) | 못 잡는 것 (misses) |
|---|---|---|---|
| S1 | `FlowEstimator.estimate(prev_bgr, next_bgr) -> np.ndarray` | 모양 `(H, W, 2)`·`float32`·px 단위·부호(오른쪽 이동 = +x), 해상도 축소 후 복원 배율. 합성 평행 이동 영상으로 확인 | 실제 군중 영상의 정확도, 가림 처리 |
| S2 | `ground.ground_velocity(flow, h, dt_s, mask)` | 호모그래피 적용 방향, 동차 좌표 나눗셈, `dt` 나눗셈. 알려진 배율 H로 정확한 값 비교 | 호모그래피 자체의 보정 오차, 머리 높이 평면 선택의 옳고 그름 |
| S3 | `ground.build_cell_index(...)` | 픽셀 → 셀 번호, 보행 불가 영역 `-1`, 격자 범위 밖 처리 | counting 모듈 격자와 실제로 같은지 (통합 시험으로 확인) |
| S4 | `cells.reduce_to_cells(cell_ids, vel, n_cells)` | 셀 평균, 빈 셀 `NaN`, 유효 픽셀 수 `Q_c`, 역방향 비율 `B_c` | 셀 크기·마스크 선택의 적절성 |
| S5 | `cells.TemporalInstability.update(mean_v)` | 난류 조사 V1: 알려진 분산의 합성 시계열에서 `S_c` 일치, 창 채우기 전 `NaN`, 잡음 빼기 후 0 아래 자르기 | 창 길이 T의 적절성 (V5 민감도 분석으로 본다) |
| S6 | `noise_floor.measure_noise_floor(series, static_mask)` | 정지 표시 표본만 쓰는지, 표본 부족 셀 `NaN`, 단위 m²/s² | "정지 구간" 선정 자체가 맞는지 |
| S7 | `baselines.persistence_forecast`, `baselines.advect_density`, `baselines.mae` | 균일 이동 시 질량이 옮겨지는지, 닫힌 벽에서 질량 보존, 음수 밀도 없음, CFL 분할 | 외삽이 실제 군중 움직임을 잘 따르는지 |
| S8 | `unsup_losses.backward_warp`, `photometric_loss`, `smoothness_loss`, `fb_consistency_mask` | 흐름 0이면 항등, 정수 이동의 정확한 비틀기, 같은 영상이면 광도 손실 ≈ 0, 일정한 흐름이면 평활 손실 0, 일치하는 앞뒤 흐름이면 마스크 1 | 손실이 줄어도 흐름이 정확해지는지 (기획 4.2 단점) |
| S9 | `finetune.train(cfg)` 짧은 실행 | 합성 이동 프레임 쌍에서 몇십 step 안에 손실이 줄어든다, 체크포인트 경로가 저장소 밖이다, 같은 시드 2회 결과가 허용 오차 안이다 | 실제 데이터 학습 효과, 긴 학습의 안정성 |
| S10 | `timeline_flow.build_flow_cells(...)` | 필드 이름·단위, `NaN` → `null`, 신뢰도 낮은 셀 비우기, 픽셀 배열이 들어가지 않는다 | 필드 이름이 팀 합의와 같은지 (합의 후 고정) |
| S11 | `run_flow.analyze_video(...)` 통합 | 합성 영상 1개 → 초마다 셀 레코드가 나온다, 1Hz 간격, 흐름장 파일이 생기지 않는다 | 실제 영상 처리 시간, 코덱별 프레임 탐색 차이 |

- S1의 RAFT 시험은 `torch`가 없으면 건너뛴다. CPU에서도 돌지만 느리다.
- S9는 GPU 없이 `raft_small` + 작은 해상도(128×128 이상, 8의 배수)로 돌린다 (가정).

---

## 4. 단계별 구현

### 4.0 단계 0: 준비 (11-09)

| 항목 | 내용 |
|---|---|
| 할 일 | `numpy`·`opencv-python` 추가 승인, `torch`·`torchvision` 추가 승인 요청, 테스트 도구 결정, `timeline.json` 흐름 필드 초안 공유 |
| 파일 | `requirements.txt`(승인 후 담당자가 반영) |
| 완료 조건 | 승인 결과가 팀 채널에 기록됨. `requirements.txt`에 버전이 적힘 |
| 증명 | 새 가상환경에서 `pip install -r requirements.txt` 후 `python -c "import cv2, numpy"` 성공 |

- `requirements.txt`가 비어 있으므로 `numpy`, `opencv-python`도 승인 대상이다 (CLAUDE.md 패키지 규칙).

### 4.1 단계 1: 사전학습 파이프라인 끝까지 (11-09~11-10, G0)

| 항목 | 내용 |
|---|---|
| 할 일 | 추정기 3종, 지면 변환, 셀 통계, 시간 분산, 타임라인 출력, 실행 진입점. 2분 영상으로 노이즈 바닥 측정 |
| 파일 | `estimators.py`, `ground.py`, `cells.py`, `noise_floor.py`, `timeline_flow.py`, `run_flow.py`, `configs/analyze_default.json` |
| 완료 조건 | 2분 영상 1개에서 Farneback·사전학습 RAFT 각각 흐름 타임라인 JSON이 나온다. 초마다 셀 레코드에 2.2 필드가 있다. `outputs/flow/eval/<estimator>/noise_floor.csv`가 두 추정기 모두 있다 |
| 증명 | S1~S6, S10, S11 통과. 실제 영상 실행 결과 파일 존재 |

- 밀도 `rho*_c`가 아직 없으면 `flow_pressure`는 `null`로 둔다. 나머지 필드는 낸다.
- DIS는 같은 단계에 넣지만 G0 완료 조건에는 넣지 않는다 (가정).

### 4.2 단계 2: 추가 학습과 기준선 (11-10~11-12)

| 항목 | 내용 |
|---|---|
| 할 일 | 비지도 손실, 학습 루프, GPU 서버 실행. 기준선 2종과 오차. 평가 진입점 |
| 파일 | `unsup_losses.py`, `finetune.py`, `baselines.py`, `eval_flow.py`, `configs/finetune_v1.json` |
| 완료 조건 | GPU 서버에서 학습 1회 이상 끝남. `outputs/flow/runs.csv`에 1행 이상, `runs/<run_id>/train_log.csv` 존재. 사전학습 RAFT·Farneback·추가 학습 RAFT의 `baseline.csv` 존재 |
| 증명 | S7~S9 통과. 학습 로그에서 손실 감소 확인. 학습·평가 영상 목록이 겹치지 않음을 `eval_flow.py`가 검사 |

### 4.3 단계 3: G1 판정 (11-13)

| 항목 | 내용 |
|---|---|
| 할 일 | 같은 평가 영상·셀·창에서 추정기별 중간 1·2 지표 계산. 기획 5.2 기준 판정 |
| 파일 | `eval_flow.py` 실행 결과 `outputs/flow/g1_decision.csv` |
| 완료 조건 | 판정표에 채택/불채택과 근거 수치가 적힘. 팀에 공유됨 |
| 증명 | 판정표의 수치를 `noise_floor.csv`·`baseline.csv`에서 다시 계산해 같은 값이 나온다 |

### 4.4 단계 4: 분기 (11-14~11-17)

| 분기 | 할 일 | 완료 조건 |
|---|---|---|
| 채택 | 증류와 비교 계획 작성 후 실행 (범위 밖 1.3). 나예린 님 시계열 모델 입력으로 흐름 타임라인 전달 | 비교표 |
| 불채택 | 사전학습 추정기 중 가장 나은 것으로 `configs/analyze_default.json` 고정. 난류 조사 V1·V2·V5 수행 | V1 테스트 통과, V2 표, V5 민감도 표 (셀 크기 1·2m, T 10·30·60초, 추정기별) |

### 4.5 단계 5: G2 최종 비교 (11-18)와 동결 (11-19)

- G2: 흐름 추정기만 바꾸고 나머지(셀, 창, 시계열 모델, 시드)는 고정해 시계열 모델 예측 오차표를 만든다 (기획 2.3).
- 11-19: 코드 동결. 동결 후에는 설정 파일의 추정기 이름만 확인한다.

---

## 5. 코드 초안

- 모든 코드는 초안이다. 실행해 검증하지 않았다.
- PEP 8, 타입힌트, 한국어 docstring을 따른다.
- torchvision RAFT API는 모델 조사 5.3에서 확인한 사실만 쓴다:
    - `raft_small`/`raft_large`, `Raft_Small_Weights.DEFAULT`/`Raft_Large_Weights.DEFAULT`
    - `weights.transforms()`가 두 영상을 [-1, 1]로 바꾼다.
    - 높이·너비는 8의 배수, 최소 128×128이다.
    - 출력은 반복별 흐름 목록이고 마지막 원소가 최종 결과다. 반복 횟수 인자는 `num_flow_updates`(기본 12)다.

### 5.1 흐름 추정기 (`src/flow/estimators.py`)

```python
"""흐름 추정기 어댑터. 모든 추정기는 같은 입출력을 쓴다."""
from __future__ import annotations

from pathlib import Path
from typing import Protocol

import cv2
import numpy as np


class FlowEstimator(Protocol):
    """두 프레임 사이 광학 흐름을 구하는 추정기의 공통 인터페이스."""

    name: str

    def estimate(self, prev_bgr: np.ndarray, next_bgr: np.ndarray) -> np.ndarray:
        """BGR uint8 프레임 2장의 흐름을 (H, W, 2) float32, px 단위로 돌려준다."""
        ...


def _to_gray(img_bgr: np.ndarray) -> np.ndarray:
    """BGR 프레임을 회색조 uint8로 바꾼다."""
    return cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)


class FarnebackEstimator:
    """OpenCV Farneback 흐름. 학습하지 않는 기준선이다."""

    def __init__(self) -> None:
        """기본 파라미터(proposal-detail 3.4 시작값, 가정)로 만든다."""
        self.name = "farneback-cv2"

    def estimate(self, prev_bgr: np.ndarray, next_bgr: np.ndarray) -> np.ndarray:
        """Farneback 흐름을 px 단위로 돌려준다."""
        # 인자 순서: prev, next, flow, pyr_scale, levels, winsize,
        # iterations, poly_n, poly_sigma, flags. 값은 시작값 (가정)
        flow = cv2.calcOpticalFlowFarneback(
            _to_gray(prev_bgr), _to_gray(next_bgr), None,
            0.5, 3, 15, 3, 5, 1.2, 0,
        )
        return flow.astype(np.float32)


class DisEstimator:
    """OpenCV DIS 흐름. 학습하지 않는 기준선이다."""

    def __init__(self, preset: int = cv2.DISOPTICAL_FLOW_PRESET_MEDIUM) -> None:
        """DIS 프리셋을 정해 만든다. TUB CrowdFlow DIS4·DIS2와의 대응은 (확인 필요)."""
        self.name = f"dis-cv2-preset{preset}"
        self._dis = cv2.DISOpticalFlow_create(preset)

    def estimate(self, prev_bgr: np.ndarray, next_bgr: np.ndarray) -> np.ndarray:
        """DIS 흐름을 px 단위로 돌려준다."""
        return self._dis.calc(_to_gray(prev_bgr), _to_gray(next_bgr), None)


class RaftEstimator:
    """torchvision RAFT 흐름. 사전학습 가중치 또는 추가 학습 체크포인트를 쓴다."""

    def __init__(
        self,
        size: str = "large",
        checkpoint: Path | None = None,
        device: str = "cuda",
        work_hw: tuple[int, int] = (544, 960),
        num_flow_updates: int = 12,
    ) -> None:
        """모델을 만든다. work_hw는 추론 해상도이며 8의 배수여야 한다."""
        import torch
        from torchvision.models.optical_flow import (
            Raft_Large_Weights, Raft_Small_Weights, raft_large, raft_small,
        )

        if work_hw[0] % 8 or work_hw[1] % 8 or min(work_hw) < 128:
            raise ValueError("work_hw는 8의 배수이고 128 이상이어야 한다")
        if size == "large":
            weights, builder = Raft_Large_Weights.DEFAULT, raft_large
        elif size == "small":
            weights, builder = Raft_Small_Weights.DEFAULT, raft_small
        else:
            raise ValueError(f"알 수 없는 size: {size}")

        # 추가 학습 모델도 사전학습과 같은 정규화로 학습하므로 전처리를 공유한다.
        self._preprocess = weights.transforms()
        if checkpoint is None:
            model = builder(weights=weights)
            self.name = f"raft_{size}-pretrained-{weights}"  # 문자열 표기 (확인 필요)
        else:
            model = builder(weights=None)
            state = torch.load(checkpoint, map_location="cpu", weights_only=True)
            model.load_state_dict(state)
            self.name = f"raft_{size}-ft-{Path(checkpoint).stem}"
        self._model = model.to(device).eval()
        self._device = device
        self._work_hw = work_hw
        self._iters = num_flow_updates
        self._torch = torch

    def _to_tensor(self, img_bgr: np.ndarray) -> "torch.Tensor":
        """BGR 프레임을 작업 해상도의 (1, 3, h, w) uint8 RGB 텐서로 바꾼다."""
        h, w = self._work_hw
        rgb = cv2.cvtColor(cv2.resize(img_bgr, (w, h)), cv2.COLOR_BGR2RGB)
        return self._torch.from_numpy(rgb).permute(2, 0, 1).unsqueeze(0).contiguous()

    def estimate(self, prev_bgr: np.ndarray, next_bgr: np.ndarray) -> np.ndarray:
        """RAFT 흐름을 원본 해상도 px 단위로 돌려준다."""
        h0, w0 = prev_bgr.shape[:2]
        h, w = self._work_hw
        a, b = self._preprocess(self._to_tensor(prev_bgr), self._to_tensor(next_bgr))
        with self._torch.no_grad():
            flows = self._model(
                a.to(self._device), b.to(self._device),
                num_flow_updates=self._iters,
            )
        flow = flows[-1][0].permute(1, 2, 0).cpu().numpy()  # 마지막 반복 결과
        flow = cv2.resize(flow, (w0, h0), interpolation=cv2.INTER_LINEAR)
        flow[..., 0] *= w0 / w  # 작업 해상도 px → 원본 px
        flow[..., 1] *= h0 / h
        return flow.astype(np.float32)
```

- `torch`는 `RaftEstimator` 안에서만 가져온다. 그래서 Farneback·DIS만 쓸 때는 `torch` 없이 돈다.
- 사전학습 가중치는 첫 실행 때 자동으로 내려받는다 [M2]. GPU 서버의 외부 접속 가능 여부는 (확인 필요)다.

### 5.2 지면 변환과 셀 번호표 (`src/flow/ground.py`)

```python
"""픽셀 변위를 지면 속도로 바꾸고, 픽셀별 셀 번호표를 만든다."""
from __future__ import annotations

import numpy as np


def apply_homography(h: np.ndarray, pts: np.ndarray) -> np.ndarray:
    """(N, 2) 영상 좌표에 3×3 호모그래피를 적용해 (N, 2) 지면 좌표(m)를 돌려준다."""
    ones = np.ones((pts.shape[0], 1), dtype=np.float64)
    p = np.hstack([pts.astype(np.float64), ones]) @ h.T
    return p[:, :2] / p[:, 2:3]


def ground_velocity(
    flow: np.ndarray, h: np.ndarray, dt_s: float, mask: np.ndarray,
) -> np.ndarray:
    """마스크 픽셀의 흐름을 지면 속도 (N, 2) m/s로 바꾼다.

    v = (H·(p + f) − H·p) / dt (proposal-detail 3.4(2)).
    픽셀 순서는 np.nonzero(mask)의 행 우선 순서이며 cell_index[mask]와 같다.
    h는 속도용 호모그래피다. 바닥 평면인지 머리 높이 평면인지는 [토론].
    """
    ys, xs = np.nonzero(mask)
    p = np.stack([xs, ys], axis=1).astype(np.float64)
    d = flow[ys, xs].astype(np.float64)
    g0 = apply_homography(h, p)
    g1 = apply_homography(h, p + d)
    return (g1 - g0) / dt_s


def build_cell_index(
    h_cell: np.ndarray,
    image_hw: tuple[int, int],
    walkable: np.ndarray,
    origin_m: tuple[float, float],
    cell_m: float,
    grid_ny_nx: tuple[int, int],
) -> np.ndarray:
    """픽셀마다 셀 번호(iy * nx + ix)를 담은 (H, W) int32 표를 만든다.

    보행 불가 픽셀과 격자 밖 픽셀은 -1이다.
    h_cell은 counting 모듈과 같은 호모그래피를 써야 셀이 일치한다 [토론].
    """
    hh, ww = image_hw
    ny, nx = grid_ny_nx
    ys, xs = np.mgrid[0:hh, 0:ww]
    pts = np.stack([xs.ravel(), ys.ravel()], axis=1)
    g = apply_homography(h_cell, pts)
    ix = np.floor((g[:, 0] - origin_m[0]) / cell_m).astype(np.int64)
    iy = np.floor((g[:, 1] - origin_m[1]) / cell_m).astype(np.int64)
    ok = (ix >= 0) & (ix < nx) & (iy >= 0) & (iy < ny) & walkable.ravel()
    index = np.full(hh * ww, -1, dtype=np.int32)
    index[ok] = (iy[ok] * nx + ix[ok]).astype(np.int32)
    return index.reshape(hh, ww)
```

- 셀 번호표는 영상마다 한 번만 만든다. 픽셀 위치는 바뀌지 않기 때문이다.
- 셀 배정용 `h_cell`과 속도용 `h`를 나눈 이유:
    - 셀 배정은 counting 모듈과 같아야 한다.
    - 속도 변환은 흐름이 잡히는 머리·어깨 높이 평면이 맞을 수 있다 (난류 조사 5.2, C3) `[토론]`.
- 척도 10% 오차는 분산·압력을 약 21% 바꾼다 (난류 조사 5.2). 호모그래피 선택은 결과 수치에 직접 영향을 준다.

### 5.3 셀 통계와 시간 분산 (`src/flow/cells.py`)

```python
"""픽셀 속도를 셀 통계로 줄이고, 셀 평균 속도의 시간 분산 S_c를 갱신한다."""
from __future__ import annotations

import warnings
from dataclasses import dataclass

import numpy as np


@dataclass
class CellFlow:
    """한 시점의 셀 통계. 흐름장은 담지 않는다."""

    mean_v: np.ndarray       # (n_cells, 2) 셀 평균 지면 속도 V_c [m/s], 빈 셀은 NaN
    count: np.ndarray        # (n_cells,) 유효 픽셀 수 Q_c
    counterflow: np.ndarray  # (n_cells,) 역방향 픽셀 비율 B_c [0~1], 빈 셀은 NaN


def reduce_to_cells(
    cell_ids: np.ndarray, vel: np.ndarray, n_cells: int, min_speed: float = 0.05,
) -> CellFlow:
    """픽셀 속도 (N, 2)를 셀 번호 (N,)별로 모아 셀 통계를 만든다.

    역방향 비율은 셀 평균과 내적이 음수이고 min_speed(m/s, 가정) 이상인 픽셀의 비율이다.
    """
    count = np.bincount(cell_ids, minlength=n_cells).astype(np.float64)
    sx = np.bincount(cell_ids, weights=vel[:, 0], minlength=n_cells)
    sy = np.bincount(cell_ids, weights=vel[:, 1], minlength=n_cells)
    with np.errstate(invalid="ignore", divide="ignore"):
        mean_v = np.stack([sx, sy], axis=1) / count[:, None]
        dot = (vel * mean_v[cell_ids]).sum(axis=1)
        moving = np.linalg.norm(vel, axis=1) >= min_speed
        opp = np.bincount(
            cell_ids, weights=((dot < 0) & moving).astype(np.float64),
            minlength=n_cells,
        )
        counterflow = opp / count
    return CellFlow(mean_v=mean_v, count=count.astype(np.int64), counterflow=counterflow)


class TemporalInstability:
    """S_c(t) = max(<|V_c − U_c|²>_T − Var_noise_c, 0)를 계산한다 (난류 조사 6.4).

    U_c는 최근 T초 창의 평균으로 둔다. 그러면 <|V_c − U_c|²>_T는 창 안 시간 분산이다 (가정).
    셀 평균 시계열만 메모리에 두며 흐름장은 보관하지 않는다.
    """

    def __init__(
        self,
        n_cells: int,
        window_s: float = 30.0,
        rate_hz: float = 1.0,
        noise_var: np.ndarray | None = None,
        min_valid_ratio: float = 0.8,
    ) -> None:
        """창 길이(가정: 30초)와 셀별 잡음 분산으로 초기화한다."""
        self._len = int(round(window_s * rate_hz))
        self._buf = np.full((self._len, n_cells, 2), np.nan)
        self._pos = 0
        self._filled = 0
        self._noise = np.zeros(n_cells) if noise_var is None else np.nan_to_num(noise_var)
        self._min_valid = int(np.ceil(min_valid_ratio * self._len))

    def update(self, mean_v: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """새 V_c (n_cells, 2)를 넣고 (S_c, 잡음 빼기 전 분산)을 m²/s²로 돌려준다.

        창이 다 차기 전이거나 유효 표본이 부족한 셀은 NaN이다.
        """
        self._buf[self._pos] = mean_v
        self._pos = (self._pos + 1) % self._len
        self._filled = min(self._filled + 1, self._len)
        n_cells = mean_v.shape[0]
        if self._filled < self._len:
            empty = np.full(n_cells, np.nan)
            return empty, empty.copy()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", category=RuntimeWarning)  # 모두 NaN인 셀
            u = np.nanmean(self._buf, axis=0)                          # U_c
            raw = np.nanmean(((self._buf - u) ** 2).sum(axis=2), axis=0)
        valid = np.isfinite(self._buf[..., 0]).sum(axis=0) >= self._min_valid
        raw[~valid] = np.nan
        s = np.maximum(raw - self._noise, 0.0)
        s[~valid] = np.nan
        return s, raw


def pressure(rho: np.ndarray, s: np.ndarray) -> np.ndarray:
    """P_c = rho*_c × S_c [1/s²]. rho는 counting 모듈의 EMA 밀도 [명/㎡]다."""
    return rho * s
```

- `((NaN − u) ** 2).sum(axis=2)`는 빈 칸에서 0이 아니라 `NaN`이 되어야 한다. `sum`은 `NaN`을 그대로 전파하므로 `nanmean`에서 빠진다.
- 셀 내부 공간 분산(기존 `Var_c(v)`)은 만들지 않는다. 기획 2.1이 시간 분산을 택했다. V5 민감도 분석에서 공간 분산이 필요하면 그때 더한다.

### 5.4 노이즈 바닥 (`src/flow/noise_floor.py`)

```python
"""정지 구간의 셀 평균 속도 시계열로 셀별 잡음 분산을 잰다 (중간 1, 난류 조사 V2)."""
from __future__ import annotations

import warnings

import numpy as np


def measure_noise_floor(
    mean_v_series: np.ndarray, static_mask: np.ndarray, min_samples: int = 30,
) -> np.ndarray:
    """(T, n_cells, 2) V_c 시계열에서 static_mask (T, n_cells)가 참인 표본만으로 Var_noise_c [m²/s²]를 낸다.

    표본이 min_samples(가정)보다 적은 셀은 NaN이다.
    """
    v = np.where(static_mask[..., None], mean_v_series, np.nan)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=RuntimeWarning)
        u = np.nanmean(v, axis=0)
        var = np.nanmean(((v - u) ** 2).sum(axis=2), axis=0)
    n = np.isfinite(v[..., 0]).sum(axis=0)
    var[n < min_samples] = np.nan
    return var


def summarize_noise_floor(var: np.ndarray) -> dict[str, float]:
    """셀별 잡음 분산을 중앙값·90백분위·유효 셀 수로 요약한다."""
    ok = var[np.isfinite(var)]
    if ok.size == 0:
        return {"median": float("nan"), "p90": float("nan"), "n_cells": 0}
    return {
        "median": float(np.median(ok)),
        "p90": float(np.percentile(ok, 90)),
        "n_cells": int(ok.size),
    }
```

- "정지" 표시 방법 `[토론]`:
    - 안 1: 사람이 없는 셀·시간. counting의 `rho*_c`가 0에 가까운 표본 (가정: 0.05명/㎡ 미만).
    - 안 2: 사람이 직접 고른 정지 구간(시작·끝 초).
- 정지 배경 셀의 잡음은 사람이 있는 셀의 잡음과 다를 수 있다 (가정). 그래서 `Var_noise_c`를 빼는 것은 하한 보정이다.

### 5.5 단순 기준선 (`src/flow/baselines.py`)

```python
"""60초 예측의 단순 기준선과 오차 (중간 2). 정답은 흐름과 독립인 셀 밀도다 (기획 2.3)."""
from __future__ import annotations

import math

import numpy as np


def persistence_forecast(rho_now: np.ndarray) -> np.ndarray:
    """현재값 유지: T초 뒤 밀도 = 지금 밀도."""
    return rho_now.copy()


def advect_density(
    rho: np.ndarray,
    vel: np.ndarray,
    walkable: np.ndarray,
    cell_m: float,
    horizon_s: float,
    dt_s: float = 1.0,
) -> np.ndarray:
    """셀 밀도 (ny, nx)를 셀 속도 (ny, nx, 2)로 horizon_s초 옮긴다 (흐름 외삽, 가정).

    1차 상류(upwind) 유한체적이다. 예측 동안 속도는 고정한다.
    보행 불가 셀과의 면은 막고, 격자 바깥 경계는 나가는 흐름만 허용한다 (화각 밖 유출).
    vel[..., 0]은 열(x) 방향, vel[..., 1]은 행(y) 방향 속도 [m/s]다.
    """
    rho = np.where(walkable, np.nan_to_num(rho), 0.0)
    u = np.where(walkable, np.nan_to_num(vel[..., 0]), 0.0)
    v = np.where(walkable, np.nan_to_num(vel[..., 1]), 0.0)
    ux = 0.5 * (u[:, :-1] + u[:, 1:]) * (walkable[:, :-1] & walkable[:, 1:])
    vy = 0.5 * (v[:-1, :] + v[1:, :]) * (walkable[:-1, :] & walkable[1:, :])

    vmax = max(np.abs(u).max(initial=0.0), np.abs(v).max(initial=0.0))
    n_sub = max(1, math.ceil(vmax * dt_s / cell_m / 0.5))  # 축당 CFL ≤ 0.5
    h = dt_s / n_sub
    for _ in range(int(round(horizon_s / dt_s)) * n_sub):
        fx = np.where(ux > 0, rho[:, :-1], rho[:, 1:]) * ux  # 면 유량 [명/(m·s)]
        fy = np.where(vy > 0, rho[:-1, :], rho[1:, :]) * vy
        out = np.zeros_like(rho)                              # 셀 순유출
        out[:, :-1] += fx
        out[:, 1:] -= fx
        out[:-1, :] += fy
        out[1:, :] -= fy
        out[:, 0] += rho[:, 0] * np.maximum(-u[:, 0], 0.0)
        out[:, -1] += rho[:, -1] * np.maximum(u[:, -1], 0.0)
        out[0, :] += rho[0, :] * np.maximum(-v[0, :], 0.0)
        out[-1, :] += rho[-1, :] * np.maximum(v[-1, :], 0.0)
        rho = rho - h / cell_m * out
    return rho


def mae(pred: np.ndarray, true: np.ndarray, mask: np.ndarray) -> float:
    """마스크 안 유한한 칸의 평균 절대 오차."""
    ok = mask & np.isfinite(pred) & np.isfinite(true)
    return float(np.abs(pred[ok] - true[ok]).mean()) if ok.any() else float("nan")


def baseline_errors(
    rho_series: np.ndarray,
    vel_series: np.ndarray,
    walkable: np.ndarray,
    cell_m: float,
    horizon_s: int = 60,
) -> dict[str, float]:
    """1Hz 시계열 rho (T, ny, nx), V (T, ny, nx, 2)로 두 기준선의 MAE를 낸다.

    정답 rho*_c(t + T)는 counting 출력이며 흐름 추정기와 무관하다.
    """
    p_err, a_err = [], []
    for t in range(rho_series.shape[0] - horizon_s):
        true = rho_series[t + horizon_s]
        p_err.append(mae(persistence_forecast(rho_series[t]), true, walkable))
        pred = advect_density(rho_series[t], vel_series[t], walkable, cell_m, horizon_s)
        a_err.append(mae(pred, true, walkable))
    mp, ma = float(np.nanmean(p_err)), float(np.nanmean(a_err))
    return {"mae_persist": mp, "mae_advect": ma, "skill_advect": 1.0 - ma / mp, "n": len(p_err)}
```

- 셀 면적은 `cell_m²`로 둔다. 보행 가능 면적 비율은 무시한다 (가정).
- 외삽 속도로 순간값 `V_c(t)`를 쓴다. 최근 몇 초 평균이 나을 수 있다 (가정). V5에서 함께 본다.
- `proposal-detail.md` 3.4(4)의 경계 유출·도착 시간 모델을 셀 격자 안으로 줄인 형태다 (기획 5.1, 가정).
- 현재값 유지 오차는 추정기와 무관하다. 추정기 비교에는 `mae_advect`와 `skill_advect`를 본다.

### 5.6 비지도 손실 (`src/flow/unsup_losses.py`)

```python
"""비지도 광학 흐름 손실. 영상은 [0, 1] 범위 (B, 3, H, W) 텐서를 받는다."""
from __future__ import annotations

import torch
import torch.nn.functional as F


def backward_warp(img: torch.Tensor, flow: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
    """img를 x + flow 위치에서 표본해 (비틀린 영상, 화면 안 마스크)를 돌려준다.

    flow는 (B, 2, H, W) px 단위, 채널 0이 x다.
    """
    b, _, h, w = img.shape
    ys, xs = torch.meshgrid(
        torch.arange(h, device=img.device, dtype=img.dtype),
        torch.arange(w, device=img.device, dtype=img.dtype),
        indexing="ij",
    )
    x = xs + flow[:, 0]
    y = ys + flow[:, 1]
    grid = torch.stack([2.0 * x / (w - 1) - 1.0, 2.0 * y / (h - 1) - 1.0], dim=-1)
    warped = F.grid_sample(img, grid, mode="bilinear", padding_mode="zeros", align_corners=True)
    inside = ((x >= 0) & (x <= w - 1) & (y >= 0) & (y <= h - 1)).unsqueeze(1).to(img.dtype)
    return warped, inside


def fb_consistency_mask(
    f12: torch.Tensor, f21: torch.Tensor, alpha1: float = 0.01, alpha2: float = 0.5,
) -> torch.Tensor:
    """앞뒤 흐름 일치 검사로 가려지지 않은 픽셀 마스크 (B, 1, H, W)를 만든다.

    |f12 + f21(x + f12)|² < alpha1·(|f12|² + |f21(x + f12)|²) + alpha2 이면 1.
    상수는 UnFlow 계열 관례값이다 (확인 필요). 기울기는 흐르지 않는다.
    """
    f21_w, _ = backward_warp(f21, f12)
    diff = (f12 + f21_w).pow(2).sum(1, keepdim=True)
    bound = alpha1 * (f12.pow(2).sum(1, keepdim=True) + f21_w.pow(2).sum(1, keepdim=True)) + alpha2
    return (diff < bound).to(f12.dtype).detach()


def charbonnier(x: torch.Tensor, eps: float = 1e-3, alpha: float = 0.45) -> torch.Tensor:
    """일반화 Charbonnier (x² + eps²)^alpha. 상수는 (가정)."""
    return (x.pow(2) + eps ** 2).pow(alpha)


def _gray(img: torch.Tensor) -> torch.Tensor:
    """RGB [0, 1] 영상을 회색조 (B, 1, H, W)로 바꾼다."""
    r, g, b = img[:, 0:1], img[:, 1:2], img[:, 2:3]
    return 0.299 * r + 0.587 * g + 0.114 * b


def _census(gray: torch.Tensor, patch: int = 7) -> torch.Tensor:
    """부드러운 census 변환. 주변 patch×patch 픽셀과의 밝기 차이 부호를 연속값으로 낸다."""
    b, _, h, w = gray.shape
    p = F.unfold(gray, patch, padding=patch // 2).view(b, patch * patch, h, w)
    d = p - gray
    return d / torch.sqrt(0.81 + d * d)


def photometric_loss(
    img1: torch.Tensor, img2_warped: torch.Tensor, mask: torch.Tensor, kind: str = "census",
) -> torch.Tensor:
    """마스크 안 광도 손실의 평균.

    kind: "census"(밝기 변화에 강함) 또는 "charbonnier"(단순). 기본값 선택은 (가정).
    census 상수(0.81, 0.1)는 UFlow·DDFlow 구현 관례값이다 (확인 필요).
    """
    if kind == "census":
        t1, t2 = _census(_gray(img1)), _census(_gray(img2_warped))
        dist = (t1 - t2).pow(2)
        per_px = (dist / (0.1 + dist)).sum(1, keepdim=True)
    elif kind == "charbonnier":
        per_px = charbonnier(img1 - img2_warped).mean(1, keepdim=True)
    else:
        raise ValueError(f"알 수 없는 kind: {kind}")
    return (per_px * mask).sum() / (mask.sum() + 1e-6)


def smoothness_loss(
    flow: torch.Tensor, img: torch.Tensor, mask: torch.Tensor, edge_weight: float = 150.0,
) -> torch.Tensor:
    """경계 인식 1차 평활 손실. 영상 경계에서는 흐름이 바뀌어도 벌점을 줄인다.

    edge_weight는 [0, 1] 영상 기준값이다 (가정). mask는 군중·보행 영역이다.
    """
    dfx = (flow[..., :, 1:] - flow[..., :, :-1]).abs()
    dfy = (flow[..., 1:, :] - flow[..., :-1, :]).abs()
    wx = torch.exp(-edge_weight * (img[..., :, 1:] - img[..., :, :-1]).abs().mean(1, keepdim=True))
    wy = torch.exp(-edge_weight * (img[..., 1:, :] - img[..., :-1, :]).abs().mean(1, keepdim=True))
    mx, my = mask[..., :, 1:] * mask[..., :, :-1], mask[..., 1:, :] * mask[..., :-1, :]
    lx = (wx * dfx * mx).sum() / (2 * mx.sum() + 1e-6)
    ly = (wy * dfy * my).sum() / (2 * my.sum() + 1e-6)
    return lx + ly


def sequence_unsup_loss(
    f12s: list[torch.Tensor],
    f21s: list[torch.Tensor],
    img1: torch.Tensor,
    img2: torch.Tensor,
    region: torch.Tensor,
    w_smooth: float = 0.1,
    gamma: float = 0.8,
    kind: str = "census",
) -> tuple[torch.Tensor, dict[str, float]]:
    """RAFT 반복별 양방향 흐름에 감쇠 가중치 gamma^(N−1−i)를 둔 비지도 손실 (가정).

    region은 보행 가능·군중 영역 마스크 (B, 1, H, W)다 (기획 4.3).
    가림 마스크는 마지막 반복의 앞뒤 흐름으로 한 번 만들어 모든 반복에 쓴다 (가정).
    """
    occ12 = fb_consistency_mask(f12s[-1], f21s[-1])
    occ21 = fb_consistency_mask(f21s[-1], f12s[-1])
    n = len(f12s)
    total = img1.new_zeros(())
    log = {"photo": 0.0, "smooth": 0.0}
    for i, (f12, f21) in enumerate(zip(f12s, f21s)):
        wgt = gamma ** (n - 1 - i)
        w2, in2 = backward_warp(img2, f12)
        w1, in1 = backward_warp(img1, f21)
        m12, m21 = region * occ12 * in2, region * occ21 * in1
        photo = photometric_loss(img1, w2, m12, kind) + photometric_loss(img2, w1, m21, kind)
        smooth = smoothness_loss(f12, img1, region) + smoothness_loss(f21, img2, region)
        total = total + wgt * (photo + w_smooth * smooth)
        if i == n - 1:
            log = {"photo": float(photo.detach()), "smooth": float(smooth.detach())}
    return total, log
```

- 손실 종류 선택 (가정):
    - 기본은 census다. 기획 4.3이 밝기 변화에 강한 손실을 제안했다. UFlow가 비교한 손실 중 무엇이 가장 나았는지는 원문으로 확인한다 (확인 필요).
    - 첫 학습이 불안정하면 `charbonnier`로 바꿔 비교한다.
- census는 반복 12회 × 양방향 × 49채널을 만든다. GPU 메모리가 부족하면 마지막 몇 반복에만 손실을 걸거나 자르기 크기를 줄인다 (가정).

### 5.7 추가 학습 루프 (`src/flow/finetune.py`)

```python
"""torchvision RAFT 비지도 추가 학습. GPU 서버에서 백그라운드로 실행한다."""
from __future__ import annotations

import csv
import json
import os
import random
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

import cv2
import numpy as np
import torch
from torch.utils.data import DataLoader, Dataset
from torchvision.models.optical_flow import (
    Raft_Large_Weights, Raft_Small_Weights, raft_large, raft_small,
)

from src.flow.unsup_losses import sequence_unsup_loss

REPO_ROOT = Path(__file__).resolve().parents[2]


@dataclass
class FinetuneConfig:
    """학습 설정. 값은 모두 시작값이다 (가정)."""

    run_id: str
    train_videos: list[str]                 # 영상 경로 (GPU 서버 데이터 폴더, 저장소 밖)
    eval_videos: list[str]                  # 학습에 쓰지 않는 평가 영상 (기획 3.1)
    region_masks: dict[str, str]            # 영상 경로 → 보행 영역 마스크 PNG 경로 [토론]
    size: str = "small"
    work_hw: tuple[int, int] = (544, 960)   # 8의 배수
    crop_hw: tuple[int, int] = (368, 496)   # 8의 배수, 메모리 절약용 무작위 자르기
    frame_gap: int = 6                      # 프레임 간격. 30fps면 0.2초 (proposal-detail 3.4)
    pairs_per_video: int = 2000
    iters: int = 12                         # num_flow_updates
    photo_loss: str = "census"
    w_smooth: float = 0.1
    gamma: float = 0.8
    lr: float = 1e-5                        # 망각을 줄이려 작게 둔다 (기획 4.3)
    weight_decay: float = 1e-5
    batch_size: int = 2
    max_steps: int = 5000
    save_every: int = 500
    clip_grad: float = 1.0
    seed: int = 42
    num_workers: int = 4
    device: str = "cuda"
    extra: dict = field(default_factory=dict)


def set_seed(seed: int) -> None:
    """random·numpy·torch 시드를 고정한다.

    CUDA의 grid_sample 역전파는 결정적이지 않을 수 있어 완전 재현은 보장하지 않는다 (확인 필요).
    """
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False


def _seed_worker(worker_id: int) -> None:
    """DataLoader 작업자마다 numpy·random 시드를 torch 시드에서 이어받는다."""
    s = torch.initial_seed() % 2 ** 32
    np.random.seed(s)
    random.seed(s)


def checkpoint_dir(run_id: str) -> Path:
    """체크포인트 폴더. 환경 변수 CROWDSIGHT_CKPT_DIR(기본 ~/crowdsight_ckpt) 아래이며 저장소 밖이어야 한다."""
    root = Path(os.environ.get("CROWDSIGHT_CKPT_DIR", Path.home() / "crowdsight_ckpt"))
    path = (root / run_id).resolve()
    if REPO_ROOT == path or REPO_ROOT in path.parents:
        raise ValueError("체크포인트를 저장소 안에 둘 수 없다")
    path.mkdir(parents=True, exist_ok=True)
    return path


class FramePairDataset(Dataset):
    """영상에서 (t, t + frame_gap) 프레임 쌍과 보행 영역 마스크를 읽는다. 프레임을 디스크에 따로 저장하지 않는다."""

    def __init__(self, cfg: FinetuneConfig) -> None:
        """영상별 시작 프레임 번호를 시드 고정으로 미리 뽑는다."""
        rng = np.random.default_rng(cfg.seed)
        self._cfg = cfg
        self._items: list[tuple[str, int]] = []
        for path in cfg.train_videos:
            cap = cv2.VideoCapture(path)
            n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            cap.release()
            starts = rng.integers(0, max(1, n - cfg.frame_gap), size=cfg.pairs_per_video)
            self._items += [(path, int(s)) for s in starts]

    def __len__(self) -> int:
        """프레임 쌍 수."""
        return len(self._items)

    def __getitem__(self, i: int) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        """(img1 uint8 (3, h, w), img2 uint8 (3, h, w), 영역 마스크 float (1, h, w))를 돌려준다."""
        path, start = self._items[i]
        cap = cv2.VideoCapture(path)
        cap.set(cv2.CAP_PROP_POS_FRAMES, start)  # 코덱별 탐색 정확도 (확인 필요)
        ok1, f1 = cap.read()
        for _ in range(self._cfg.frame_gap - 1):
            cap.grab()
        ok2, f2 = cap.read()
        cap.release()
        if not (ok1 and ok2):
            return self[(i + 1) % len(self)]
        h, w = self._cfg.work_hw
        mask = cv2.imread(self._cfg.region_masks[path], cv2.IMREAD_GRAYSCALE)
        f1, f2 = cv2.resize(f1, (w, h)), cv2.resize(f2, (w, h))
        mask = cv2.resize(mask, (w, h), interpolation=cv2.INTER_NEAREST) > 0

        # 무작위 자르기·좌우 뒤집기·밝기 대비: 두 프레임에 같게 적용한다. 움직임은 늘지 않는다.
        ch, cw = self._cfg.crop_hw
        y0 = np.random.randint(0, h - ch + 1)
        x0 = np.random.randint(0, w - cw + 1)
        f1, f2 = f1[y0:y0 + ch, x0:x0 + cw], f2[y0:y0 + ch, x0:x0 + cw]
        mask = mask[y0:y0 + ch, x0:x0 + cw]
        if np.random.rand() < 0.5:
            f1, f2, mask = f1[:, ::-1], f2[:, ::-1], mask[:, ::-1]
        gain, bias = np.random.uniform(0.8, 1.2), np.random.uniform(-20, 20)
        f1 = np.clip(f1 * gain + bias, 0, 255).astype(np.uint8)
        f2 = np.clip(f2 * gain + bias, 0, 255).astype(np.uint8)

        def to_t(img: np.ndarray) -> torch.Tensor:
            rgb = cv2.cvtColor(np.ascontiguousarray(img), cv2.COLOR_BGR2RGB)
            return torch.from_numpy(rgb).permute(2, 0, 1).contiguous()

        m = torch.from_numpy(np.ascontiguousarray(mask)).float().unsqueeze(0)
        return to_t(f1), to_t(f2), m


def _freeze_batchnorm(model: torch.nn.Module) -> None:
    """배치 크기가 작으므로 BatchNorm 통계를 고정한다 (가정). RAFT 안 BatchNorm 위치는 (확인 필요)."""
    for mod in model.modules():
        if isinstance(mod, torch.nn.BatchNorm2d):
            mod.eval()


def train(cfg: FinetuneConfig, out_root: Path = REPO_ROOT / "outputs" / "flow") -> Path:
    """비지도 추가 학습을 돌리고 마지막 체크포인트 경로를 돌려준다."""
    if set(cfg.train_videos) & set(cfg.eval_videos):
        raise ValueError("학습·평가 영상이 겹친다 (기획 3.1)")
    set_seed(cfg.seed)
    weights = Raft_Large_Weights.DEFAULT if cfg.size == "large" else Raft_Small_Weights.DEFAULT
    model = (raft_large if cfg.size == "large" else raft_small)(weights=weights).to(cfg.device)
    model.train()
    _freeze_batchnorm(model)
    preprocess = weights.transforms()
    opt = torch.optim.AdamW(model.parameters(), lr=cfg.lr, weight_decay=cfg.weight_decay)

    gen = torch.Generator()
    gen.manual_seed(cfg.seed)
    loader = DataLoader(
        FramePairDataset(cfg), batch_size=cfg.batch_size, shuffle=True,
        num_workers=cfg.num_workers, worker_init_fn=_seed_worker,
        generator=gen, drop_last=True,
    )
    run_dir = out_root / "runs" / cfg.run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "config.json").write_text(
        json.dumps(asdict(cfg), ensure_ascii=False, indent=2), encoding="utf-8",
    )
    ckpt_dir = checkpoint_dir(cfg.run_id)
    log_f = open(run_dir / "train_log.csv", "w", newline="", encoding="utf-8")
    log = csv.writer(log_f)
    log.writerow(["step", "loss", "photo", "smooth", "lr", "elapsed_s"])

    step, t0, last = 0, time.time(), ckpt_dir / "step000000.pth"
    while step < cfg.max_steps:
        for img1, img2, region in loader:
            a, b = preprocess(img1, img2)  # [-1, 1]
            a, b, region = a.to(cfg.device), b.to(cfg.device), region.to(cfg.device)
            f12s = model(a, b, num_flow_updates=cfg.iters)
            f21s = model(b, a, num_flow_updates=cfg.iters)
            loss, terms = sequence_unsup_loss(
                f12s, f21s, (a + 1) / 2, (b + 1) / 2, region,
                w_smooth=cfg.w_smooth, gamma=cfg.gamma, kind=cfg.photo_loss,
            )
            opt.zero_grad(set_to_none=True)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), cfg.clip_grad)
            opt.step()
            step += 1
            log.writerow([step, float(loss.detach()), terms["photo"], terms["smooth"],
                          cfg.lr, round(time.time() - t0, 1)])
            if step % cfg.save_every == 0 or step == cfg.max_steps:
                last = ckpt_dir / f"step{step:06d}.pth"
                torch.save(model.state_dict(), last)  # 가중치만 저장, 저장소 밖
                log_f.flush()
            if step >= cfg.max_steps:
                break
    log_f.close()
    return last


if __name__ == "__main__":
    import sys

    raw = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    for key in ("work_hw", "crop_hw"):
        if key in raw:
            raw[key] = tuple(raw[key])
    print(train(FinetuneConfig(**raw)))
```

- 학습 중 노이즈 바닥 조기 중단(기획 4.3)은 루프 안에 넣지 않는다. 대신 `save_every`마다 체크포인트를 남기고, `eval_flow.py`로 체크포인트별 노이즈 바닥을 잰다. 루프를 단순하게 두기 위해서다 (가정).
- 보행 영역 마스크가 정지 배경을 다 빼지 못하면 0 흐름 학습이 남는다. 그때는 밀도 기반 마스크를 검토한다 `[토론]`.

### 5.8 `timeline.json` 흐름 필드 (`src/flow/timeline_flow.py`)

```python
"""셀 통계를 timeline.json 흐름 필드로 바꾼다. 필드 이름은 기획 2.2 후보이며 [토론]이다."""
from __future__ import annotations

import math

import numpy as np

from src.flow.cells import CellFlow


def _num(x: float, nd: int = 4) -> float | None:
    """NaN·무한대는 None(JSON null)으로, 나머지는 반올림한다."""
    return None if not math.isfinite(float(x)) else round(float(x), nd)


def build_flow_cells(
    cell_names: list[str],
    cf: CellFlow,
    s: np.ndarray,
    rho: np.ndarray | None,
    min_pixels: int = 200,
) -> list[dict]:
    """한 시점의 셀 레코드 목록을 만든다. 셀·구역 집계값만 담는다.

    유효 픽셀이 min_pixels(가정)보다 적은 셀은 흐름 값을 비운다 (난류 조사 6.3 A2).
    """
    out = []
    for i, name in enumerate(cell_names):
        ok = cf.count[i] >= min_pixels
        si = s[i] if ok else float("nan")
        pi = rho[i] * si if (ok and rho is not None) else float("nan")
        out.append({
            "cell_id": name,
            "flow_vx": _num(cf.mean_v[i, 0]) if ok else None,      # m/s
            "flow_vy": _num(cf.mean_v[i, 1]) if ok else None,      # m/s
            "flow_instability": _num(si, 5),                       # m²/s²
            "flow_pressure": _num(pi, 5),                          # 1/s²
            "flow_counterflow": _num(cf.counterflow[i], 3) if ok else None,
            "flow_quality": int(cf.count[i]),                      # 유효 픽셀 수
        })
    return out
```

- 출력 예 (가정). 전체 `timeline.json` 구조는 팀 규격을 따른다. 흐름 모듈은 `cells` 안의 흐름 필드만 채운다.

```json
{
  "zone_id": "zone-01",
  "camera_id": "cam-01",
  "rate_hz": 1,
  "flow_estimator": "raft_small-pretrained-...",
  "seconds": [
    {
      "t": 30,
      "cells": [
        {"cell_id": "r03c05", "flow_vx": 0.412, "flow_vy": -0.051,
         "flow_instability": 0.00731, "flow_pressure": 0.02193,
         "flow_counterflow": 0.042, "flow_quality": 1834}
      ]
    }
  ]
}
```

- `flow_estimator`를 셀마다 넣지 않고 파일 머리에 한 번 넣는다 (가정). 기획 2.2는 필드로만 적었다 `[토론]`.
- JSON 저장은 `json.dumps(..., allow_nan=False)`로 한다. `NaN`이 남아 있으면 오류로 바로 알 수 있다.

### 5.9 영상 분석 진입점 (`src/flow/run_flow.py`, 핵심 부분)

```python
"""영상 1개를 1Hz로 분석해 흐름 타임라인 레코드를 만든다. 흐름장은 파일로 남기지 않는다."""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from src.flow.cells import TemporalInstability, reduce_to_cells
from src.flow.estimators import FlowEstimator
from src.flow.ground import ground_velocity
from src.flow.timeline_flow import build_flow_cells


def analyze_video(
    video_path: Path,
    estimator: FlowEstimator,
    cell_index: np.ndarray,
    cell_names: list[str],
    h_vel: np.ndarray,
    gap_frames: int,
    rho_series: np.ndarray | None = None,
    noise_var: np.ndarray | None = None,
    window_s: float = 30.0,
) -> list[dict]:
    """초마다 (t초 프레임, t초 + gap 프레임) 쌍의 흐름을 셀 통계로 줄여 레코드 목록을 돌려준다.

    rho_series는 counting 출력 (T, n_cells) EMA 밀도다. 없으면 압력은 null이다.
    """
    cap = cv2.VideoCapture(str(video_path))
    fps = cap.get(cv2.CAP_PROP_FPS)
    if gap_frames >= fps:
        raise ValueError("gap_frames는 1초 프레임 수보다 작아야 한다")
    n_cells = len(cell_names)
    mask = cell_index >= 0
    ids = cell_index[mask]  # np.nonzero(mask)와 같은 행 우선 순서
    tracker = TemporalInstability(n_cells, window_s=window_s, noise_var=noise_var)

    records: list[dict] = []
    t, start, frame_no, prev = 0, 0, -1, None
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        frame_no += 1
        if frame_no == start:
            prev = frame
        elif frame_no == start + gap_frames and prev is not None:
            flow = estimator.estimate(prev, frame)
            vel = ground_velocity(flow, h_vel, gap_frames / fps, mask)
            del flow  # 흐름장은 여기서 버린다
            cf = reduce_to_cells(ids, vel, n_cells)
            s, _ = tracker.update(cf.mean_v)
            rho = None if rho_series is None or t >= len(rho_series) else rho_series[t]
            records.append({"t": t, "cells": build_flow_cells(cell_names, cf, s, rho)})
            t += 1
            start, prev = int(round(t * fps)), None
    cap.release()
    return records
```

- 노이즈 바닥 측정을 위해 `V_c` 시계열(셀 집계값)도 함께 모아 `eval_flow.py`에 넘긴다. 집계값이므로 저장 규칙에 맞다.
- `ground_velocity`는 매번 `g0`를 다시 계산한다. 느리면 `g0`를 미리 계산해 넘긴다 (가정). 처음에는 단순하게 둔다.

### 5.10 G1 판정 (`src/flow/eval_flow.py`, 핵심 부분)

```python
"""추정기별 중간 1·2 지표를 모아 G1 판정을 낸다 (기획 5.2)."""
from __future__ import annotations


def g1_decision(
    ft: dict[str, float], pre: dict[str, float], mae_tol: float = 0.0,
) -> tuple[bool, str]:
    """추가 학습(ft)과 사전학습 RAFT(pre)의 지표로 채택 여부와 근거를 돌려준다.

    조건 1: 노이즈 바닥 중앙값이 더 낮다.
    조건 2: 흐름 외삽 MAE가 사전학습 대비 mae_tol 비율 이상 나빠지지 않는다.
    개선 폭 수치 기준(mae_tol 등)은 [토론]이다 (기획 9장 11번).
    """
    c1 = ft["noise_floor_median"] < pre["noise_floor_median"]
    c2 = ft["mae_advect"] <= pre["mae_advect"] * (1.0 + mae_tol)
    reason = (
        f"noise {ft['noise_floor_median']:.5f} vs {pre['noise_floor_median']:.5f}, "
        f"mae_advect {ft['mae_advect']:.4f} vs {pre['mae_advect']:.4f}"
    )
    return c1 and c2, reason
```

---

## 6. GPU 서버 실행 방법

### 6.1 환경 준비

- 패키지는 승인 후에만 설치한다 (CLAUDE.md). 버전은 승인 때 정한다 `[토론]`.
- `torch`·`torchvision` 버전은 서버 CUDA 드라이버와 맞아야 한다. 서버 사양은 (확인 필요)다. P2PNet과 같은 버전을 공유하는 것이 좋다 (모델 조사 5.3, 가정).
- 순서 (예시, bash):

```bash
git clone <저장소 주소> ~/Triple-Y && cd ~/Triple-Y
git switch feat/<브랜치 이름>
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt   # 승인된 패키지만 들어 있어야 한다
nvidia-smi                        # GPU·드라이버 확인
python -c "import torch, torchvision; print(torch.__version__, torchvision.__version__, torch.cuda.is_available())"
```

- 데이터는 저장소 밖 폴더(예: `~/crowdsight_data/`)에 둔다. 설정 파일의 영상 경로가 이 폴더를 가리킨다.
- 학습용 원본을 GPU 서버에 두는 범위·기간은 팀이 정한다 (기획 9장 8번) `[토론]`.
- AI Hub 데이터는 이용 조건 확인 후에만 서버로 옮긴다 (기획 9장 9번) (확인 필요).

### 6.2 백그라운드 실행

- 접속이 끊겨도 학습이 계속되도록 `tmux` 또는 `nohup`을 쓴다.

```bash
# tmux
tmux new -s flowft
export CROWDSIGHT_CKPT_DIR=~/crowdsight_ckpt
python -m src.flow.finetune src/flow/configs/finetune_v1.json 2>&1 | tee ~/crowdsight_logs/finetune_v1.out
# 분리: Ctrl-b d, 다시 붙기: tmux attach -t flowft

# 또는 nohup
mkdir -p ~/crowdsight_logs
CROWDSIGHT_CKPT_DIR=~/crowdsight_ckpt nohup python -m src.flow.finetune \
    src/flow/configs/finetune_v1.json > ~/crowdsight_logs/finetune_v1.out 2>&1 &
```

- 진행 확인: `tail -f outputs/flow/runs/<run_id>/train_log.csv`, `nvidia-smi`.
- 학습이 도는 동안 Spring Boot 작업을 병행한다 (기획 6장, 가정).

### 6.3 재현성

- 설정 파일 `config.json`에 시드·데이터 목록·하이퍼파라미터를 모두 남긴다.
- 실행 직전에 `git rev-parse HEAD`, `pip freeze`, `nvidia-smi --query-gpu=name --format=csv`를 `runs/<run_id>/env.txt`에 남긴다.
- 커밋하지 않은 수정이 있으면 학습을 시작하지 않는다 (가정). 결과와 코드 버전을 맞추기 위해서다.
- 같은 설정으로 2회 돌려 손실 곡선이 비슷한지 한 번 확인한다. 완전 일치는 기대하지 않는다 (5.7 `set_seed` 주석).

### 6.4 가져오는 것과 가져오지 않는 것

| 가져온다 (git 커밋 가능) | 가져오지 않는다 |
|---|---|
| `outputs/flow/runs/<run_id>/` 안 `config.json`, `env.txt`, `train_log.csv` | 원본 영상, 잘라낸 프레임 |
| `outputs/flow/eval/` 안 CSV, `g1_decision.csv`, `runs.csv` | 체크포인트 `*.pth` (git 제외. 로컬에 필요하면 저장소 밖 경로로 받는다) |
| 흐름 타임라인 JSON (셀·구역 집계값) | 흐름장, 머리 좌표, 개인 궤적 |
| | `~/crowdsight_logs/*.out` (필요한 수치는 CSV로 옮긴다) |

- 결과 회수 예: `rsync -av server:~/Triple-Y/outputs/flow/ ./outputs/flow/ --exclude "*.pth"`.

---

## 7. 평가 실행

### 7.1 공통 조건

- 평가 영상 목록은 학습 영상과 영상 단위로 겹치지 않는다. `train()`과 `eval_flow.py`가 모두 검사한다.
- 모든 추정기를 같은 영상·같은 셀 번호표·같은 창(T = 30초, 가정)·같은 프레임 간격으로 돌린다.
- 비교 대상: Farneback, DIS, 사전학습 RAFT, 추가 학습 RAFT(체크포인트별).

### 7.2 중간 1·2 계산

| 지표 | 계산 | 출력 |
|---|---|---|
| 중간 1 노이즈 바닥 | `run_flow`로 `V_c` 시계열 → 정지 표시 표본(5.4) → `measure_noise_floor` → `summarize_noise_floor` | `eval/<estimator>/noise_floor.csv`, 중앙값·p90 |
| 중간 2 기준선 | counting의 `rho*_c` 시계열(고정본)과 추정기별 `V_c` 시계열 → `baseline_errors` (T = 60초, 가정) | `eval/<estimator>/baseline.csv`, `mae_persist`, `mae_advect`, `skill_advect` |
| 보조 (가능하면) | Jülich 궤적 대비 셀 속도 오차 (난류 조사 V3) | 범위 밖. 시간이 남으면 따로 계획 |

- 노이즈 바닥만 보면 흐름을 전부 0으로 내는 모델이 이긴다. 그래서 중간 2를 함께 본다 (기획 5.2 조건 2).
- 추가 확인 (가정): 움직이는 셀의 평균 속력이 사전학습 대비 크게 줄지 않았는지 같이 적는다. 과도한 평활을 잡기 위해서다.

### 7.3 G1 판정표 (`outputs/flow/g1_decision.csv`)

| 열 | 내용 |
|---|---|
| `estimator` | 추정기 이름 (`flow_estimator`와 같은 문자열) |
| `ckpt_step` | 추가 학습이면 체크포인트 step |
| `noise_floor_median`, `noise_floor_p90` | 중간 1 [m²/s²] |
| `mae_persist`, `mae_advect`, `skill_advect` | 중간 2 [명/㎡] |
| `moving_speed_ratio` | 움직이는 셀 평균 속력 / 사전학습 RAFT 값 (가정) |
| `adopt` | `g1_decision` 결과 (추가 학습 행만) |
| `reason` | 근거 수치 문자열 |

- 판정 대상은 사전학습 RAFT 대비 추가 학습 RAFT다 (기획 5.2).
- 불채택이면 사전학습 추정기 중 노이즈 바닥과 `mae_advect`가 가장 나은 것을 고정한다. 둘이 엇갈리면 팀이 정한다 `[토론]`.

### 7.4 정답 고정 규칙 (기획 2.3)

- 주 정답은 `rho*_c(t + T)`다. counting 출력 파일 한 버전을 고정하고 파일 이름·커밋을 `runs.csv`의 `note`에 적는다.
- 불안정 지표를 정답으로 쓸 때는 고정 기준 추정기(사전학습 RAFT 또는 Farneback) 하나로 계산한 `S_c`만 쓴다. 어느 것을 기준으로 할지는 `[토론]`이다.
- 흐름 추정기만 바꾼다. 셀 격자, 창 길이, 프레임 간격, 시계열 모델, 시드는 고정한다.
- 평가 코드는 정답 시계열을 추정기 결과에서 다시 계산하지 않는다. 고정 파일에서 읽기만 한다.

---

## 8. 구현 위험과 대비책

| 위험 | 내용 | 대비 |
|---|---|---|
| 패키지 승인 지연 | `torch`·`torchvision`이 없으면 RAFT 단계가 막힌다 | Farneback·DIS 경로는 `torch` 없이 돈다 (5.1). G0는 Farneback만으로도 완료 조건을 채운다 |
| GPU 메모리 부족 | 양방향 × 12반복 × census 49채널 | `raft_small`, 자르기 368×496, 배치 2에서 시작. 부족하면 마지막 반복만 손실, 자르기 축소 |
| 0 흐름 붕괴 | 정지 배경이 손실을 지배한다 | 영역 마스크, 7.2 움직이는 셀 속력 확인, 낮은 학습률 |
| 망각 | 사전학습 성능이 무너진다 | `lr = 1e-5`, 짧은 `max_steps`, 체크포인트별 노이즈 바닥 비교 |
| 프레임 탐색 부정확 | 일부 코덱에서 `CAP_PROP_POS_FRAMES` 위치가 어긋난다 (확인 필요) | 학습 쌍은 간격만 맞으면 된다. 분석(`run_flow`)은 순차 읽기를 쓴다 |
| 셀 격자 불일치 | counting과 flow의 셀이 다르면 `P_c = rho* × S` 가 틀린다 | `infra/`의 같은 설정을 읽는다. S3 통합 시험에 counting 셀 번호 비교를 넣는다 |
| 호모그래피 평면 | 바닥 H로 머리 높이 흐름을 바꾸면 척도가 틀린다 | 속도용 H를 인자로 분리 (5.2). 평면 선택은 `[토론]` |
| 머리 점 주변 픽셀 | `proposal-detail.md` 3.4(2)는 머리 점 주변 픽셀만 쓰라고 한다. 그러나 AI 모듈끼리는 `timeline.json`(집계값)으로만 주고받는다 | 지금은 보행 영역 마스크만 쓴다. 분석 스크립트 안에서 메모리로 머리 점을 넘길지는 `[토론]` |
| 재현성 | CUDA 비결정 연산 | 시드 고정 + 2회 실행 확인. 완전 일치는 요구하지 않는다 |
| 개인정보 | 디버깅 중 흐름장·프레임 저장 유혹 | 코드에 흐름장 저장 함수를 두지 않는다. S11에서 출력 폴더에 큰 배열 파일이 없는지 검사 |
| 일정 | 서버 작업과 겹친다 | G1에서 학습을 끊는다. 학습은 백그라운드로 돌린다 |

---

## 9. 남은 결정 `[토론]`

| 번호 | 내용 | 기획 9장 |
|---|---|---|
| D1 | 학습 모델을 MVP에 넣는 범위 변경 | 1번 |
| D2 | 흐름·예측 모듈 경계. 흐름 타임라인 전달 방식 | 2번 |
| D3 | `timeline.json` 흐름 필드 이름·주기, `flow_estimator` 위치(파일 머리 vs 셀) | 3번 |
| D4 | 정답 고정. 불안정 정답용 기준 추정기 선택 | 4번 |
| D5 | 지표 정의 변경(시간 분산, 잡음 빼기, 0.02/s² 참고선) | 5번 |
| D6 | E5 목표 변경 | 6번 |
| D7 | `torch`·`torchvision` 추가 승인과 버전. `numpy`·`opencv-python`·`pytest`도 함께 | 7번 |
| D8 | 학습용 원본 영상의 GPU 서버 보관 범위·기간 | 8번 |
| D9 | AI Hub 이용 조건 확인 담당 | 9번 |
| D10 | `references.md` [66] 깨진 링크 처리 | 10번 |
| D11 | G1 개선 폭 수치 기준(`mae_tol` 등) | 11번 |
| D12 | 테스트 폴더 위치(`tests/flow/`)와 도구(`pytest` 또는 `unittest`) | 이 문서 |
| D13 | 3장 seam 목록 확정 | 이 문서 |
| D14 | 속도 변환 평면(바닥 vs 머리 높이), 셀 격자·호모그래피 공유 형식 (`infra/`, 이유노 님과) | 이 문서 (난류 조사 C3) |
| D15 | 노이즈 바닥 "정지" 표시 방법 (밀도 기준 vs 수동 구간) | 이 문서 |
| D16 | 머리 점 주변 픽셀 마스크 사용 여부 | 이 문서 |
| D17 | 학습 영역 마스크(보행 영역 vs 밀도 기반) | 이 문서 |

### (확인 필요) 모음

- torchvision 가중치 열거형의 문자열 표기 (`f"{weights}"` 결과).
- RAFT 내부 BatchNorm 위치와 학습 모드 영향.
- CUDA `grid_sample` 역전파의 비결정성.
- census·Charbonnier·앞뒤 일치 상수의 출처값 (UFlow·UnFlow 원문).
- UFlow가 가장 낫다고 보고한 광도 손실 종류.
- OpenCV `CAP_PROP_POS_FRAMES` 탐색 정확도 (코덱별).
- DIS 프리셋과 TUB CrowdFlow DIS4·DIS2 대응.
- GPU 서버 사양(CUDA 드라이버, VRAM), 외부 접속(가중치 자동 내려받기) 가능 여부.
- AI Hub 데이터 이용 조건.
- `src/` 패키지 실행 방식(`python -m src.flow.xxx`)이 팀 import 규칙과 맞는지.
