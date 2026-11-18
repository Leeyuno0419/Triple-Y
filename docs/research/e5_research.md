# E5 조사: 불안정 지표 시계열·기준값 민감도·유입과 인원 증가 시간 차

| 항목 | 내용 |
|---|---|
| 작성일 | 2026-11-16 |
| 작성 | Researcher 서브에이전트 (조영준 요청) |
| 기준 커밋 | `f0236fb` (`main` = `origin/main` = `feat/flow-e5`, 열린 PR 없음) |
| 범위 | `docs/proposal.md` E5의 MVP 3항목: (1) 불안정 지표 P 시계열, (2) 서버 기준값 민감도, (3) 유입 → 인원 증가 시간 차 (`docs/proposal.md:51-52`, `:126-127`, `:136`, `:316`) |
| 범위 밖 | 정답 클립 라벨, ROC, 재현율 ≥ 0.8, E7 절제 실험 (`docs/proposal-detail.md:86`, `:310`, `:883`, `:885`의 옛 설계) |

- 표기는 `docs/proposal-guide.md` 3절을 따른다. `(가정)` 설계값, `[토론]` 팀 합의 필요, `(확인 필요)` 검증 못함, `(계산)` 이 문서에서 직접 계산한 값, `(추론)` 자료로 미루어 본 판단.
- 코드는 읽기만 했다. 직접 돌린 것: `build_cells`로 E04_039 셀 계산, `outputs/` CSV 요약, 로컬 영상 헤더 읽기, Farneback 1쌍 시간 측정, `pytest tests/flow -m "not slow"`. 파일은 이 문서만 썼다.

---

## 0. 요약

1. **E5는 지금 바로 돌릴 수 없다.** 흐름 필드(`pressure`, `inflow_ratio`)가 채워진 실제 E04_039 타임라인이 어디에도 없다. 로컬에는 E04_039 영상, P2PNet 가중치, P2PNet 공식 코드, `scipy`가 없다 (A.1).
2. **흐름 모듈은 실제 영상으로 한 번도 돌지 않았다.** `run_flow.analyze_video`는 CLI가 없고 머리 점 `heads`를 메모리로 받아야 한다. 이것을 넘길 통합 스크립트(결정 8)는 아직 없다 (A.2, A.3).
3. **실행 시간 추정**: 이 PC에서 1080p Farneback 1쌍이 약 1.0초다. 180초 영상의 흐름 계산은 약 3분이다. 머리 점만 따로 구하면(180장) 전체 약 5분이다 (추정, A.4).
4. **`fake_timeline.py`는 E5에 못 쓴다.** 밀도·흐름이 합성값이고, E04_039 셀 구성도 실제와 다르다 (A.5).
5. **실제 E04_039 셀은 12개다.** 왼쪽 열은 4.0·4.0·4.0·2.6㎡로 모두 판정 대상이고, 2㎡ 미만은 오른쪽 열 4개다. api-spec 10절 17번의 걱정(왼쪽 열 1.0~1.2㎡)은 가짜 셀 기준이다 (A.6, H).
6. **서버 규칙은 Python으로 다시 구현하길 권한다.** 서버 JUnit 시험 사례를 pytest로 옮겨 어긋남을 막는다 (D.8).
7. **"유입이 약 20~25초 앞섰다"는 재현 근거가 없다.** 11-06 기획서 v3.0 문서 커밋에서 처음 나왔다. 그때는 흐름 코드가 없었고, 노트북·PR·문서에 측정 방법이 없다 (F.1).
8. **지금 정의로는 유입 선행을 보기 어려울 수 있다 (추론).** E04_039 경계 셀은 화면 아래 줄 3개뿐이다. 수작업 정답에서 사람은 `c-0100`에 먼저 차고 경계 셀 `c-0000`은 나중에 찬다. 또 `count` ≥ 3이 t=47에야 처음 나와서, 서버 유입 경보는 그 전에 켜질 수 없다 (F.4).

---

## A. 입력 데이터

### A.1 로컬에 있는 것과 없는 것

| 필요한 것 | 경로 (코드 기준) | 로컬 상태 | 근거 |
|---|---|---|---|
| E04_039 영상 | `data/processed/g1/E04_039.mp4` (실행 예시) | **없음**. PC 전체(Desktop·Downloads·Documents·Videos)에서 찾지 못함 | `src/counting/run_density.py:3-4` |
| 원본 zip | `data/raw/aihub_71850/.../TS_인파밀집_할로윈데이_포함_금.zip` | 있음. 안에는 `E05_035`~`E05_038.mp4` 4개뿐 (압축은 풀지 않고 목록만 봄) | zip 목록 |
| E05_035 영상 | `data/raw/aihub_71850/halloween_fri/E05_035.mp4` | 있음. 30 fps, 1847프레임, 1920×1080 | `cv2` 헤더 |
| E04_022 영상 | 저장소 밖 `Desktop/project/E04_022.mp4` | 있음 (호모그래피 사전 검증용, 분석 대상 아님) | `docs/timeline-spec.md:21` |
| P2PNet 가중치 | `data/raw/weights/SHTechA.pth` | **없음** | `src/counting/eval_e1.py:30` |
| P2PNet 공식 코드 | `third_party/CrowdCounting-P2PNet` | **없음** (git 제외 폴더) | `src/counting/eval_e1.py:28`, `.gitignore` |
| `scipy` | `eval_e1.py`가 모듈 첫머리에서 import | `crowdsight` 환경에 **없음**. 그래서 `run_density`도 import가 안 된다 | `src/counting/eval_e1.py:20`, PR #36 본문("`run_density` import가 scipy를 요구") |
| 구역 설정 | `infra/homography/E04_039.json` | 있음 (`head_plane`, `cell_origin_m`, `counter`) | `infra/homography/E04_039.json:89`, `:173`, `:178-183` |
| E05_035 구역 설정 | `infra/homography/E05_035.json` | **없음** (어느 브랜치에도 없음) | `git log --all -- infra/homography/E05_035.json` 결과 없음 |
| 밀도 타임라인 | `data/processed/timeline/E04_039.json` | **없음**. `data/processed/`에는 `.gitkeep`뿐 | `server/src/main/resources/application.yml:12-13`, PR #29 본문("git 밖, 따로 전달") |
| 초별 구역 인원 | `outputs/g1/E04_039_counts.csv` | 있음. t=0~179, `zone_count`(5장 평균)·`frame_count` | `src/counting/run_density.py:125-128`, 커밋 `54849d2` |
| E2 수작업 정답 | `outputs/e2/E04_039_gt.csv` | 있음. 30프레임(6초 간격), 셀별 인원 | |
| RAFT 가중치 | torch hub 캐시 `raft_small_C_T_V2-01064c6d.pth` | 있음 (MVP는 Farneback이라 불필요) | `docs/proposal.md:147` |

- 팀장이 가진 실제 타임라인도 흐름 필드가 비어 있다. 예측 모듈 주석에 "E04_039 에서 실제로 발생: meta.models.flow='none'"이 있다 (`src/predict/model.py:91`).
- PR #36의 남은 이슈: "실제 영상(E04_039)으로 확인하지 않음 … 영상과 P2PNet 가중치 `SHTechA.pth`를 받은 뒤 확인". 그 뒤 댓글은 없다.

### A.2 실제 E04_039 타임라인을 만드는 경로

1. **인원·밀도** `python -m src.counting.run_density --homography infra/homography/E04_039.json --video <영상> --out data/processed/timeline/E04_039.json [--limit N]` (`src/counting/run_density.py:3-4`, `:45-50`).
    - 셀: `build_cells(H_img_to_ground, walkable_polygon_px, 영상 크기, 2.0, origin_m=cell_origin_m)` (`:55`, `:67`).
    - 초마다 t−0.4~t+0.4초 5장(`counter.avg_frames` 5, `window_s` 0.4)에서 머리를 세고 평균한다 (`:58`, `:71-74`). 머리는 `head_plane.H_head_img_to_ground`로 바닥에 옮긴다 (`:54`, `:88`).
    - 출력: `density`(2자리), `count`(2자리). 흐름·예측 필드는 모두 `null`이다 (`:100-104`).
    - 부산물: `outputs/g1/{video}_counts.csv`를 덮어쓴다 (`:125-128`).
2. **흐름** `src.flow.run_flow.analyze_video(video, timeline_in, timeline_out, estimator, *, heads, h_head, cell_origin_m, gap_frames=1, noise_var=None, window_s=30.0, min_heads=1, patch_radius_px=6, inflow_min_heads=0)` (`src/flow/run_flow.py:55-70`).
    - CLI(`__main__`)가 없다. 라이브러리 함수다.
    - `heads[t]`는 프레임 `round(t·fps)`의 머리 점 (N, 2) px다. 파일에 저장하지 않고 같은 프로세스에서 메모리로 넘겨야 한다 (`:73-76`, `docs/timeline-spec.md:193`).
    - `h_head`·`cell_origin_m`은 `load_head_plane(infra/homography/E04_039.json)`으로 읽는다 (`src/flow/run_flow.py:29`).
    - 흐름 필드(`vx`, `vy`, `speed_var`, `pressure`, `inflow_ratio`)만 채우고 같은 파일에 원자적으로 다시 쓴다.
3. **예측**은 E5에 필요 없다 (`density_pred_60s`는 E5가 쓰지 않는다).

### A.3 통합 스크립트(결정 8)가 필요한가

- 결정 8: 밀도+흐름+예측을 timeline 하나로 합치는 통합 분석 스크립트는 이유노 담당이다 (`docs/decisions-2026-11-11.md:17`). 저장소와 원격 브랜치에 아직 없다.
- 연결 방법 초안: 밀도 반복문에서 가운데 장(offset 0)의 머리를 `heads[t]`로 모아 `analyze_video`에 넘긴다 (`docs/plans/flow_head_plane_impl_plan.md:296-307`). 가운데 장 프레임 번호 `round((t+0)·fps)`는 흐름 시작 프레임 `round(t·fps)`와 같다 (`src/counting/run_density.py:74`, `src/flow/run_flow.py:203`).
- **E5 자체는 통합 스크립트가 없어도 된다.** E5는 흐름 필드가 채워진 timeline 파일만 있으면 된다. 만드는 길은 셋이다.

| 길 | 하는 일 | 필요한 것 | 장단점 |
|---|---|---|---|
| 가. F4-2를 기다림 | 이유노의 통합 스크립트로 `E04_039.json` 생성 | 이유노 일정 | 서버·G2와 같은 파일. 일정 의존 |
| 나. 밀도 timeline을 받고 흐름만 돌림 | 이유노가 가진 밀도 `E04_039.json`을 받는다. E5용 작은 진입점이 프레임 `round(t·fps)`만 P2PNet으로 세어 `heads`를 만들고 `analyze_video` 호출 | 영상, 밀도 timeline, 가중치, P2PNet 코드, `scipy` | P2PNet 180장만. 머리 세는 코드가 `run_density` 반복문과 일부 겹친다 (`head_points`는 import해서 씀) |
| 다. 밀도·흐름을 E5가 다 돌림 | 위 + `run_density`도 직접 실행 | 가와 같은 입력 | 가장 느림. `outputs/g1/E04_039_counts.csv`를 덮어쓴다 (`run_density.py:125-128`) |

- 나·다는 `src/counting/`을 고치지 않고 import만 한다. 그래도 같은 일을 두 곳에서 하게 되므로 이유노와 상의가 필요하다 (CLAUDE.md "다른 사람의 폴더는 담당자와 상의").

### A.4 실행 시간 (추정)

| 단계 | 근거 | 추정 |
|---|---|---|
| Farneback 1쌍 (1920×1080) | 이 PC, `E05_035` 0·1번 프레임, `estimators.py` 시작값으로 3회: 1.047·1.038·1.005초 | 1쌍 약 1.0초 |
| 흐름 180초 영상 | 1쌍 × 180 + 디코딩(`grab` 300장 0.52초 → 5400장 약 10초) | 약 3분 (추정) |
| 밀도 패스 (P2PNet 900장) | "현재 3분 영상에 약 8분 반" (`docs/decisions-2026-11-11.md:18`, `docs/api-spec.md:272`). 팀장 PC 값 | 8.5분 |
| 머리만 (P2PNet 180장) | 위 값 ÷ 5 (장당 약 0.57초, 팀장 PC) | 약 1.7분 (추정, 이 PC는 미측정) |
| 길 나 합계 | 머리 + 흐름 | **약 5분 (추정)** |
| 길 가·다 합계 | 밀도 + 흐름 | 약 11~12분 (추정) |

- E04_039 fps는 확인하지 못했다. 같은 데이터셋의 `E05_035`·`E04_022`는 30 fps, 1920×1080이다.
- 기준값 민감도(항목 2)와 시간 차(항목 3)는 timeline만 다시 읽으므로 영상을 다시 돌리지 않는다. 기준값을 서버 설정에 둔 이유가 이것이다 (`docs/timeline-spec.md:164`).

### A.5 `fake_timeline.py`는 E5에 쓸 수 없다

- 파일은 있다. 밀도·흐름이 합성값이고 `models`가 `"synthetic"`이다 (`src/counting/fake_timeline.py:1-2`, `:213`).
- 시나리오는 E04_022 장면 기준이다 (`GATHER_PX`, 54초 시작·130초 최대, `:156-157`).
- `pressure = d × (0.003 + 0.04·crowd·near)`로 만든 값이다 (`:198-201`). 측정값이 아니다.
- `inflow_ratio = 0.1 + 0.5 × walking`이라 최대 0.6이다 (`:204`). 서버 조건은 0.6 **초과**라 가짜 파일로는 유입 경보가 켜지지 않는다 (계산, `InflowMonitor.java:38`).
- `cell_origin_m`을 쓰지 않아 E04_039 셀이 9개로 실제(12개)와 다르다 (계산, A.6).

### A.6 실제 E04_039 셀 (계산)

`build_cells(H_img_to_ground, walkable_polygon_px, (1920, 1080), 2.0, origin_m=(-0.5, -1.34))`로 계산했다. 셀 12개, 합계 35.77㎡로 PR #29 본문("셀 12개(35.8㎡)")과 같다.

| 행 \ 열 | col 0 (왼쪽 벽) | col 1 | col 2 (오른쪽) |
|---|---|---|---|
| row 3 (화면 위, 먼 쪽) | `c-0300` 2.6㎡ | `c-0301` 2.6㎡ | `c-0302` 1.17㎡ ✕ |
| row 2 | `c-0200` 4.0㎡ | `c-0201` 4.0㎡ | `c-0202` 1.8㎡ ✕ |
| row 1 | `c-0100` 4.0㎡ | `c-0101` 4.0㎡ | `c-0102` 1.8㎡ ✕ |
| row 0 (화면 아래, 가까운 쪽) | `c-0000` 4.0㎡ **경계** | `c-0001` 4.0㎡ **경계** | `c-0002` 1.8㎡ ✕ **경계** |

- ✕: 2㎡ 미만이라 구역 등급·`INSTABILITY`에서 빠진다 (`ZoneGrader.java:45`, `application.yml:23`). 판정 대상은 8개다.
- **경계**: `boundary_inward` 기준(`image_polygon`이 0·1에서 0.02 안) 경계 셀은 아래 줄 3개뿐이다. 안쪽 단위 벡터(지면 x=열, y=행)는 `c-0000` (0.55, 0.83), `c-0001` (0, 1), `c-0002` (−0.55, 0.83)이다. 즉 "유입"은 화면 아래 끝에서 화면 위(먼 쪽)로 가는 움직임만 뜻한다.
- 같은 함수를 `origin_m` 없이 부르면(가짜 timeline 방식) 셀 9개, 왼쪽 열 1.2·1.06·1.0㎡다. api-spec 10절 17번의 "1.0~1.2㎡"는 이 값이다.

---

## B. timeline 필드 (`docs/timeline-spec.md` v0.2)

| 필드 | 위치 | 단위 | 소수 | null 규칙 | 근거 |
|---|---|---|---|---|---|
| `t` | `frames[]` | 초 | 정수 | 0부터 빠짐없이 1초 간격 (`interval_s` 1) | `timeline-spec.md:117`, `:99`, `run_flow.py:115-119` 검사 |
| `count` | `frames[]` | 명 | 2자리 | 숫자 또는 null. 셀 인원 합 (작은 셀 포함 12개 전부) | `timeline-spec.md:119`, `run_density.py:101` |
| `inflow_ratio` | `frames[]` | 0~1 | 규격 4자리, **코드는 2자리** | 사람 있는 경계 셀에 움직이는 머리가 없으면 null | `timeline-spec.md:118`, `run_flow.py:82`, `:243` |
| `density` (ρ) | `cells[]` | 명/㎡ | 2자리 | null 금지 (서버가 거부) | `timeline-spec.md:127`, `:134`, `api-spec.md:190` |
| `vx`, `vy` (V) | `cells[]` | m/s | 2자리 | 사람 없음·머리 < `min_heads`·비유한이면 null | `src/flow/timeline_flow.py:64-75` (C.3) |
| `speed_var` (Var(v)) | `cells[]` | m²/s² | 4자리 | 위 + 30초 창 미충족이면 null | `timeline-spec.md:129` |
| `pressure` (P) | `cells[]` | 1/s² | 4자리 | 사람 없음(ρ=0)이면 **0**, 그 밖에 `speed_var` null이면 null | `timeline-spec.md:130`, `:141` |
| `counterflow` (B) | `cells[]` | 0~1 | 4자리 | **흐름 모듈이 쓰지 않아 늘 null** | `timeline-spec.md:131`, `src/flow/timeline_flow.py:6` |

- 분석 간격은 1초(1 Hz)다 (`timeline-spec.md:10`). 서버도 1초에 한 칸 재생한다 (`application.yml:16`).
- 규격 차이 2개:
    - `inflow_ratio` 자리수: 규격 4자리, 흐름 코드 2자리(가정) (`run_flow.py:82`, `:243`). E5 결과에는 영향이 작다(평균 기준 0.6과 비교).
    - `counterflow` 정의: 규격은 "픽셀 비율"(`timeline-spec.md:135`), 코드는 머리 표본 비율(`src/flow/cells.py:28-31`)이고 파일에 쓰지 않는다.
- `density`는 5장 평균이지만 흐름의 머리는 한 장(가운데 장)이다. 그래서 `density` > 0인데 그 초 머리가 없으면 흐름 필드가 null이다 (`run_flow.py:83-85`).

---

## C. 흐름 지표 정의 (코드)

### C.1 셀 속도 V_c

- 머리마다 반경 6 px 패치 흐름의 성분별 중앙값을 머리 높이 평면 행렬로 지면 속도(m/s)로 바꾼다 (`src/flow/ground.py:44`, `:87`; `run_flow.py:221-226`).
- 흐름은 프레임 `round(t·fps)`와 `+gap_frames`(기본 1) 쌍이다. dt = 1/fps (`run_flow.py:64`, `:203`, `:223`).
- 셀 배정은 인원 모듈 `count_cells`와 같은 식이다 (`ground.py:118`).
- `reduce_to_cells`: 셀 평균 V_c, 유효 머리 수 Q_c, 역방향 비율 B_c (`src/flow/cells.py:19-56`). B_c의 `min_speed` 0.05 m/s (가정) (`cells.py:23`, `:28-31`).

### C.2 속도 분산 Var(v) = S_c (`TemporalInstability`)

- 정의: `S_c(t) = max(<|V_c − U_c|²>_T − Var_noise_c, 0)`, U_c는 최근 T초 창 평균 (`src/flow/cells.py:59-66`, `:130-134`).
- T = 30초 (가정) (`cells.py:72`, `run_flow.py:66`). 창이 다 차기 전(첫 29번 갱신)은 NaN이다 (`cells.py:125-127`). 그래서 **`speed_var`·`pressure`는 t=0~28에 늘 null**이다 (계산).
- 창 30칸 중 유효(두 성분 유한) 표본이 `ceil(0.8 × 30)` = 24개 미만인 셀은 NaN이다 (`cells.py:75`, `:108`, `:132-133`).
- 머리 수 < `min_heads`(기본 1)인 셀은 창에 NaN으로 넣는다 (`run_flow.py:229-230`).
- **잡음 바닥은 지금 빠져 있다.** `noise_var` 기본값이 None이면 0을 뺀다 (`cells.py:84-86`, `:103-106`). `measure_noise_floor`(`src/flow/noise_floor.py:9`)는 정의만 있고, 정지 표시(`static_mask`)를 만드는 코드도 부르는 곳도 없다 (`grep` 결과). 즉 파일의 `speed_var`는 잡음 포함 원분산이다.

### C.3 군중 압력 P와 저장 규칙 (`fill_flow_fields`)

- `pressure = round(round(density, 2) × 저장된 speed_var, 4)` (`src/flow/timeline_flow.py:30-34`, `:79-81`). 서버가 비교하는 값이 이 저장값이다.
- 소수 2자리 density가 0이면 `vx`·`vy`·`speed_var` null, `pressure` 0 (`timeline_flow.py:64-68`).
- 머리 수 < `min_quality`면 네 필드 모두 null (`:69-72`). `speed_var` 비유한이면 `speed_var`·`pressure` null, 속도는 씀 (`:35-40`).
- 영상이 먼저 끝난 초·디코딩 실패 초도 같은 규칙으로 비운다 (`run_flow.py:247`, `_clear_flow`).

### C.4 경계 유입 비율 `inflow_ratio`

- 경계 셀: `image_polygon`의 점 하나라도 0·1에서 `edge_tol` 0.02 안 (가정) [토론] (`src/flow/inflow.py:3-13`, `:19-22`).
- 안쪽 방향: 경계 셀 중심 → 구역 중심(모든 셀 중심 평균) 단위 벡터 (`inflow.py:31-34` [토론]).
- 비율 = 경계 셀에서 속력 ≥ `min_speed` 0.05 m/s인 머리 중 안쪽 방향과 내적 > 0인 비율 (`inflow.py:57-63`, `:69-73`, `:102`).
- 분모 0이거나 `min_samples`(= `inflow_min_heads`, 기본 0) 미만이면 None (`inflow.py:100-101`, `run_flow.py:69`, `:240`).
- 사람 있는(소수 2자리 density > 0) 경계 셀의 머리만 쓴다 (가정) [토론] (`run_flow.py:93-95`, `:235-240`).
- 저장은 2자리 (`run_flow.py:243`).
- 이것은 **비율**이지 유량(명/초)이 아니다. 경계에 두 명이 있고 둘 다 안쪽으로 걸으면 1.0이다 (계산).

### C.5 E5가 정리할 수 있는 `(가정)`·`[토론]` (흐름 코드)

| 위치 | 내용 | E5에서 할 수 있는 것 |
|---|---|---|
| `cells.py:72`, `run_flow.py:66` | T = 30초 | 저장된 `vx`·`vy`로 T를 바꿔 S를 다시 계산해 분포 비교 (영상 재실행 불필요, C.6) |
| `cells.py:75` | 유효 비율 0.8 | `pressure` null 비율을 셀별로 보고 |
| `cells.py:84-86`, `noise_floor.py` | 잡음 바닥 미적용 | 사람 없는/정지 구간에서 분산 크기를 보고만 함. 정지 표시 규칙이 없어 MVP E5에서 적용은 어렵다 |
| `run_flow.py:64` | `gap_frames` 1 (dt = 1/30초) | 표시만. 바꾸려면 흐름 재실행. 난류 조사는 Δt 0.2초를 가정했다 (`crowd_turbulence_research.md:358`) |
| `run_flow.py:67`, `:69` | `min_heads` 1, `inflow_min_heads` 0 | null 빈도·값 튐을 보고 |
| `inflow.py:3-13`, `:31-34` | 경계 정의·안쪽 방향 | E04_039에서 경계가 아래 줄뿐임을 보고 (A.6, F.4) |
| `run_flow.py:93-95` | 사람 있는 경계 셀만 | 위와 같음 |
| `cells.py:29-31` | 주 흐름 없는 셀 B = NaN | 파일에 쓰지 않으므로 E5와 무관 |

### C.6 T 민감도를 영상 없이 다시 계산할 수 있다 (계산·추론)

- 창에 들어가는 값과 파일의 `vx`·`vy`는 같은 조건에서 null이다: 머리 < `min_heads`이면 둘 다 빠지고(`run_flow.py:229-231`, `timeline_flow.py:69-72`), density 0이면 그 초 가운데 장 머리도 0명이라 창에도 NaN이다 (추론, B 마지막 줄).
- `vx`·`vy`는 0.01 m/s로 반올림된다. 양자화 분산은 두 성분 합 2 × 0.01²/12 ≈ 1.7×10⁻⁵ m²/s²다 (계산). 기준 근처 `speed_var`(아래 D.7 예: 0.008)보다 훨씬 작다.
- 확인 방법: T=30으로 다시 계산한 값이 파일의 `speed_var`와 반올림 안에서 같은지 본다.

---

## D. 서버 규칙 (그대로 재현할 것)

### D.1 설정값 (`server/src/main/resources/application.yml:19-32`, `api-spec.md:300-313`)

| 키 | 값 | 뜻 |
|---|---|---|
| `grade.density` | caution 3.0, alert 4.0, critical 5.0 | 이상이면 그 등급 (`GradeRule.java`) |
| `grade.up-seconds` / `down-seconds` | 2 / 10 | 올림·내림 관측 수 (가정) |
| `grade.min-walkable-area-m2` | 2.0 | 판정 대상 셀 (결정 4) |
| `instability.pressure` / `seconds` | 0.02 / 3 | 초과가 3초 연속이면 불안정 (가정, E5로 조정) |
| `inflow.ratio` / `window-seconds` / `min-samples` / `off-seconds` / `min-count` | 0.6 / 5 / 3 / 10 / 3 | 유입 경보 (결정 6, 결정 기록 8) |

### D.2 한 초 처리 순서

1. 첫 프레임과 반복(불연속)이면 `grader.reset()`, `alerts.reset()` (`ZoneRuntime.java:42-44`, `ZonePlayer.java:22`, `:61`).
2. `ZoneGrader.evaluate`: 셀마다 `InstabilityTracker.update(pressure)` → 관측 등급 → `GradeHysteresis.update` (`ZoneGrader.java:71-84`). 그다음 구역 `InflowMonitor.update(inflow_ratio, count)` (`:85`).
3. `AlertDetector.detect`: `INSTABILITY` → `GRADE_UP` → `INFLOW` 순서 (`AlertDetector.java:26-50`).

- E5는 한 번 재생(t=0부터 끝까지, 시작에 초기화)만 보면 된다.

### D.3 불안정 `InstabilityTracker` (셀 단위, 모든 셀)

- `pressure != null && pressure > threshold`(초과, 같으면 아님)이면 연속 +1, `seconds`에서 멈춤. 아니면 연속 0 (`InstabilityTracker.java:25-33`).
- `null`도 연속을 0으로 만든다. 사람 없는 셀은 `pressure` 0이라 역시 끊는다.
- 불안정 = 연속 ≥ `seconds`. 조건이 깨진 초에 바로 풀린다. 별도 유지 타이머는 없다 (`InstabilityTracker.java:5-8`).
- 판정 대상이 아닌 작은 셀도 추적하고 자기 등급은 올리지만, 구역 등급·알림에서는 빠진다 (`ZoneGrader.java:73-81`, `AlertDetector.java:29`, `ZoneGraderTest.java:292` "작은 셀의 불안정은 자기 등급만 올리고 구역 등급에서 빠진다").

### D.4 등급 `ZoneGrader` + `GradeHysteresis` (셀 단위 → 구역)

- 관측 등급 = 불안정이면 `CRITICAL`, 아니면 밀도 등급. 밀도 null이면 관측 null (`ZoneGrader.java:101-106`).
- 히스테리시스 (셀마다, 시작 `NORMAL`) (`GradeHysteresis.java:34-54`):
    - null 관측은 아무것도 바꾸지 않는다 (`:35-37`).
    - 올림: 최근 2개 관측이 모두 현재보다 높으면 그중 낮은 등급으로 (`:42-47`). 기록은 비우지 않는다.
    - 내림: 최근 10개 관측이 모두 현재보다 낮으면 한 단계만 내리고 기록을 비운다 (`:49-52`).
- 구역 등급 = 판정 대상 셀 등급의 최댓값. 대상이 없으면 `NORMAL` (`ZoneGrader.java:76-81`).

### D.5 유입 `InflowMonitor` (구역 단위)

- 원형 창 5칸에 `inflow_ratio`(null 포함)를 넣는다 (`InflowMonitor.java:32-36`).
- 평균: 관측이 5개 쌓이기 전(t0~t3)은 null. 그 뒤 창 안 non-null이 3개 이상이면 그 평균, 아니면 null (`:59-71`).
- 조건: 평균 != null && 평균 > 0.6 (초과) && `count` != null && `count` ≥ 3 (이상) (`:38-39`).
- 켬: 조건이 참인 초에 바로. 끔: 켜진 뒤 조건이 10초 연속 거짓. 평균 null·`count` 부족·`count` null인 초도 거짓 (`:40-46`, `:12`).
- `count`는 작은 셀을 포함한 구역 전체 인원이다 (B 표).

### D.6 알림 `AlertDetector` (구역 단위)

| 알림 | 생기는 때 | 다시 보내는 조건 | 근거 |
|---|---|---|---|
| `INSTABILITY` | 판정 대상 불안정 셀이 0개 → 1개 이상이 된 초 | 모두 풀린 뒤 다시 생길 때. 다른 셀이 추가로 불안정해져도 새 알림 없음 | `AlertDetector.java:29-33`, `api-spec.md:148` |
| `GRADE_UP` | 구역 등급 ≥ `ALERT`이고 이번 사건에서 보낸 최고 단계보다 높을 때 | 구역 등급이 `ALERT` 아래로 내려가면 사건 끝 | `AlertDetector.java:35-42`, `api-spec.md:142-143` |
| `INFLOW` | 유입 경보가 꺼짐 → 켜짐 | 꺼졌다 다시 켜질 때 | `AlertDetector.java:44-47` |

- 주의(`CAUTION`)로 오르는 것은 알림이 없다 (`api-spec.md:150`).

### D.7 시점 예 (서버 시험으로 확인된 것)

- 밀도 1.0, `pressure` 0.03이 계속이면 `unstable`은 t2부터 참, 셀·구역 등급은 t3에 `CRITICAL` (`ZoneGraderTest.java:259-267`). 알림은 t2 `INSTABILITY`, t3 `GRADE_UP`(심각) (`AlertDetectorTest.java:244-258`, `api-spec.md:149`).
- t4부터 `pressure` 0이면 `CRITICAL`은 t12까지, t13에 `ALERT` (`ZoneGraderTest.java:278-289`). 그 뒤 10초마다 한 단계씩 내려가 `ALERT` 아래가 되면 `GRADE_UP` 사건이 끝난다 (계산).
- 그래서 "경보 시간"은 정의에 따라 크게 다르다: (a) 불안정 셀이 있는 초, (b) 구역 `CRITICAL`인 초(+10초 꼬리), (c) `GRADE_UP` 사건이 열린 초(+20초 꼬리, 계산). E5에서 정해야 한다.
- E04_039 밀도 수준: 수작업 정답에서 셀 최대 밀도는 2.5명/㎡(`c-0000`, t=147, 10명/4㎡)다 (계산, `outputs/e2/E04_039_gt.csv`). P2PNet은 평균 0.82명 적게 센다(`outputs/e2/E04_039_e2_avg5.md`). 따라서 E04_039에서 밀도만으로는 주의(3.0)에도 못 미칠 가능성이 크고, `GRADE_UP`은 불안정에서만 나올 것이다 (추론).
- 이 밀도에서 P > 0.02가 되려면 `speed_var` > 0.02/ρ, 예: ρ = 2.5이면 0.008 m²/s² 초과, ρ = 1.0이면 0.02 초과가 필요하다 (계산).

### D.8 민감도 실행 방식 비교

| | (i) Python으로 다시 구현 (`src/flow/`) | (ii) Java 판정기 재사용 (`server/`) |
|---|---|---|
| 하는 일 | `InstabilityTracker`·`GradeHysteresis`·`InflowMonitor`·`AlertDetector` 규칙을 작은 Python 클래스로 옮겨 timeline을 1초씩 넣는다 | `TimelineLoader`(패키지 공개 `load`, `TimelineLoader.java:54`) + `ZoneGrader` + `AlertDetector`를 설정만 바꿔 돌리는 main 또는 별도 Gradle 작업 |
| 어긋남 위험 | 있음. 서버 규칙이 바뀌면 따라 고쳐야 한다. 11-19 코드 동결 뒤에는 위험이 작다 (`docs/proposal.md:171`) | 없음. 서버 코드 그대로 |
| 어긋남 대책 | 서버 JUnit 사례(D.9)를 pytest로 옮긴다. 기본 설정 결과를 서버 기준값으로 기록 | 불필요 |
| 폴더 담당 | `src/flow/` = 조영준 | `server/` = 조영준. 둘 다 같은 담당이라 문제없음 |
| 공수 | 상태 기계 4개 약 100~150줄 + 시험. 시계열 그림·시간 차 분석과 한 언어 | `ZoneGrader`·`AlertDetector`는 Spring 없이 생성 가능(`ZoneRuntime.java:19`). 그래도 JSON 매퍼(SNAKE_CASE)·설정 record 생성, `build.gradle`에 실행 작업 추가, CSV 출력, Python과 이어 붙이기가 필요 |
| 규칙 충돌 | 없음 | 서버 규칙 "기준값은 `application.yml` 한 곳"(CLAUDE.md `server/` 표)과 실험용 값 바꾸기가 어긋난다. 실험 코드가 서버 빌드에 들어간다. 실제 데이터 파일을 읽는 시험은 다른 PC에서 깨진다 |
| 시간 | 설정 조합 수백 개도 몇 초 | 빠르지만 JVM·Gradle 기동 비용 |

- **권장: (i)**. 이유: E5의 나머지(시계열, 시간 차, 표·그림)가 모두 Python이다. 서버 규칙은 작고 시험 사례가 잘 정리돼 있다(D.9). 서버를 실제로 띄워 재생하는 방법은 조합 하나에 180초가 걸려 제외한다.
- (i)를 고르면 결과 문서에 "서버 규칙 기준 커밋 `f0236fb`(#52)"를 적는다.

### D.9 pytest로 옮길 서버 시험 사례

- `InstabilityTrackerTest.java:27-62`: 3초 연속 초과면 불안정 / null은 연속을 끊음 / 기준과 같으면 초과 아님 / 기준 아래로 내려간 초에 바로 풀림 / 초기화 / `seconds` 1.
- `InflowMonitorTest.java:58-183`: 5초 평균 초과 초에 켬 / 창 덜 차면 null / 창 안 null 빼고 평균 / non-null 3개 미만이면 null / 같으면 안 켬 / `count` < 3 안 켬, 정확히 3 켬, null 안 켬 / 10초 연속 거짓이면 끔 / 평균 null도 끄는 연속에 셈 / 중간에 참이면 연속 처음부터.
- `GradeHysteresisTest.java:67-166`: 2초 올림, 1초 튐 무시, 낮은 쪽으로 올림, 단계 건너뜀, 10초 한 단계 내림, null 처리.
- `ZoneGraderTest.java:105-138`, `:259-306`: 2㎡ 규칙(정확히 2㎡ 포함), 불안정 → 심각 시점, 내림 꼬리.
- `AlertDetectorTest.java:64-258`: 재전송 규칙, 판정 대상만, 한 초 순서.
- `api-spec.md:143` 등급 예(정상, 주의, 경계, 심각, 경계, 심각, 주의, 경계 → 3·4·8번째 전송), `:210` 유입 평균 예(0.7, null, 0.8, 0.7, 0.9 → 0.775).

---

## E. 기존 도구·출력 형식·규칙

- **그림 도구 없음.** `src/flow/eval_flow.py`는 G1 채택 판정(`g1_decision`, `choose_fallback`)뿐이고(`eval_flow.py:10`, `:90`), `baselines.py`는 60초 예측 기준선과 `mae`다(`baselines.py:12`, `:90`). E5에 그대로 쓸 함수는 없다.
- **패키지**: `requirements.txt`에 `matplotlib`·`pandas`가 없다 (`requirements.txt:6-14`). `scipy`는 있지만 버전이 없다 (`:12`). `crowdsight` 환경에도 `matplotlib`·`pandas`·`scipy`·`yaml`·`sklearn`이 없다(직접 import 확인). 있는 것: numpy 2.4.6, opencv 5.0.0, torch 2.14.1+cpu, Pillow 13.0.0, pytest 9.2.0. 패키지 추가는 `requirements.txt` 반영·팀 알림·승인 후 설치다 (CLAUDE.md "데이터·AI 규칙").
- **출력 형식 (따라 할 것)**:
    - `outputs/e1/SHA.md`: `# 제목` + `| 항목 | 값 |` 표(지표, 소요 시간, 환경). `SHA.csv`: 행별 원자료.
    - `outputs/e2/E04_039_e2_avg5.md`: 설정별 비교 표 + 판정 줄. `*_best.json`: 고른 설정. `*_gt.csv`: 원자료.
    - `outputs/g1/E04_039_counts.csv`: `t,zone_count,frame_count`.
    - 제안: `outputs/e5/E04_039_e5.md`(요약·표), `E04_039_series.csv`(초별 시계열), `E04_039_sweep.csv`(설정별 결과). 원본 프레임 이미지는 저장하지 않는다 (CLAUDE.md "원본 영상 … 저장하지 않는다").
- **시험 배치**: `tests/flow/test_*.py`, 모듈 docstring에 테스트 경계(T번호)와 손 계산 방식을 한국어로 적는다 (`tests/flow/test_inflow.py:1-4`). 함수 `-> None` 타입힌트 + 한국어 docstring. 느린 시험은 `@pytest.mark.slow` (`pytest.ini`). 루트 `conftest.py`로 `import src...`가 된다.
- **현재 상태**: `pytest tests/flow -m "not slow"` 259 통과, 5개 제외(13초).
- **코드 규칙**: PEP 8, 타입힌트, 한국어 docstring, `(가정)`·`[토론]` 표기(`src/flow/` 전체). 흐름 계획은 줄 79자 이하를 썼다 (`docs/plans/flow_head_plane_impl_plan.md` 8절). E5는 무작위가 없지만 실험 설정·결과는 기록한다 (CLAUDE.md "재현성").
- **timeline 읽기**: `src/predict/io.py:25` `load_timeline`(dataclass)과 `src/predict/schema.py:270` `validate_timeline`이 있다. 나예린 폴더라 import만 한다. dict로 직접 읽어도 된다(`run_flow.py`는 `json.loads`).

---

## F. 유입 → 인원 증가 시간 차 (항목 3)

### F.1 "약 20~25초 앞섰다"의 출처

- 문장: `docs/proposal.md:136`. 처음 들어온 커밋은 `79c9cf1`(2026-11-06, 이유노, "프로젝트명 CrowdSight와 v3.0 범위 축소 반영", 문서만 바꿈)이다 (`git log -S "20~25"`).
- 그 시점에는 흐름 코드가 없었다. 첫 흐름 코드는 11-09(`f304050`, `a5bfc7b`), `inflow.py`는 #32, E04_039 밀도 파이프라인은 #29(11-11)다.
- PR #7 본문·댓글, 다른 PR 본문, `docs/`·`docs/research/`·`docs/plans/`, 노트북(`notebooks/`는 비어 있고 `.ipynb` 커밋 이력 없음)에 측정 방법이 없다.
- 같은 문장의 "샘플 4개에서는 직선 추세가 현재값 유지보다 나빴다"도 근거 파일이 없다.
- 결론: **지금 저장소로는 재현할 수 없다.** 무엇을 "유입"으로 봤는지, 무엇을 "인원 증가"로 봤는지, 어떤 자료(AI Hub 라벨인지 등)를 썼는지 이유노에게 물어야 한다 (확인 필요).

### F.2 지금 있는 자료

| 자료 | 있음 | 내용 |
|---|---|---|
| 초별 구역 인원 | 있음 | `outputs/g1/E04_039_counts.csv` (P2PNet 5장 평균, t=0~179) |
| 수작업 정답 | 있음 | `outputs/e2/E04_039_gt.csv` (6초 간격 30프레임, 셀별) |
| 초별 `inflow_ratio` | **없음** | 흐름 실행 필요 (A.3) |

- `count` 10초 평균 (계산): 0~39초 1.06~1.52명 → 40~49초 2.20 → 50~59초 4.14 → 60~69초 6.60 → 70~79초 10.82 → 80~169초 9.5~12.0 → 170~179초 14.20.
- `count` ≥ 3이 처음 나오는 초는 t=47이다 (계산).
- 수작업 정답: 30프레임 합계로 `c-0000` 136명, `c-0100` 110명, 나머지 10개 셀은 0~3명이다 (계산). `c-0100`은 t=3부터 1명, t=33에 2명이고, `c-0000`은 t=45에 처음 1명이다.
- 큰 상승은 한 번(약 t=40~75)이고 끝 부분(약 t=150~179)에 작은 상승이 있다. 시간 차 표본이 1~2개뿐이다 (추론).

### F.3 측정 방법 후보

| 방법 | 계산 | 필요한 자료 | 장점 | 약점 |
|---|---|---|---|---|
| 상호상관 | `inflow_ratio`(또는 서버식 5초 평균) vs `d(count)/dt`(평활 후)의 지연 k별 상관, 최대 k | 초별 `inflow_ratio`, `count` | 사건 정의가 필요 없다 | null이 많으면 계열이 끊긴다. 상승 1~2번이라 최대점이 불안정. `count` 미분은 잡음이 크다(10초 안 최소·최대 차 수 명) |
| 사건 기반 (원 신호) | t_in = 5초 평균이 처음 0.6 초과(인원 조건 없이), t_cnt = `count`가 기준(예: 3명, 상승 폭의 50%) 처음 도달. 차 = t_cnt − t_in | 위와 같음 | 서버 규칙과 같은 평균이라 설명이 쉽다 | 기준 선택에 따라 값이 바뀐다 → 기준 몇 개로 표 |
| 사건 기반 (서버 경보) | t_in = 실제 `INFLOW` 알림 초(`count` ≥ 3 조건 포함) | 위와 같음 + D.5 규칙 | 상황실이 실제로 받는 선행 시간 | `count` ≥ 3 조건 때문에 t=47 전에는 켜질 수 없다 |
| 유량 기반 (추가 제안) | 비율 대신 안쪽으로 움직이는 경계 머리 수 | 흐름 모듈 수정 필요(파일에 없음) | "몇 명이 들어오나"에 가깝다 | 규격 밖. MVP E5 범위를 넘는다 |

- 원 신호와 서버 경보를 둘 다 보고하면 "신호는 앞서지만 인원 조건 때문에 경보는 늦다" 같은 결과를 그대로 보여 줄 수 있다.

### F.4 E04_039에서 주의할 구조 (추론, 확인 필요)

- 경계 셀은 화면 아래 줄 3개뿐이다. 판정은 사람 있는 경계 셀만 쓴다 (A.6, C.4). 수작업 정답상 아래 줄에서 사람이 있는 곳은 사실상 `c-0000`뿐이고 t=45부터다 (F.2). 그 전에는 지나가는 사람이 없으면 `inflow_ratio`가 null일 것이다.
- 인원은 `c-0100`(경계 아님)에서 먼저 늘고(t=33) `c-0000`이 나중에 찬다. 사람이 화면 아래 끝으로 들어오는지, 먼 쪽(화면 위, 경계 아님)이나 왼쪽 벽 쪽에서 오는지는 영상을 봐야 안다.
- 따라서 지금 정의로는 유입 신호가 인원 증가(약 t=33~47 시작)보다 20초 넘게 앞서기 어려울 수 있다. 실제 흐름 실행으로 확인해야 한다.
- `pressure`도 같은 구조다. 새로 찬 셀은 30칸 중 유효 24칸이 쌓이기 전까지 null이다. `c-0000`이 t≈45부터 계속 차 있으면 `pressure`는 대략 t≈68부터 나온다 (추론, C.2).

---

## G. 난류 조사 문서에서 E5에 쓸 것 (`docs/research/crowd_turbulence_research.md`)

- 0.02/s²는 그대로 옮겨 쓸 수 있는 값이 아니다. 원 저자가 "측정 방법의 매개변수, 특히 R에 따라 달라지므로 보정해야 한다"고 썼다 (`:22`, `:121`). 다른 장소에서 독립 검증한 연구는 못 찾았다 (`:123`).
- 0.02/s²는 메카 2006 시간 그래프에서 난류가 시작된 시점의 값이다. 원 연구는 개인 추적, R = 1m, 8 fps, 45분 평균 기준 분산이다 (`:22`, `:117`).
- 속도 척도 오차 k배 → 분산·압력 k²배. 척도 10% 오차 → 압력 약 21% (`:351`). E04_039 구역 설정에도 "가로 배율이 5~10% 작을 수 있음"이 있다 (`infra/homography/E04_039.json:52`).
- 잡음 바닥: 성분 잡음 σ = 0.05 m/s만으로 밀도 5명/㎡에서 P = 0.025/s² (`:367-369`). 잡음을 빼지 않으면 P가 밀도 정보를 반복할 수 있다 (`:371`). 지금 코드는 잡음을 빼지 않는다 (C.2).
- 제안 C4: 0.02는 "문헌 참고선"으로 표시하고, 경보 기준은 장면 기준선 대비 상대값(정상 구간 P 분포의 상위 백분위) (가정) [토론] (`:416`, `:441`). 상대 기준은 "평소와 다름"이지 "위험"이 아니다 (`:422`).
- T(10·30·60초)를 바꿔 보는 것이 민감도 분석의 핵심이라고 했다 (`:421`, `:458` V5).
- C5: E5를 민감도 표·잡음 바닥 표 등으로 바꾸자는 제안이 이미 있다 (`:417`). 지금 E5 범위와 맞는다.

---

## H. E5가 닫을 안건

| 안건 | 위치 | 지금 상태 | E5로 할 수 있는 것 |
|---|---|---|---|
| 0.02/s² + 3초 | `api-spec.md:341` (10절 2번), `:201`, `server_s4_instability_inflow_plan.md:911` | "E5 결과로 조정" | 민감도 표로 기준값 제안. 바꾸면 `application.yml:25-26`만 고친다 (`server_s4_instability_inflow_plan.md:763`) |
| `pressure` null이 3초 연속을 끊는 빈도 | `server_impl_plan.md:661` (#11), `server_s4_instability_inflow_plan.md:890`, `:910` | "끊음 유지, E5 때 빈도 확인" | 셀별 null 비율, 초과 연속이 null로 끊긴 횟수 vs 기준 이하로 끊긴 횟수, "null 건너뜀" 변형과 알림 수 비교 |
| `counterflow`를 불안정 판정에 넣을지 | `api-spec.md:347` (10절 8번), `:203-204`, `server_s4_instability_inflow_plan.md` [토론] 6 | 쓰지 않음 | **자료로 닫을 수 없다.** 흐름 모듈이 `counterflow`를 쓰지 않아 늘 null이다 (B). 닫으려면 흐름 쪽 쓰기 추가(범위 밖) 또는 "MVP는 안 씀"으로 닫기 |
| 2㎡ 기준이 왼쪽 열을 뺀다 | `api-spec.md:356` (10절 17번), 결정 4 `decisions-2026-11-11.md:13` | "실제 셀 면적 확인 뒤 결정" | **실제 셀로는 문제가 없다** (A.6). 왼쪽 열 4.0·4.0·4.0·2.6㎡ 모두 대상, 사람이 몰리는 `c-0000`·`c-0100`도 대상. 빠지는 것은 오른쪽 열(1.8·1.8·1.8·1.17㎡). 결정 4의 1.17㎡ 셀(`c-0302`, 오른쪽 위)과도 맞다 |
| 유입 기준 0.6, `count` < 3 | 결정 6 (`decisions-2026-11-11.md:15`), `api-spec.md:342` | 닫힘 (가정 값) | 민감도 표로 값 근거 보충, `count` 조건이 선행 시간을 깎는지 보고 (F.3) |
| `inflow_ratio` 정의 [토론] | `inflow.py:3-13`, `:31-34`, `run_flow.py:93-95` | 팀 결정 대기 | E04_039 경계가 아래 줄뿐이라는 사실과 null 빈도 보고 |

---

## 확인 못한 것

- E04_039 영상 위치·fps·해상도. 셀 계산은 1920×1080을 가정했다(보행 다각형의 y = 1080, PR #29의 셀 수·면적과 일치).
- 20~25초 사전 측정의 방법·자료·코드 (F.1). 이유노에게 물어야 한다.
- 이 PC의 P2PNet 추론 시간 (가중치가 없어 못 잼). 8.5분은 팀장 PC 값이다.
- 실제 흐름 값: `pressure`·`inflow_ratio`의 크기, null 비율, 속력 중앙값 (흐름이 실제 영상에서 돈 적이 없다. PR #36 남은 이슈의 계획 8단계도 미실행).
- E04_039에서 사람이 어디로 들어오는지 (영상 확인 필요, F.4).
- 팀장이 가진 밀도 `E04_039.json`이 지금 `main`의 `run_density.py`(5장 평균)로 만든 것인지. `outputs/g1/E04_039_counts.csv`는 5장 평균 커밋(`54849d2`)에서 갱신됐다.
- `E05_035` 구역 설정 일정 (결정 1 기한 11-13, 아직 없음).
- AI Hub 71850 `군집` zip(E04 계열)을 어디서 받는지. 로컬 zip은 `인파밀집` 금요일분뿐이다.

---

## Planner에게: 사용자가 정할 것

1. **입력을 어떻게 얻을지** (A.3): 가) F4-2 통합 스크립트를 기다린다 / 나) 이유노에게 영상·밀도 timeline·가중치를 받아 E5용 흐름 진입점을 만든다 / 다) 밀도까지 직접 돌린다. 나·다는 `scipy` 설치(`requirements.txt`에는 이미 있음)와 `third_party/` P2PNet 코드가 필요하다.
2. **항목 1을 어느 영상으로 할지**: 기획서상 불안정 시연은 `E05_035`다 (`proposal.md:182`, `:214`). 하지만 `E05_035` 구역 설정이 없다. E04_039로 먼저 할지, E05_035 설정(F1-6)을 기다릴지.
3. **민감도 실행 방식**: (i) Python 재구현 + 서버 시험 사례 이식(권장) / (ii) Java 재사용 (D.8).
4. **그림 도구**: `matplotlib` 추가(버전 고정, 팀 알림, 설치 승인) / `cv2`로 직접 그림(한글 글자 불가) / CSV만 내고 그림은 생략.
5. **구역 시계열 대표값**: 판정 대상 셀 `pressure` 최댓값(= `INSTABILITY` 값과 같은 정의) / 밀도 가중 평균 / 셀별 선 여러 개.
6. **민감도 격자와 지표 정의**: `pressure` 기준(예: 0.02의 0.25·0.5·1·2배), `seconds`(1~5), null 처리(끊음 / 건너뜀), `inflow.ratio`·`window-seconds`·`min-samples`·`min-count`·`off-seconds` 범위 (모두 제안 값, 결정 필요). "경보 시간"을 (a) 불안정 셀 있는 초 / (b) 구역 `CRITICAL` 초 / (c) 사건 열린 초 중 무엇으로 셀지 (D.7).
7. **T(30초) 민감도를 넣을지**: 저장된 `vx`·`vy`로 다시 계산하면 영상 재실행 없이 된다 (C.6). 기획서 E5 문구에는 없다.
8. **시간 차 정의**: 상호상관 / 사건 기반(기준 몇 개) / 서버 경보 기준 중 무엇을 주 결과로 할지, 표본이 1~2개뿐이라는 한계를 결과에 어떻게 적을지 (F.3). 20~25초 문장을 E5 결과로 바꿀지(기획서는 이유노 문서).
9. **`counterflow` 안건(10절 8번)**: 자료가 없으니 "MVP는 판정에 안 씀"으로 닫을지 (H).
10. **결과 위치와 형식**: `outputs/e5/`에 md + csv(+ png) (E 절 제안).
