# E5 구현 계획: 불안정 지표 시계열·기준값 민감도·유입 → 인원 증가 시간 차

| 항목 | 내용 |
|---|---|
| 작성일 | 2026-11-16 |
| 작성 | Planner 서브에이전트 (조영준 요청) |
| 브랜치 | `feat/flow-e5` (기준 `main` = `f0236fb`, v1.4에서 `origin/main` = `24537bb`를 병합. PR 기준 `main`) |
| 근거 | `docs/proposal.md:51-52`, `:126-127`, `:136`, `:316` (E5), `docs/research/e5_research.md` (조사), 사용자 결정 11-16 (2장 확정 1~5), 11-18 (확정 6) |
| 서버 판정 | 서버 판정 클래스를 그대로 쓰는 Java 실행기 `e5Sweep` (확정 2). 기본값 `application.yml:19-32` |
| 상태 | **계획 v1.4. 사용자 점검 중.** v1.3까지 구현·리뷰 완료(미커밋). v1.4는 main 병합과 E5 자체 timeline 생성 제거(8.1절 I1~I4) |
| 테스트 명령 | Python 전체 `conda run -n crowdsight python -m pytest tests -m "not slow" -q` (11-18 `main` 병합 뒤 416 통과, 5 제외. 그중 `tests/flow` 312). Java (Git Bash, `server/`) `JAVA_HOME="/c/Program Files/Eclipse Adoptium/jdk-21.0.13.9-hotspot" ./gradlew test --no-daemon` |
| 담당 폴더 | 새 코드는 `src/flow/e5/`, `tests/flow/e5/`, `server/src/test/java/com/tripley/crowdsight/e5/`, `server/src/test/resources/e5/`, `server/build.gradle`(작업 1개 추가), 결과는 `outputs/e5/` (모두 조영준). `server/src/main/`은 바꾸지 않는다. `src/counting/`·`infra/`·`docs/proposal.md`(이유노), `src/predict/`(나예린)는 import·읽기만 |

## 0. 코드로 다시 확인한 것

조사 문서의 핵심 주장을 소스에서 다시 확인했다. 아래는 계획이 기대는 사실만 적는다.

### 0.1 입력 생성: 통합 분석 스크립트 (v1.4, `origin/main` `24537bb`로 확인)
- E5 입력은 이유노의 통합 분석 스크립트 `src/counting/analyze.py`(#53, `e5906cb`)가 만든 timeline이다 (확정 6). CLI (`analyze.py:3-5`, `:35-40`):
  `python -m src.counting.analyze --homography infra/homography/{video}.json --video data/processed/g1/{video}.mp4 --out data/processed/timeline/{video}.json [--predictor P] [--limit N]`
- 순서 (`analyze.py:48-68`): `run_density.count_video(cfg, video, limit)` → `(timeline, heads, rows)` → `out`에 밀도 timeline 쓰기 → `analyze_video(video, out, out, FarnebackEstimator(), heads=heads, h_head=…, cell_origin_m=…)`(`:56-58`) → `del heads` → `fill_predictions(…, make_predictor(config))`로 `density_pred_60s`를 채워 다시 쓴다. 머리 점은 메모리로만 넘긴다.
- `count_video`(`run_density.py`, main `:59-133`)의 가운데 장은 `frame_plan`이 정하는 `round(t·fps)` 프레임이고 흐름 시작 프레임과 같다. 이것을 `tests/counting/test_analyze.py:10-17`이 확인한다. 셀 필드·`count`·meta(`zone_id` = `zone-{video 소문자, _→-}`, `models.counter`)는 v1.3까지 E5가 만들던 것과 같은 식이다.
- 흐름 인자: `analyze.py:56-58`은 `noise_var`·`min_heads`·`patch_radius_px`·`inflow_min_heads`를 넘기지 않는다. 그래서 `analyze_video` 기본값(`run_flow.py:64-69`: `noise_var=None`, `window_s=30`, `min_heads=1`, 반경 6, `inflow_min_heads=0`)이 쓰인다. v1.3 E5 진입점과 같은 값이다.
- E5가 읽는 필드는 모두 채워진다: 셀 `density`·`vx`·`vy`·`speed_var`·`pressure`, 프레임 `count`·`inflow_ratio`(`analyze_video`), `meta.models.flow` = `"farneback-cv2 head-r6"`(`run_flow.py:86`, `estimators.py:33`). 추가로 `density_pred_60s`와 `meta.models.predictor`(기본 `persistence`, `src/predict/config.yaml`)가 채워진다. `analysis.py`·`report.py`는 이 둘을 읽지 않는다(`report.py:273-281`은 `counter`·`flow`만 쓴다). 서버 검증기는 v1.3 때도 이 필드를 받았다.
- **부수 효과 (중요)**: `analyze.py`는 `outputs/g1/{video}_counts.csv`(`save_counts`, `:51`)와 `outputs/e8/{video}_analysis_time.json`(`:79-81`)을 덮어쓴다. 두 폴더 파일은 main에서 git 추적 중이다(E04_039·E05_035·E05_038 모두, 이유노 결과). `--limit` 실행도 덮어쓴다. 그래서 E5 쪽에서 직접 돌리면 실행 뒤 `git restore outputs/g1 outputs/e8`로 되돌린다(10장 A).
- 처리 시간(이유노 PC, `outputs/e8/*_analysis_time.json`): E04_039 180초 → 629초(인원 522, 흐름 107), E05_035 61초 → 약 1154초(인원 1120), E05_038 60초 → 1093초(인원 1059).
- 구역 설정: main에 `infra/homography/E05_035.json`·`E05_038.json`(#54)이 생겼다. 둘 다 `head_plane`·`cell_origin_m`이 있다. 구역 ID는 `zone-e04-039`·`zone-e05-035`·`zone-e05-038`이다(`count_video` meta 규칙).
- 가중치·P2PNet 코드 경로(`eval_e1.py:28-30`)는 그대로다. 이 PC에는 `third_party/`, `data/raw/weights/`, `data/processed/` 내용이 없다(v1.4 `ls` 확인). 그래서 timeline은 이유노에게 받는 쪽이 기본이다(10장 A).
- `crowdsight` 환경 (v1.4 확인): `scipy` 1.17.1, `matplotlib` 3.11.2 있음. **`scikit-learn`·`joblib` 없음**(import 실패). main의 `tests/predict/test_ml_forecast.py`가 `src.predict.train_forecast.make_model`(함수 안에서 `sklearn` import)과 `save_bundle`/`load_bundle`(`joblib`)을 써서, 설치 전에는 그 시험 일부가 실패한다(3.2절).
- 예측 단계의 `save_timeline`(`src/predict/io.py`)은 `schema._DIGITS`(vx·vy 2자리, speed_var·pressure 4자리)로 다시 반올림한다. `fill_flow_fields`(`timeline_flow.py:77-81`)와 같은 자리수라 흐름 값은 바뀌지 않는다. 그래서 `recompute_check`(6.3절) 기대도 그대로다.
- `src/predict/schema.validate_timeline`과 `src/predict/io.assert_not_raw`는 `analysis.py`·`report.py`가 계속 import한다 (나예린 파일, 읽기만).
- 한글 글꼴: `C:/Windows/Fonts/malgun.ttf` 있음.

### 0.2 서버 재생 경로 (Java 실행기가 그대로 쓸 클래스)
| 클래스 | 위치 | 실행기가 쓰는 방법 |
|---|---|---|
| `TimelineLoader(JsonMapper, CrowdsightProperties)` | `timeline/TimelineLoader.java:27`, `loadAll()` `:36-51` (공개), `load(Path)` `:54`(패키지 전용) | `loadAll()`만 쓴다. 파일 하나를 `timeline-dir` = 부모 폴더, `timeline-files` = [이름]으로 넘긴다. 읽기 → `TimelineValidator.validate` → record (`:70-79`). 서버와 같은 검증기를 거친다 |
| `ZoneRegistry(TimelineLoader, CrowdsightProperties)` | `replay/ZoneRegistry.java:150-155`, `register` `:167-178` | 서버와 같은 배선: `new ZoneGrader(meta.cells, props.grade(), props.instability(), props.inflow())` + `new ZoneRuntime(new ZonePlayer(timeline, props.replay().loop()), grader)`. 실행기는 조합마다 `CrowdsightProperties`를 만들어 이 생성자를 부른다(직접 배선 없음) |
| `ZoneRuntime.tick()` | `replay/ZoneRuntime.java:37-48` | 첫 tick(불연속)에 판정·알림 초기화 → `ZoneGrader.evaluate` → `AlertDetector.detect`. `ZoneStep(tick, evaluation, alerts)`를 준다 |
| `ZonePlayer(timeline, loop)` | `replay/ZonePlayer.java:25`, `tick()` `:47-71` | `loop=false`면 끝에서 `ENDED`, 빈 값. 실행기는 빈 값이 나올 때까지 돈다 |
| `ReplayScheduler.tickAll` | `replay/ReplayScheduler.java:63-98` | 구역마다 `zone.tick()` → 방송. 판정은 `ZoneRuntime.tick()` 그대로라 실행기는 방송만 뺀 같은 경로다 |
| `WsZoneBroadcaster.zoneState` | `ws/WsZoneBroadcaster.java:36-43` | 실제 서버는 `step.alerts()`마다 `AlertStore.issue`(INFO 로그 `알림 zone= t= reason= level= value=`, `alert/AlertStore.java:45`) 후 방송. 실행기 알림 = `step.alerts()` |
| 설정 record | `config/CrowdsightProperties.java:31-33`(11개 성분, 공개 생성자), `grade/GradeSettings`·`InstabilitySettings(double pressure, int seconds)`·`InflowSettings(double ratio, int windowSeconds, int minSamples, int offSeconds, double minCount)` | 조합마다 새로 만든다. 값 검사는 각 record 생성자가 한다 |
| 기본값 | `src/test/java/.../config/TestProperties.java:16-22` `GRADE`·`INSTABILITY`·`INFLOW` | `application.yml` 기본값과 같음을 `CrowdsightServerApplicationIntegrationTest.java:55-56`(실제 yml 바인딩)과 `CrowdsightPropertiesTest`가 확인한다. 실행기 기본 행 = 이 상수 |
| JSON 매퍼 | `src/test/java/.../timeline/TimelineFixtures.java:16-18` `MAPPER` | `SNAKE_CASE`, "application.yml과 같게". 실행기가 그대로 쓴다 |
| 판정 결과 | `grade/ZoneEvaluation(t, zoneGrade, maxDensity, inflowAvg, inflowAlert, cells)`, `grade/CellEvaluation(cellId, grade, gradePred60s, eligible, unstable, state)`, `alert/AlertEvent(level, reason, message, value, cellIds)`, `alert/AlertReason` `GRADE_UP`·`INFLOW`·`INSTABILITY` | CSV 열의 원천 |
| `build.gradle` | `server/build.gradle` | 사용자 작업 없음. `test`는 `useJUnitPlatform()`. JUnit Platform은 `@Test`가 있는 클래스만 실행하므로 `main`만 있는 클래스는 시험으로 돌지 않는다 |

- 실제 서버 알림 수집 (4번 지시 확인 결과):
  - `crowdsight.alert-log`(`application.yml:38`, 기본 `logs/alerts.jsonl`, `server/` 기준)은 **알림 확인(ack) 기록만** 쓴다. `AlertLogWriter.java:16-17`, `:35-36`이고, 처음 확인일 때만 부른다(`api/AlertController.java:49-51`). 그래서 확인하지 않은 알림은 이 파일에 없다.
  - 낸 알림 전체는 `GET /api/zones/{zone_id}/alerts`(`AlertController.java:55-63`, 오래된 것부터)로 받는다. 키는 `t`·`reason`·`level`·`value`·`cell_ids` 등이다(`api/AlertView.java:25-26`). 구역당 `crowdsight.unacked-alert-limit`(기본 100)개까지만 보관한다(`AlertStore.java:46-48`).
- 서버 실행 설정 키 확인: `crowdsight.replay.loop`(`CrowdsightProperties.Replay`, yml `replay.loop`), `crowdsight.unacked-alert-limit`, `crowdsight.timeline-dir`·`timeline-files` 기본값이 `../data/processed/timeline`·`[E04_039.json]`(`application.yml:12-13`). 실행 예는 `server/README.md:94`의 `--args='--crowdsight.…'` 방식이다.

### 0.3 결과에 영향을 주는 사실
- `outputs/g1/E04_039_counts.csv` 계산: `count` ≥ 3이 처음 나오는 초는 t=47. 10초 평균 0~39초 1.06~1.52명 → 50~59초 4.14 → 70~79초 10.82 → 170~179초 14.20. 큰 상승은 한 번(약 t=40~75), 끝에 작은 상승.
- `speed_var`·`pressure`는 30초 창이 차기 전(t=0~28) 늘 null이다 (`src/flow/cells.py:125-127`). 잡음 바닥은 빼지 않는다(`noise_var=None`, `cells.py:84-86`).
- `inflow_ratio`는 사람 있는(소수 2자리 density > 0) 경계 셀 머리만 쓴다 (`run_flow.py:235-241`). E04_039 경계 셀은 화면 아래 줄 3개뿐이다 (조사 A.6). 그래서 t≈45 전에는 대부분 null일 수 있다 (조사 F.4, 추론).
- v1 작성 때 `pytest tests/flow -m "not slow"`: 259 passed, 5 deselected. v1.4 작성 때(구현 뒤, 병합 전): `tests` 전체 408 passed, `tests/flow` 327, `tests/flow/e5` 68 (자체 timeline 시험 15 포함).

## 1. 목적·범위·하지 않는 것

### 1.1 목적
1. **불안정 지표 시계열**: E04_039의 초별 군중 압력 P = ρ × Var(v)를 시간 축 그림으로 그려, 봉우리를 영상 장면과 눈으로 맞춰 볼 수 있게 한다. 정답이 없으므로 정확도는 주장하지 않는다 (`proposal.md:51`).
2. **기준값 민감도**: 서버 판정 클래스를 그대로 쓰는 Java 실행기로 실제 timeline을 재생하고, 기준값 격자마다 알림 수·경보 시간·첫 알림 초를 표로 낸다.
3. **유입 → 인원 증가 시간 차**: 상호상관과 사건 기준 두 방법으로 잰다. `proposal.md:136`의 "약 20~25초"는 측정 방법 기록이 없으므로(조사 F.1) E5 결과로 대체할 값을 제안한다.
4. **실제 서버 확인 (G2 통합 시험 첫 단계)**: 실제 E04_039 timeline으로 서버를 한 번 재생해, 낸 알림(종류·t)이 실행기 기본값 결과와 같은지 본다. 화면(웹)은 필요 없다.

### 1.2 범위
- 입력: 통합 분석 스크립트(`python -m src.counting.analyze`)가 만든 timeline (확정 6). 이유노에게 받거나 이 PC에서 돌린다(10장 A).
- 영상: E04_039·E05_035·E05_038 세 구역 (제안 P12, v1.4). 같은 명령을 구역마다 돌린다. 먼저 E04_039로 끝까지 확인한 뒤 E05 두 개를 붙인다(CLAUDE.md "기본 구역 1개로 먼저").
- 결과: `outputs/e5/` md·csv·png.

### 1.3 하지 않는 것
- 정답 클립 라벨, ROC, 재현율 목표, E7 절제 실험 (`proposal-detail.md`의 옛 설계).
- `src/counting/`·`infra/`·`docs/proposal.md`·`server/src/main/` 수정. 서버 기준값·규칙 변경은 결과를 본 뒤 별도 PR(12장).
- 서버 판정 규칙을 Python으로 다시 만드는 것 (확정 2).
- 서버에 없는 판정 변형(예: `pressure` null 건너뜀)의 민감도. 서버 동작을 바꿔야 하므로 결과 뒤 `[토론]`으로 남긴다(12장).
- 잡음 바닥 적용, `counterflow` 쓰기, `inflow_ratio` 정의 변경(흐름 모듈 범위).
- E05 오경보·속도 이상치 수정(`min_heads` 기본값, `analyze.py`의 `noise_var` 전달). 원인만 12.1절에 적고 수정은 별도 계획이다(v1.4).
- 통합 분석 스크립트(`src/counting/analyze.py`) 수정. E5는 그 출력만 읽는다(v1.4).
- 에이전트의 `bootRun` 실행. 서버 확인은 사용자가 한다(10장 C).
- pandas 사용 (numpy만, 확정 3).

## 2. 결정 표

### 2.1 확정 (사용자, 11-16·11-18. 다시 열지 않는다)
| # | 항목 | 결정 |
|---|---|---|
| 1 | 입력 데이터 | **(v1.4에서 6으로 대체)** 11-16: 통합 스크립트(결정 8)를 기다리지 않고 E5가 밀도와 흐름을 직접 돌린다 |
| 2 | 민감도 방식 | **Java 판정 클래스 재사용 (11-16 사용자).** 서버 판정 클래스(`TimelineLoader`·`ZoneRegistry`·`ZoneRuntime`·`ZoneGrader`·`AlertDetector`)를 그대로 쓰는 실행기를 서버 **test 소스셋**에 두고(bootJar에 들어가지 않음) Gradle 작업 `e5Sweep`으로 돌린다. `./gradlew test`·`check`에는 묶지 않는다. Python으로 규칙을 다시 만들지 않는다. 서버에 없는 변형은 격자에서 빼고 결과 뒤 `[토론]`으로 남긴다. 실제 서버를 한 번 재생해 실행기 기본값 결과와 대조한다(사용자 실행, G2 통합 시험 첫 단계) |
| 3 | 그림 | `matplotlib`를 `requirements.txt`에 버전 고정으로 추가(numpy 2.4.6과 호환), pandas 없이 numpy만. PNG는 `outputs/e5/`. 팀에 알린다. 설치 명령은 사용자에게 주고 실행하지 않는다 |
| 4 | 시간 차 | 상호상관과 사건 기준을 둘 다 보고한다. 상승 사건이 1~2개뿐이라는 한계를 적는다. `proposal.md:136`은 이유노 문서라 고치지 않고 바꿀 문장을 제안한다 |
| 5 | 폴더 배치 | E5 전용 코드는 `src/flow/e5/` 패키지에, 시험은 `tests/flow/e5/`에 둔다. 흐름 모듈 본체(`src/flow/*.py`)와 섞지 않는다. 시험 파일 이름은 `test_e5_` 접두사를 유지한다(4.1절) |
| 6 | 입력 = 통합 스크립트 출력 | **(11-18 사용자)** E5는 이유노 통합 분석 스크립트(`python -m src.counting.analyze`, main #53)가 만든 timeline을 쓴다. E5 자체 timeline 생성 진입점과 그 시험·전용 도우미는 지운다(8.1절 I3). 실행 기록은 통합 스크립트의 `outputs/e8/{video}_analysis_time.json`이 대신한다. `origin/main`을 `feat/flow-e5`에 병합한 뒤 지운다 |

### 2.2 제안 (사용자 점검 필요)
| # | 항목 | 제안 | 대안 | 이유 |
|---|---|---|---|---|
| P1 | E5 입력 진입점 방식 | **폐기 (v1.4, 확정 6).** E5 자체 진입점을 지우고 통합 스크립트 출력을 쓴다 | — | 통합 스크립트가 같은 구조(한 번의 영상 패스, 가운데 장 머리 점을 메모리로 흐름에 넘김)로 main에 들어왔다 |
| P2 | 입력 timeline 경로 | `data/processed/timeline/{video}.json` (통합 스크립트 `--out` 예시와 같음) | `data/processed/e5/{video}.json` | 서버 기본 설정(`application.yml:12-13`)이 바로 읽는다. 10장 C 서버 확인도 E04_039는 설정을 바꾸지 않고 된다. `data/`는 git 밖이라 다른 PC에 영향 없음 |
| P3 | 구역 P 대표값 | **판정 대상 셀(면적 ≥ 2㎡) 중 non-null `pressure`의 최댓값**. 그림에는 판정 대상 셀별 P를 회색 가는 선으로 함께 그린다 | 밀도 가중 평균 / 셀별 선만 | 서버 `INSTABILITY`는 판정 대상 셀 하나라도 넘으면 켜지고 구역 등급도 셀 최댓값이다 (`AlertDetector.java:29`, `ZoneGrader.java:76-81`). 최댓값이면 그림의 기준선 0.02와 바로 비교된다. 가중 평균은 국소 불안정을 묽혀 서버 판정과 맞지 않는다 |
| P4 | 불안정 격자 (Java 실행기) | `pressure` ∈ {0.005, 0.01, **0.02**, 0.04, 0.08}(0.25~4배, 2배 간격) × `seconds` ∈ {1, 2, **3**, 5} = **20행**. null 처리는 서버 규칙(연속을 끊음) 하나뿐이다. 서버에 없는 "null 건너뜀" 변형은 격자에서 빼고 결과 뒤 `[토론]`(12장)으로 남긴다. 근거 자료는 Python 셀 표의 끊김 통계(초과 연속이 null로 끊긴 수 vs 기준 이하로 끊긴 수)다. md에는 P 분포 백분위(p50·p90·p95·p99·최대)와 0.02의 백분위 위치를 함께 적는다 | 데이터 백분위를 기준으로 격자 | 고정 격자가 다른 영상(E05_035)과 비교된다. 백분위는 같은 데이터로 기준을 정하고 같은 데이터로 평가하게 되므로 격자에 넣지 않고 표로만 보인다. 건너뜀 변형을 Java로 내려면 서버 `InstabilityTracker`를 바꿔야 한다(범위 밖) |
| P5 | 유입 격자 (Java 실행기) | `ratio` ∈ {0.5, 0.55, **0.6**, 0.65, 0.7} × (창, `min_samples`) ∈ {(3, 2), **(5, 3)**, (10, 6)} × `min_count` ∈ {0, **3**, 5} = 45행. `off_seconds` 10 고정 | `off_seconds`도 격자 | 첫 알림 초와 알림 수는 `off_seconds`에 거의 영향받지 않는다(끄는 꼬리만 바뀜). `min_samples`는 기본 3/5 비율을 유지(가정). `min_count` 0은 "인원 조건 없음"이라 조건이 선행 시간을 얼마나 깎는지 보인다. 모두 `InflowSettings` 검사(`min_samples` ≤ 창, `min_count` ≥ 0)를 통과한다 |
| P6 | "경보 시간" 세는 법 (Java `SweepSummary`가 계산) | 주 지표 (a) `unstable_s` = 판정 대상 셀 중 `unstable`이 1개 이상인 초 수. 참고 (b) `critical_s` = 구역 등급 CRITICAL인 초 수(히스테리시스 꼬리 +10초 포함). 유입은 `inflow_on_s` = `inflowAlert`가 참인 초 수(끔 꼬리 포함). 첫 알림 초는 `INSTABILITY`·`GRADE_UP`·`INFLOW` 각각 | `GRADE_UP` 사건이 열린 초 (조사 D.7 (c)) | (a)는 기준값 효과만 보인다. (b)는 상황실 화면이 실제로 보이는 시간이다. (c)는 (b)와 거의 같고(+10초) 설명이 복잡해 뺀다 |
| P7 | 30초 창(T) 확인 (Python) | 저장된 `vx`·`vy`로 T ∈ {10, 30, 60}초 S를 다시 계산(`TemporalInstability`, `fill_flow_fields` 재사용)한다. T마다 **P 분포만**(non-null 비율, p95, 0.02 초과 비율) 낸다. T=30 재계산과 파일 값의 최대 차이를 함께 적어 방법을 검증한다. **T별 알림 수는 이번에 내지 않는다**(Java 재생이 필요, 12장 `[토론]`) | T별 timeline을 써서 `e5Sweep`으로 재생 | 영상 재실행이 없고 기존 함수 재사용이라 싸다 (조사 C.6). 알림 수까지 내려면 T별 timeline 파일과 Gradle 실행이 늘어 실행 순서가 복잡해진다 |
| P8 | 시간 차 세부 | 상호상관: x = 실행기 `ticks.csv`의 `inflow_avg`(서버 `InflowMonitor` 값 그대로), y = `count` 5초 가운데 이동평균의 가운데 차분(명/초). 지연 k ∈ −30…+60초, 쌍 ≥ 30개인 k만, 최대 r의 k. 사건 기준: t_in = `inflow_avg` > 0.6이 처음인 초(인원 조건 없음), t_alarm = 실행기 `alerts.csv`의 첫 `INFLOW` 초(기본값), t_cnt = 평활 `count`가 (i) 3명 이상, (ii) 기준선 + 상승 폭 10%, (iii) + 50%에 처음 닿는 초. 기준선 = t < 30 평활 `count` 중앙값, 상승 폭 = 최댓값 − 기준선. 시간 차 = t_cnt − t_in(양수면 유입이 앞섬), t_cnt − t_alarm | 원 `inflow_ratio`로 상관 / 기준 하나만 | 서버 평균과 같은 값이라 설명이 쉽다. 기준 3개로 값이 기준 선택에 얼마나 흔들리는지 보인다. 원 신호와 서버 경보를 둘 다 내면 "`count` ≥ 3 조건 때문에 경보는 t=47 전에 켜질 수 없다"(조사 F.3)가 표로 보인다 |
| P9 | 그림 구성 | 3장: `*_series.png`(위아래 3칸: P / `count` / 유입), `*_sweep.png`(불안정·유입 민감도), `*_lag.png`(상관 곡선 + 사건 표시). 한 축만 쓰고(이중 y축 금지) 패널을 나눈다. 글꼴은 Malgun Gothic → AppleGothic → NanumGothic → DejaVu Sans 순서로 있는 것 | 영어 라벨 | 팀 문서·발표가 한국어다. 글꼴이 없는 PC에서는 한글만 네모로 나오고 실행은 된다 |
| P10 | `scipy` 버전 고정 | `requirements.txt:12`를 `scipy==1.17.1`로 고정하자고 이유노에게 제안(직접 고치지 않음) | 그대로 둠 | 버전 없는 줄은 PC마다 다른 판이 깔린다. dry-run으로 numpy 2.4.6과 맞는 판을 확인했다 |
| P11 | 결과로 닫을 안건 | api-spec 10절 **#8** `counterflow` → "MVP 미사용"으로 닫기(흐름 모듈이 값을 쓰지 않아 자료가 없다). **#17** 2㎡ 기준 → 실제 셀 표로 닫기(왼쪽 열 4.0·4.0·4.0·2.6㎡ 모두 판정 대상). **#2** 0.02/3초 → 결과를 본 뒤. 서버 계획 `[토론]` 4(null이 연속을 끊음) → 끊김 통계를 본 뒤 | 모두 결과 뒤 | #8·#17은 결과 전에도 근거가 있다. 다만 #17은 실제 실행 md의 셀 표로 다시 확인한 뒤 닫는다 |
| P12 | 영상 (v1.4 수정) | E04_039 → E05_035 → E05_038 순서로 같은 명령(10장). 구역 ID `zone-e04-039`·`zone-e05-035`·`zone-e05-038`. E05 두 영상은 60~61초라 T=30이면 P가 약 31초만 나온다(t ≥ 29). 시간 차(3장)는 E05에서 쌍이 30개 남짓이라 "측정 불가"가 나올 수 있다 | E04_039만 | main #54로 E05 구역 설정이 생겼다. 이유노 리뷰(12.1절)가 E05 민감도 표를 요청했다 |
| P13 | 실행 기록 | **폐기 (v1.4, 확정 6).** 처리 시간·환경은 통합 스크립트가 `outputs/e8/{video}_analysis_time.json`에 남긴다. 실행 확인 요약값(pressure non-null 비율, 속력)은 D 보고서의 셀 표·P 분포와 10장 A-2 확인 명령으로 본다 | — | E5 쪽 별도 기록 파일이 필요 없다 |
| P14 | 장면 대조 메모 | 생성 md는 다시 돌리면 덮어쓰므로, 영상과 맞춘 해석은 사용자가 `outputs/e5/{video}_notes.md`에 손으로 쓴다(봉우리 초 표를 복사해 "영상에서 본 것" 열 추가) | 생성 md에 직접 | 다시 생성해도 해석이 지워지지 않는다 |
| P15 | 실행기 배선 | 조합마다 `CrowdsightProperties`를 새로 만들어 **서버와 같은 `TimelineLoader` → `ZoneRegistry` → `ZoneRuntime.tick()`** 경로로 재생한다. 실행기는 판정 객체를 직접 조립하지 않는다. 그래서 별도 "동등성 시험" 대신, 합성 fixture의 기본값 알림 순서를 손으로 계산한 시험을 둔다(8장 5단계) | timeline을 한 번 읽고 `ZoneRuntime`을 직접 조립 + 서버 경로와의 동등성 시험 | 서버 배선 코드(`ZoneRegistry.register`)를 그대로 쓰면 배선이 어긋날 수 없다. 조합 65개 × 파일 다시 읽기는 수 초다(가정). 대가는 조합마다 INFO 로그 3줄(타임라인 폴더·읽음·구역 등록)이다 |
| P16 | 실제 서버 알림 자료원 | `GET /api/zones/zone-e04-039/alerts`를 재생이 끝난 뒤 받아 `data/processed/e5/E04_039_server_alerts.json`에 저장. 보관 한도에 걸리지 않게 `--crowdsight.unacked-alert-limit=10000`으로 띄운다 | `crowdsight.alert-log` 파일 / 콘솔 INFO 로그 | **지시의 "alert log"는 확인(ack) 기록만 담는다**(0.2). 콘솔 로그는 줄을 잘라 붙여야 한다. REST는 JSON이라 그대로 비교된다 |
| P17 | 서버 확인 대조 방법 | `src/flow/e5/analysis.py`의 `compare_alerts`(순수 함수, `report.py`가 부름)가 서버 JSON과 실행기 `alerts.csv`를 (t, reason, level, value, cell_ids)로 비교하고, md 4절에 일치 여부·다른 행을 적는다 | 문서로 적은 수작업 대조 | 함수 약 20줄 + 시험 3개다. 알림이 수십 개여도 실수 없이 다시 돌릴 수 있고, 결과가 md에 증거로 남는다 |
| P18 | 서버 README | `server/README.md`에 `e5Sweep` 사용법 3줄 추가 | 계획 문서에만 | 새 Gradle 작업은 README 없이 찾기 어렵다 |

## 3. 전제: 사용자가 준비할 것

에이전트는 설치·다운로드·긴 실행·서버 실행을 하지 않는다. 아래는 사용자가 한다.

### 3.1 입력 timeline (v1.4)
| 방법 | 놓을 경로 | 비고 |
|---|---|---|
| (기본) 이유노에게 받기 | `data/processed/timeline/E04_039.json`, `E05_035.json`, `E05_038.json` | 통합 스크립트(`src.counting.analyze`) 출력이어야 한다. `meta.models.flow`가 `"farneback-cv2 head-r6"`인지 3.3 명령 2로 확인 |
| 이 PC에서 돌리기 | 같은 경로 (`--out`) | 아래 세 파일과 P2PNet 준비가 필요하다. `outputs/g1`·`outputs/e8` 추적 파일을 덮어쓰므로 실행 뒤 되돌린다(10장 A) |

이 PC에서 돌릴 때만 필요한 것:
| 무엇 | 놓을 경로 (코드 기준) | 근거 |
|---|---|---|
| 영상 `E04_039.mp4`·`E05_035.mp4`·`E05_038.mp4` (1920×1080) | `data/processed/g1/` | `analyze.py:3-5` 실행 예시, `camera_fit.py:5` |
| P2PNet 가중치 `SHTechA.pth` | `data/raw/weights/SHTechA.pth` | `eval_e1.py:30` `WEIGHTS` |
| P2PNet 공식 코드 | `third_party/CrowdCounting-P2PNet/` (그 안에 `models/` 폴더) | `eval_e1.py:28`, `:51` |

- 영상은 이유노에게 받는다(G1·E2에 쓴 같은 파일이어야 셀·밀도가 맞다). `third_party/`, `*.pth`는 git 제외다. P2PNet 가중치는 학술 연구 용도만 허용된다.
- 처리 시간(이유노 PC 기준, 0.1): E04_039 약 10.5분, E05_035·E05_038 각 약 18~19분.

### 3.2 설치 (승인 후 사용자가 실행)
main 병합 뒤 전체 시험(`tests/predict/test_ml_forecast.py`)과 통합 스크립트의 `ml` 예측기가 `scikit-learn`·`joblib`을 쓴다. 이 환경에는 둘 다 없다(0.1). `scipy`·`matplotlib`는 이미 있다.
```powershell
conda run -n crowdsight python -m pip install scikit-learn==1.9.1 joblib==1.6.0
```
- 버전은 main `requirements.txt`의 고정값이다(나예린 줄, E5가 바꾸지 않는다).
- dry-run 결과(설치 안 함): `cloudpickle-3.1.2 joblib-1.6.0 narwhals-2.29.0 scikit-learn-1.9.1 threadpoolctl-3.8.0`. **numpy·scipy는 바뀌지 않는다.**
- Java 쪽은 새 의존성이 없다(서버 test 소스셋의 기존 의존성만 쓴다).
- 팀 알림 (확정 3). 보낼 글 초안:
  > E5 그래프용으로 `matplotlib==3.11.2`를 `requirements.txt`에 추가했습니다(numpy만 쓰고 pandas는 안 씁니다). 설치: `pip install matplotlib==3.11.2`. 없으면 E5 그림 시험만 건너뜁니다. `scipy`는 버전이 없어 `scipy==1.17.1` 고정을 제안합니다(이유노 님 줄이라 확인 부탁드립니다).

### 3.3 준비 확인 명령 (PowerShell, 저장소 루트)
```powershell
# 1. 패키지 (네 개 모두 버전이 찍혀야 한다)
conda run -n crowdsight python -c "import scipy, matplotlib, sklearn, joblib; print(scipy.__version__, matplotlib.__version__, sklearn.__version__, joblib.__version__)"
# 2. 받은 timeline: 구역 ID, 흐름 모델, 길이, 셀 수
conda run -n crowdsight python -c "import json,sys; [print(f, m['zone_id'], m['models']['flow'], m['duration_s'], len(m['cells'])) for f in sys.argv[1:] for m in [json.load(open(f,encoding='utf-8'))['meta']]]" data/processed/timeline/E04_039.json data/processed/timeline/E05_035.json data/processed/timeline/E05_038.json
# 3. (이 PC에서 돌릴 때만) P2PNet 코드와 가중치
conda run -n crowdsight python -c "from src.counting.eval_e1 import load_p2pnet, WEIGHTS; load_p2pnet(WEIGHTS); print('p2pnet ok')"
```
- 명령 2 기대: `zone-e04-039 farneback-cv2 head-r6 180 12`, `zone-e05-035 … 61 …`, `zone-e05-038 … 60 …`(E05 셀 수는 구역 설정에 따름, 미확인). `flow`가 `none`이면 밀도만 돈 파일(`run_density`)이라 쓰지 않는다.

## 4. 파일 목록

```text
requirements.txt                          수정 (matplotlib==3.11.2 한 줄 추가. main 병합 뒤 scikit-learn·joblib 줄과 함께 있음)
src/flow/e5/
├─ __init__.py                            추가  모듈 docstring만: "E5 전용 실험 코드. 흐름 모듈 본체(src/flow/*.py)와 분리한다."
├─ analysis.py                            추가  P 시계열·셀 표·T 창 확인·시간 차 (numpy만, 파일 쓰기 없음, 판정 재생 없음)
└─ report.py                              추가  실행기 CSV 읽기·서버 알림 대조·md·csv·png 쓰기 (CLI)
tests/flow/e5/                            (__init__.py·conftest.py 없음, 4.1절)
├─ e5_helpers.py                          추가  합성 timeline·합성 실행기 CSV (시험용. v1.4에서 영상·검출기 도우미 삭제)
├─ test_e5_analysis.py                    추가
└─ test_e5_report.py                      추가  (PNG 시험만 matplotlib importorskip)
server/
├─ build.gradle                           수정  Gradle 작업 e5Sweep (JavaExec, test 런타임 클래스패스) 추가
├─ README.md                              수정  e5Sweep 사용법 3줄 (제안 P18)
└─ src/test/
   ├─ java/com/tripley/crowdsight/e5/
   │  ├─ E5Sweep.java                     추가  실행기 main: 읽기 → 격자 재생 → CSV 4개 (@Test 없음)
   │  ├─ SweepSummary.java                추가  재생 결과 요약 record (제안 P6)
   │  └─ E5SweepTest.java                 추가  실행기 시험 (./gradlew test에서 돈다)
   └─ resources/e5/
      └─ e5_sweep_v02.json                추가  합성 fixture timeline 40초 (7.2절)
outputs/e5/                               추가  (사용자 실행 결과. 9장)
docs/plans/flow_e5_plan.md                추가  (이 문서)
docs/research/e5_research.md              추가  (조사 문서, 이미 있음·미추적)
```
- 바꾸지 않는 것: `server/src/main/**`(판정·재생·설정·`application.yml`), `src/counting/*`(`analyze.py` 포함), `infra/*`, `src/predict/*`, `src/flow/*.py`(본체, `cells.py`·`timeline_flow.py`·`inflow.py`는 import만), `docs/proposal.md`, `outputs/g1/*`, `outputs/e8/*`.
- v1.4에서 지우는 것 (v1.3에서 만들었고 아직 main에 없음): E5 자체 timeline 생성 모듈과 그 시험 모듈, `e5_helpers.py`의 영상·검출기 도우미(8.1절 I3).
- `docs/roadmap.md`, `CLAUDE.local.md`는 stage하지 않는다.

### 4.1 import 규칙과 시험 폴더 (저장소 설정으로 확인)
- 설정: `pytest.ini`는 `pythonpath = .`, `testpaths = tests`, import mode 기본(prepend). `tests/` 아래에는 `__init__.py`가 하나도 없고 `conftest.py`는 루트와 `tests/predict/`(fixture용)뿐이다.
- 소스 import: 기존 시험처럼 저장소 루트 기준 절대 경로를 쓴다 (`tests/flow/test_inflow.py:11` `from src.flow.inflow import …`). 새 코드도 `from src.flow.e5.analysis import …`. `src/flow/e5/` 안 모듈끼리도 절대 경로(`report.py` → `from src.flow.e5.analysis import build_report, …`). 흐름 본체는 `from src.flow.run_flow import …` 등 그대로.
- 도우미 import: prepend 모드는 `__init__.py`가 없는 시험 파일의 폴더(`tests/flow/e5/`)를 `sys.path` 앞에 넣는다. 그래서 `from e5_helpers import make_timeline, write_runner_csvs`로 읽는다. `tests/predict/test_predict.py:4` `from predict_helpers import blob_series`와 같은 방식이다.
- 결정: **`tests/flow/e5/`에 `__init__.py`와 `conftest.py`를 두지 않는다.** 이유: (1) 지금 배치(패키지 없는 시험 폴더)와 같게 두면 위 도우미 import가 그대로 된다. (2) `__init__.py`를 넣으면 모듈 이름이 `e5.test_e5_…`가 되고 도우미도 `from e5.e5_helpers import`로 바꿔야 해 다른 폴더와 방식이 달라진다. (3) 도우미는 fixture가 아닌 일반 함수·클래스라 `conftest.py`가 필요 없다.
- 이름 규칙: prepend 모드에서 시험 모듈 이름은 파일 이름만이라 `tests/` 전체에서 겹치면 안 된다. 그래서 `test_e5_` 접두사와 `e5_helpers` 이름을 유지한다(`tests/flow/`에 같은 이름 없음 확인).
- `python -m src.flow.e5.report`는 저장소 루트에서 실행한다(`src/__init__.py`, `src/flow/__init__.py`가 있어 패키지 경로가 된다).
- Java 실행기 패키지는 `com.tripley.crowdsight.e5`(test 소스셋). 공개 API(`TimelineLoader.loadAll`, `ZoneRegistry`, `ZoneRuntime.tick`, 설정 record, `TestProperties`·`TimelineFixtures` 상수)만 쓴다. 패키지 전용(`TimelineLoader.load`)은 쓰지 않는다.

## 5. 데이터 흐름

```text
[A: timeline 받기 또는 python -m src.counting.analyze]  (이유노 코드. E5 코드 없음)
영상 {video}.mp4 ─ count_video (P2PNet) → 밀도 timeline + heads[t] (메모리만)
                 → analyze_video (Farneback, 기본 인자) → 흐름 필드
                 → fill_predictions (config.yaml 예측기) → density_pred_60s
                 → data/processed/timeline/{video}.json  (E04_039·E05_035·E05_038)
   부수: outputs/g1/{video}_counts.csv, outputs/e8/{video}_analysis_time.json (추적 파일, 10장 A)

[B: ./gradlew e5Sweep --args="<timeline> <out_dir>"]  (구역마다 수 초, server/에서, 사용자 실행)
timeline.json ─ 조합마다 CrowdsightProperties → TimelineLoader(검증) → ZoneRegistry
   → ZoneRuntime.tick() 끝까지 (ZonePlayer loop=false → ZoneGrader → AlertDetector)
   ├─ 불안정 격자 20행  → E04_039_sweep_instability.csv
   ├─ 유입 격자 45행    → E04_039_sweep_inflow.csv
   └─ 기본값 1회        → E04_039_ticks.csv (초별 판정), E04_039_alerts.csv (알림 순서)

[C: 서버 확인 (G2 통합 시험 첫 단계, 사용자 실행, 화면 불필요)]
bootRun --crowdsight.replay.loop=false --crowdsight.unacked-alert-limit=10000
   → 180초 재생(ENDED) → GET /api/zones/zone-e04-039/alerts
   → data/processed/e5/E04_039_server_alerts.json

[D: python -m src.flow.e5.report]  (수 초, 사용자 실행)
timeline.json + B의 CSV 4개 (+ C의 JSON)
   ├─ zone_pressure, 셀 표, P 분포 → E04_039_series.csv, E04_039_series.png
   ├─ recompute_pressure(T=10·30·60) → E04_039_window.csv
   ├─ lagged_corr, event_lags (inflow_avg는 ticks.csv) → E04_039_lag.csv, E04_039_lag.png
   ├─ 민감도 그림 (sweep CSV) → E04_039_sweep.png
   ├─ compare_alerts (C가 있으면) → md 4절
   └─ render_markdown → E04_039_e5.md
```
- B·D 파일 이름 앞부분은 timeline 파일 이름이다. E05_035·E05_038도 같은 이름 규칙(`E05_035_sweep_instability.csv` 등)으로 같은 `outputs/e5/`에 쌓인다.

## 6. 모듈 설계

공통 (Python): PEP 8, 줄 79자 이하(흐름 모듈 관례), 모든 함수 타입힌트 + 한국어 docstring, `(가정)`·`[토론]` 표기, 무작위 없음(시드 불필요, 결정적 출력). 시간은 경과 시간만 `time.perf_counter()`.

공통 (Java, CLAUDE.md `server/` 표): Java 21, 공백 4칸, 줄 120자, LF(`server/.editorconfig`), 공개 클래스·메서드 한국어 Javadoc, 식별자 영어, DTO는 `record`, 상태 있는 클래스는 `final` + 스레드 규칙 Javadoc, unchecked 예외 + 한국어 메시지, SLF4J(`@Slf4j`) 한국어 로그, JUnit Jupiter 6 + AssertJ, `XxxTest` + `@DisplayName("한국어")`. 실행기는 시각을 쓰지 않는다(CSV에 시각 없음). 그래서 `Clock`이 필요 없고 `Instant.now()`·`System.currentTimeMillis()`를 쓰지 않는다.

### 6.1 입력: 통합 스크립트 출력 (v1.4, E5 코드 없음)

v1.3까지 이 절은 E5 자체 timeline 생성 진입점이었다. 확정 6으로 지우고, `analysis.py`·`report.py`·`E5Sweep`이 통합 스크립트 출력에서 읽는 것만 적는다.

| 읽는 곳 | 필드 | 통합 스크립트에서 채우는 곳 |
|---|---|---|
| `analysis.cell_values`·`zone_pressure`·`pressure_quantiles`·`cell_table` | 셀 `density`·`pressure`, `meta.cells[].walkable_area_m2` | `count_video`, `analyze_video` |
| `analysis.recompute_pressure`·`recompute_check` | 셀 `vx`·`vy`·`density`·`pressure` | `analyze_video` (`save_timeline` 재반올림은 같은 자리수, 0.1) |
| `analysis.build_report` series·lag | 프레임 `count`·`inflow_ratio` | `count_video`, `analyze_video` |
| `report.render_markdown` | `meta.video_id`·`duration_s`·`models.counter`·`models.flow` | `count_video`, `analyze_video` (`"farneback-cv2 head-r6"`) |
| `E5Sweep` (서버 `TimelineValidator`) | 규격 v0.2 전체 | `validate_timeline`, `save_timeline` |

- `density_pred_60s`, `models.predictor`는 채워지지만 E5는 읽지 않는다.
- v1.3 진입점이 하던 일 중 남기지 않는 것: 실행 요약값과 `outputs/e5/` 실행 기록 md. 처리 시간·환경은 `outputs/e8/{video}_analysis_time.json`(통합 스크립트)이 대신한다. pressure non-null 비율은 D 보고서의 셀 표(`pressure_null_ratio`)가, 속력 확인은 10장 A-2 명령이 대신한다.
- 흐름 인자는 통합 스크립트가 정한다(`min_heads` 1, `noise_var` 없음). E5는 바꾸지 않는다(12.1절).

#### 데이터 규칙 점검 (CLAUDE.md "셀·구역 집계값만")
| 파일 | 담는 것 | 머리 좌표 |
|---|---|---|
| `data/processed/timeline/{video}.json` (통합 스크립트) | 완성 timeline (규격 키만) | 없음 |
| `outputs/e5/*` (실행기 CSV·보고서) | 구역·셀 집계, 설정별 집계, 알림 (t·사유·단계·값·셀 ID) | 없음 |
| `data/processed/e5/*_server_alerts.json` | 서버 알림 목록 (알림 ID·시각·문구 포함) | 없음 |

### 6.2 Java 실행기 `server/src/test/java/com/tripley/crowdsight/e5/`

#### `E5Sweep.java`
```java
package com.tripley.crowdsight.e5;

/**
 * E5 기준값 민감도 실행기. test 소스셋에 있어 bootJar에 들어가지 않고, @Test가 없어 ./gradlew test에서 돌지 않는다.
 * Gradle 작업 e5Sweep으로 실행한다: 인자 = 타임라인 파일, 출력 폴더 (상대 경로는 작업 폴더 server/ 기준).
 * 타임라인 하나를 서버와 같은 경로(TimelineLoader 검증 → ZoneRegistry 배선 → ZoneRuntime.tick)로 기준값 조합마다
 * 끝까지(반복 없음) 재생해 CSV 4개를 쓴다. Spring 컨텍스트 없이 설정 record를 직접 만든다. 판정 객체를 직접
 * 조립하지 않으므로 서버 배선과 어긋날 수 없다. 기본 조합은 TestProperties(= application.yml 기본값) 상수다.
 * 스레드 규칙: main 스레드 하나에서만 돈다. 상태 없음.
 */
@Slf4j
public final class E5Sweep {

    static final List<Double> PRESSURES = List.of(0.005, 0.01, 0.02, 0.04, 0.08);
    static final List<Integer> SECONDS = List.of(1, 2, 3, 5);
    static final List<Double> RATIOS = List.of(0.5, 0.55, 0.6, 0.65, 0.7);
    static final List<Window> WINDOWS = List.of(new Window(3, 2), new Window(5, 3), new Window(10, 6));
    static final List<Double> MIN_COUNTS = List.of(0.0, 3.0, 5.0);
    static final int OFF_SECONDS = 10;

    static final String TICKS_HEADER =
            "t,zone_grade,max_density,inflow_avg,inflow_alert,n_unstable,unstable_cells,events";
    static final String ALERTS_HEADER = "t,reason,level,value,cell_ids";
    static final String INSTABILITY_HEADER = "pressure,seconds,is_default," + SweepSummary.HEADER;
    static final String INFLOW_HEADER =
            "ratio,window_seconds,min_samples,min_count,off_seconds,is_default," + SweepSummary.HEADER;

    /** 유입 평균 창과 그 창의 최소 non-null 수 (제안 P5). */
    record Window(int seconds, int minSamples) {
    }

    private E5Sweep() {
    }

    /** 인자: 타임라인 파일, 출력 폴더. 파일 이름 앞부분은 타임라인 파일 이름(확장자 뺌)이다. */
    public static void main(String[] args) {
        if (args.length != 2) {
            throw new IllegalArgumentException("사용법: e5Sweep --args=\"<타임라인 파일> <출력 폴더>\"");
        }
        Path timeline = Path.of(args[0]);
        Path outDir = Path.of(args[1]);
        String stem = stem(timeline);
        List<ZoneStep> base = replay(timeline, TestProperties.GRADE, TestProperties.INSTABILITY,
                TestProperties.INFLOW);
        write(outDir.resolve(stem + "_ticks.csv"), TICKS_HEADER, tickRows(base));
        write(outDir.resolve(stem + "_alerts.csv"), ALERTS_HEADER, alertRows(base));
        write(outDir.resolve(stem + "_sweep_instability.csv"), INSTABILITY_HEADER, instabilityRows(timeline));
        write(outDir.resolve(stem + "_sweep_inflow.csv"), INFLOW_HEADER, inflowRows(timeline));
    }

    /** 서버 경로로 끝까지 재생한 초별 결과. 시작 tick에서 판정·알림이 초기화된다 (ZoneRuntime.java:41-45). */
    static List<ZoneStep> replay(Path timeline, GradeSettings grade, InstabilitySettings instability,
                                 InflowSettings inflow) {
        CrowdsightProperties props = props(timeline, grade, instability, inflow);
        ZoneRuntime zone = new ZoneRegistry(new TimelineLoader(TimelineFixtures.MAPPER, props), props)
                .all().getFirst();
        List<ZoneStep> steps = new ArrayList<>();
        for (Optional<ZoneStep> step = zone.tick(); step.isPresent(); step = zone.tick()) {
            steps.add(step.get());
        }
        return steps;
    }

    /** 파일 하나를 읽는 서버 설정. 판정 외 성분은 TestProperties 기본값, 반복은 끈다. */
    static CrowdsightProperties props(Path timeline, GradeSettings grade, InstabilitySettings instability,
                                      InflowSettings inflow) {
        Path abs = timeline.toAbsolutePath().normalize();
        return new CrowdsightProperties(abs.getParent().toString(), List.of(abs.getFileName().toString()),
                TestProperties.TIME_ZONE, new CrowdsightProperties.Replay(1000, false, TestProperties.SLOW_TICK_MS),
                grade, instability, inflow, TestProperties.UNACKED_ALERT_LIMIT, TestProperties.WS,
                TestProperties.ALERT_LOG, TestProperties.CORS);
    }

    /** 불안정 격자 20행 (제안 P4). 유입·등급은 기본값. */
    static List<String> instabilityRows(Path timeline) { /* PRESSURES × SECONDS, is_default = settings.equals(...) */ }

    /** 유입 격자 45행 (제안 P5). 불안정·등급은 기본값. */
    static List<String> inflowRows(Path timeline) { /* RATIOS × WINDOWS × MIN_COUNTS, off 10 */ }

    /** 초별 판정 행. n_unstable·unstable_cells는 판정 대상(eligible) 셀만, events는 "REASON:LEVEL"을 ;로 잇는다. */
    static List<String> tickRows(List<ZoneStep> steps) { … }

    /** 알림 행 (서버가 같은 초에 AlertStore.issue에 넘기는 순서). cell_ids는 ;로 잇는다. */
    static List<String> alertRows(List<ZoneStep> steps) { … }

    /** 머리줄 + 행을 UTF-8·LF로 쓴다. 폴더가 없으면 만든다. 실패하면 UncheckedIOException(한국어 메시지). */
    static void write(Path file, String header, List<String> rows) { … }
}
```
- 숫자 쓰기: `Double.toString`(예 `0.005`, `0.6599999999999999`), null은 빈칸, 등급·사유는 enum 이름, `is_default`·`inflow_alert`는 `true`/`false`.
- 저장 뒤 `log.info("저장 {} ({}행)", file, rows.size())`. 조합마다 `TimelineLoader`·`ZoneRegistry`의 INFO 로그 3줄이 함께 찍힌다(제안 P15 대가).

#### `SweepSummary.java`
```java
/**
 * 재생 결과 요약 (제안 P6). 첫 알림 초는 그 알림이 없으면 null이다(없을 수 있는 정수라 Integer).
 *
 * @param nInstability       INSTABILITY 알림 수
 * @param nGradeUp           GRADE_UP 알림 수
 * @param nInflow            INFLOW 알림 수
 * @param firstInstabilityT  첫 INSTABILITY 초
 * @param firstGradeUpT      첫 GRADE_UP 초
 * @param firstInflowT       첫 INFLOW 초
 * @param unstableS          판정 대상 셀 중 unstable이 1개 이상인 초 수 (경보 시간 a)
 * @param criticalS          구역 등급이 CRITICAL인 초 수 (히스테리시스 꼬리 포함, 경보 시간 b)
 * @param inflowOnS          유입 경보가 켜진 초 수 (끔 꼬리 포함)
 */
record SweepSummary(int nInstability, int nGradeUp, int nInflow, Integer firstInstabilityT, Integer firstGradeUpT,
                    Integer firstInflowT, int unstableS, int criticalS, int inflowOnS) {

    static final String HEADER = "n_instability,n_grade_up,n_inflow,first_instability_t,first_grade_up_t,"
            + "first_inflow_t,unstable_s,critical_s,inflow_on_s";

    /** 초별 재생 결과에서 만든다. */
    static SweepSummary of(List<ZoneStep> steps) { … }

    /** HEADER 순서의 CSV 값 (null은 빈칸). */
    String toCsv() { … }
}
```

#### Gradle 작업 (`server/build.gradle` 끝에 추가)
```groovy
// E5 기준값 민감도 실행기 (조영준). test 소스셋 클래스라 bootJar에 들어가지 않고, test·check에 묶지 않는다.
// 사용 (server/): ./gradlew e5Sweep --args="../data/processed/timeline/E04_039.json ../outputs/e5"
tasks.register('e5Sweep', JavaExec) {
    description = 'E5: 타임라인을 서버 판정 클래스로 기준값 조합마다 재생해 CSV로 쓴다'
    classpath = sourceSets.test.runtimeClasspath
    mainClass = 'com.tripley.crowdsight.e5.E5Sweep'
}
```
- `sourceSets.test.runtimeClasspath`는 test 컴파일 결과를 담고 있어 Gradle이 `compileTestJava`를 먼저 돌린다. 작업 폴더 기본값은 `server/`라 상대 경로는 서버 설정(`timeline-dir: ../data/...`)과 같은 기준이다.
- `check`·`test`에 `dependsOn`을 걸지 않는다. 그래서 `./gradlew build`에서 돌지 않는다.

### 6.3 `src/flow/e5/analysis.py`

파일을 쓰지 않는 순수 함수만 둔다(numpy만). 판정 규칙(불안정 연속·유입 평균·히스테리시스·알림)은 계산하지 않는다. 그 값은 실행기 CSV에서 읽는다.

```python
from src.flow.cells import TemporalInstability
from src.flow.inflow import boundary_inward
from src.flow.timeline_flow import fill_flow_fields
from src.predict.schema import validate_timeline


def load_timeline(path: Path) -> dict:
    """timeline.json을 읽어 validate_timeline으로 확인한 dict."""


def cell_values(timeline: dict, key: str) -> np.ndarray:
    """(T, n) float 배열. null은 NaN. key는 density·pressure 등."""


def eligible_mask(timeline: dict, min_area_m2: float = 2.0) -> np.ndarray:
    """(n,) bool. walkable_area_m2 ≥ min_area_m2 (서버 min-walkable-area-m2 기본값)."""


def zone_pressure(
    timeline: dict, min_area_m2: float = 2.0,
) -> np.ndarray:
    """(T,) 구역 P = 판정 대상 셀 non-null pressure 최댓값 (제안 P3).

    판정 대상 셀이 모두 null이면 NaN.
    """


def pressure_quantiles(
    timeline: dict, threshold: float = 0.02, min_area_m2: float = 2.0,
) -> dict[str, float | int | None]:
    """판정 대상 셀-초 non-null P의 p50·p90·p95·p99·max, 표본 수,
    threshold 초과 비율, threshold의 백분위 위치. 표본 0이면 값은 None.
    """


def streak_breaks(
    pressures: Sequence[float | None], threshold: float,
) -> tuple[int, int]:
    """기준 초과 연속(길이 ≥ 1)이 끝난 원인을 센다 (자료 기술, 판정 아님).

    (null로 끊김, 기준 이하로 끊김). 시계열 끝에서 끝난 연속은 세지
    않는다. null 건너뜀 [토론](12장) 자료.
    """


def peak_times(
    series: np.ndarray, k: int = 5, min_gap_s: int = 10,
) -> list[tuple[int, float]]:
    """값이 큰 순서로 서로 min_gap_s초 이상 떨어진 (t, 값) k개. NaN 무시."""


def cell_table(timeline: dict, threshold: float = 0.02) -> list[dict]:
    """셀별 cell_id, area_m2, eligible, boundary(boundary_inward 재사용),
    pressure_null_ratio(t ≥ 29이고 density > 0인 초 중 null 비율),
    breaks_null, breaks_below (안건 #17·[토론] 근거).
    """


T_WINDOWS = (10.0, 30.0, 60.0)


def recompute_pressure(timeline: dict, window_s: float) -> dict:
    """저장된 vx·vy로 창 window_s초 speed_var·pressure를 다시 낸 사본.

    셀 순서대로 (vx, vy)를 넣는다(둘 중 하나라도 null이면 NaN).
    TemporalInstability(n, window_s)로 S를 내고 fill_flow_fields(cells,
    v, S, quality=(v 유한)·1, min_quality=1)로 같은 반올림 규칙을 쓴다.
    입력은 바꾸지 않는다. vx·vy가 0.01 m/s로 반올림돼 있어 원래 값과
    약 1.7×10⁻⁵ m²/s² 차이가 날 수 있다 (조사 C.6).
    """


def recompute_check(timeline: dict) -> dict[str, float | int]:
    """T=30 재계산 pressure와 파일 pressure 비교: 둘 다 숫자인 셀-초 수,
    최대 절대 차이, 한쪽만 null인 셀-초 수 (방법 검증, 제안 P7).
    """


def window_stats(timeline: dict, threshold: float = 0.02) -> list[dict]:
    """T ∈ T_WINDOWS마다 재계산한 판정 대상 P의 non-null 비율, p95,
    threshold 초과 비율 (제안 P7. 알림 수는 내지 않는다).
    """


def smooth(x: np.ndarray, window: int) -> np.ndarray:
    """가운데 이동평균(window 홀수). 창이 넘치는 끝과 NaN이 섞인 창은
    NaN. window가 짝수거나 1보다 작으면 ValueError.
    """


def count_rate(count: np.ndarray, window: int = 5) -> np.ndarray:
    """smooth(count, window)의 가운데 차분 (명/초). 양 끝은 NaN."""


def lagged_corr(
    x: np.ndarray, y: np.ndarray, lags: Sequence[int],
    min_pairs: int = 30,
) -> list[dict]:
    """지연 k마다 x[t]와 y[t+k]의 피어슨 r. k > 0이면 x가 k초 앞섬.

    둘 다 유한한 쌍만 쓴다. 쌍 < min_pairs이거나 한쪽 분산이 0이면
    r은 None. 행 = {"lag_s", "r", "n_pairs"}.
    """


def best_lag(rows: Sequence[dict]) -> dict | None:
    """r이 가장 큰 행. r이 모두 None이면 None."""


def first_index(mask: np.ndarray) -> int | None:
    """처음 True인 위치. 없으면 None."""


def event_lags(
    inflow_avg: np.ndarray,
    count_s: np.ndarray,
    t_alarm: int | None,
    ratio: float = 0.6,
    abs_count: float = 3.0,
    fractions: Sequence[float] = (0.1, 0.5),
    baseline_s: int = 30,
) -> list[dict]:
    """사건 기준 시간 차 표 (제안 P8).

    inflow_avg는 실행기 ticks.csv 값(서버 InflowMonitor 평균)이다.
    t_in = 처음 inflow_avg > ratio인 초. count_s(평활 count)의 기준
    (i) ≥ abs_count, (ii)(iii) ≥ 기준선 + f × (최댓값 − 기준선),
    기준선 = count_s[:baseline_s]의 nanmedian. 행 = {"criterion",
    "level", "t_cnt", "t_in", "lag_signal_s", "t_alarm", "lag_alarm_s"}.
    한쪽이 None이면 시간 차도 None.
    """


def compare_alerts(
    server: Sequence[dict], runner: Sequence[dict],
) -> dict:
    """서버 알림(REST JSON 원소)과 실행기 alerts.csv 행을 순서대로 비교.

    비교 키: t, reason, level, cell_ids(목록), value(둘 다 None이거나
    차이 ≤ 1e-9). 결과 = {"match": bool, "n_server", "n_runner",
    "diffs": [(순번, 서버 행, 실행기 행)]}. 서버 JSON의 다른 키(ID·시각·
    문구)는 보지 않는다 (제안 P17).
    """


def build_report(
    timeline: dict,
    ticks: Sequence[dict],
    alerts: Sequence[dict],
    sweep_instability: Sequence[dict],
    sweep_inflow: Sequence[dict],
    server_alerts: Sequence[dict] | None = None,
) -> dict:
    """보고서에 쓸 값을 모두 계산한 dict (파일 쓰기 없음).

    ticks·alerts·sweep_*는 실행기 CSV를 읽은 행(문자열 dict)이다.
    키: series(초별 행), cells, quantiles, peaks, window, recompute_check,
    lag_rows, best_lag, events, sweep_instability, sweep_inflow,
    default_instability·default_inflow(is_default 행), server_check
    (server_alerts가 None이면 None), meta(video_id, duration_s, models,
    n_cells, n_eligible).
    """
```
- `series` 행(Python 쪽 값만, 판정 열은 실행기 `ticks.csv`): `t, count, count_smooth, count_rate, inflow_ratio, zone_pressure, n_pressure`(판정 대상 중 non-null 셀 수).

### 6.4 `src/flow/e5/report.py`

```python
from src.flow.e5.analysis import build_report, load_timeline
from src.predict.io import assert_not_raw

TICKS_COLUMNS = ("t", "zone_grade", "max_density", "inflow_avg",
                 "inflow_alert", "n_unstable", "unstable_cells", "events")
ALERTS_COLUMNS = ("t", "reason", "level", "value", "cell_ids")
SUMMARY_COLUMNS = ("n_instability", "n_grade_up", "n_inflow",
                   "first_instability_t", "first_grade_up_t",
                   "first_inflow_t", "unstable_s", "critical_s",
                   "inflow_on_s")


def read_runner_csv(path: Path, columns: Sequence[str]) -> list[dict]:
    """실행기 CSV를 읽는다. 머리줄에 columns가 모두 없으면 ValueError
    (Java 머리줄과의 약속, 9.1절). 값은 문자열 그대로, 빈칸은 None.
    """


def write_csv(path: Path, rows: Sequence[dict]) -> None:
    """첫 행 키를 머리줄로 CSV를 쓴다. None은 빈칸, bool은 0/1.
    float는 repr 그대로(결정적). 행이 없으면 머리줄 없이 빈 파일.
    """


def render_markdown(report: dict, timeline_path: str) -> str:
    """9.2절 구성의 md 문자열. 기본 설정 행은 굵게 표시."""


def plot_series(report: dict, ticks: Sequence[dict], path: Path) -> None:
    """3칸 그림 (제안 P9). 위: 판정 대상 셀 P(회색 가는 선) + 구역 P
    (파랑 #2a78d6) + 기준 0.02(회색 점선, "기준 0.02 (문헌 참고선)") +
    불안정 초 음영(ticks n_unstable > 0, #d03b3b, 투명 0.12). 가운데:
    count + 3명 점선. 아래: inflow_ratio 점(주황 #eb6834) + inflow_avg
    선(파랑, ticks) + 0.6 점선 + 유입 경보 초 음영(ticks inflow_alert,
    #fab219, 투명 0.2). x축 10초 간격 눈금.
    """


def plot_sweep(report: dict, path: Path) -> None:
    """2칸. 왼쪽: x = pressure 기준(로그), y = unstable_s, seconds별 선
    4개(색 순서 #2a78d6·#eb6834·#1baf7a·#eda100), 기본점 검은 테두리.
    오른쪽: x = ratio, y = first_inflow_t(창 5), min_count별 선.
    """


def plot_lag(report: dict, path: Path) -> None:
    """3칸. 지연별 r(최대 지점 세로선) / inflow_avg와 t_in 표시 /
    평활 count와 t_cnt(50%) 표시. 이중 y축 없음.
    """


def write_report(
    timeline_path: Path,
    sweep_dir: Path,
    out_dir: Path,
    server_alerts_path: Path | None = None,
) -> list[Path]:
    """timeline과 sweep_dir의 {timeline 파일 이름}_ticks·_alerts·
    _sweep_instability·_sweep_inflow.csv(+ 서버 JSON)를 읽어 9.1절 D 파일을 모두 쓰고 경로
    목록을 돌려준다. out_dir이 data/raw 아래면 PermissionError
    (assert_not_raw). 실행기 CSV가 없으면 FileNotFoundError(먼저
    e5Sweep을 돌리라는 한국어 메시지).
    """


def main() -> None:
    """CLI: --timeline, --sweep-dir(기본 = --out), --server-alerts(선택),
    --out(기본 outputs/e5).
    """
```
- `matplotlib`는 `_pyplot()` 도우미 안에서만 import한다(`matplotlib.use("Agg")`, 글꼴 목록 중 설치된 첫 글꼴 + `"DejaVu Sans"`, `axes.unicode_minus = False`). 그래서 md·csv 시험은 matplotlib 없이 돈다.
- 그림 규칙: 한 축만, 2개 이상 계열이면 범례, 선 두께 1.5 이하, 기준선은 회색 점선, 상태색(빨강·노랑)은 경보 음영에만 쓴다. `dpi=150`, `figsize` 가로 12인치.

## 7. 시험 고정값

실제 원본 자료는 시험에 쓰지 않는다. 모두 합성이다.

### 7.1 Python (`tests/flow/e5/e5_helpers.py`)
```python
def make_timeline(
    areas: Sequence[float],
    density: Sequence[Sequence[float]],
    pressure: Sequence[Sequence[float | None]],
    inflow: Sequence[float | None],
    count: Sequence[float | None],
    vx: Sequence[Sequence[float | None]] | None = None,
    vy: Sequence[Sequence[float | None]] | None = None,
) -> dict:
    """규격 v0.2 모양의 합성 timeline. 셀 i는 c-00{i:02d}, row 0,
    col i, image_polygon은 화면을 가로로 n등분한 사각형.
    density[t][i] 등 t 우선. vx·vy가 None이면 모두 null.
    validate_timeline을 통과한다.
    """


def write_runner_csvs(
    out_dir: Path, stem: str, ticks: Sequence[dict],
    alerts: Sequence[dict], instability: Sequence[dict],
    inflow: Sequence[dict],
) -> None:
    """실행기 CSV 4개를 Java와 같은 머리줄(9.1절)로 쓴다 (report 시험용)."""
```
- v1.4: 도우미는 위 두 함수와 머리줄 상수(`TICKS_HEADER`·`ALERTS_HEADER`·`SUMMARY_HEADER`·`INSTABILITY_HEADER`·`INFLOW_HEADER`)만 남긴다. 영상·검출기·합성 구역 설정 도우미와 그 상수(합성 영상 크기, 셀 중심 좌표)는 지워진 시험 모듈만 썼다(`grep` 확인, 8.1절 I3). 남는 import는 `csv`, `Sequence`, `Path`다(`cv2`·`numpy` 삭제).

손 계산 고정값:
- **T=2 재계산**: density 1.0, vx [0, 1, 0, 1], vy 0 → t0 null, t1~t3 speed_var 0.25, pressure 0.25.
- **시간 차**: 100초. x = 1(20 ≤ t < 30) 아니면 0, y = x를 15초 뒤로 민 것 → `best_lag` k = 15, r ≈ 1.0.

### 7.2 Java fixture (`server/src/test/resources/e5/e5_sweep_v02.json`)
`valid_v02.json` 형식(v0.2, 검증기 통과). `zone_id` `zone-e5-test`, `camera_id` `cam-e5-test`, `video_id` `E5_TEST`, 40초, `prediction.history_s` 30. 셀 2개:

| 셀 | 면적 | density | pressure | 그 밖 셀 필드 |
|---|---|---|---|---|
| `c-0000` (판정 대상) | 4.0 | 모든 t 1.0 | t0~t3, t30~t33: 0.03, 그 밖 0.0 | null |
| `c-0102` (작은 셀) | 1.5 | 모든 t 1.0 | t0~t5: 0.03, 그 밖 0.0 | null |

프레임: `count` 모든 t 5.0, `inflow_ratio` t0~t9 null, t10~t14 0.8, t15~t39 0.1.

기본값(0.02/3초, 2/10, 유입 0.6/5/3/10/3) 손 계산:
- 불안정: `c-0000` t2·t3·t32·t33 불안정. `c-0102`는 t2~t5 불안정이나 판정 대상이 아니라 알림·구역 등급에서 빠진다.
- 등급: t3 CRITICAL(관측 t2·t3) → t13 ALERT(t4~t13 정상 10개) → t23 CAUTION → t33 CRITICAL(관측 t32·t33). t39까지 CRITICAL.
- 유입: 평균 t12 = 0.8(창 t8~t12 non-null 3개) → 켬. t15 0.66(켜짐 유지), t16 0.52부터 거짓 → t25에 끔(10초 연속 거짓).
- **알림 순서**: (t2, INSTABILITY, CRITICAL, 0.03, [c-0000]), (t3, GRADE_UP, CRITICAL, 1.0, [c-0000]), (t12, INFLOW, CAUTION, 0.8, []), (t32, INSTABILITY, CRITICAL, 0.03, [c-0000]), (t33, GRADE_UP, CRITICAL, 1.0, [c-0000]).
- **요약**: `SweepSummary(2, 2, 1, 2, 3, 12, 4, 17, 13)` (critical_s = t3~t12 10초 + t33~t39 7초, inflow_on_s = t12~t24).

격자 손 계산:
| 조합 | 기대 |
|---|---|
| 불안정 (0.04, 3) | 알림 0, 첫 초 모두 null(유입 제외), unstable_s 0 |
| 불안정 (0.02, 1) | first_instability_t 0, first_grade_up_t 1 |
| 불안정 (0.02, 5) | n_instability 0 (연속 최대 4초. 작은 셀은 t4에 불안정이지만 판정 대상 아님) |
| 유입 (0.6, (3, 2), 3) | first_inflow_t 11 (창 t9~t11 non-null 2개) |
| 유입 (0.6, (10, 6), 3) | first_inflow_t 15 (평균 (0.8×5 + 0.1)/6 = 0.683) |
| 유입 (0.7, (10, 6), 3) | first_inflow_t null |
| 유입 (0.6, (5, 3), 5) | first_inflow_t 12 (`count` 5 ≥ 5) |

## 8. TDD 순서

단계마다 **빨강(시험 먼저, 실패 확인) → 초록 → 정리**. 단계 끝마다 그 언어의 명령이 모두 통과해야 다음 단계로 간다. Python 시험 모듈 docstring에 시험 경계와 손 계산 방식을 한국어로 적는다(`tests/flow/test_inflow.py:1-4` 형식). 시험 함수는 `-> None` + 한국어 docstring. Java 시험은 영어 camelCase + `@DisplayName("한국어")`.

```powershell
# Python (저장소 루트)
conda run -n crowdsight python -m pytest tests/flow -m "not slow" -q
```
```bash
# Java (Git Bash, server/)
cd /c/Users/Woori/Desktop/project/Triple-Y/server && JAVA_HOME="/c/Program Files/Eclipse Adoptium/jdk-21.0.13.9-hotspot" ./gradlew test --tests '<패턴>' --no-daemon
```
> **에이전트는 `bootRun`을 실행하지 않는다.** 실제 E04_039로 `e5Sweep`을 돌리는 것도 사용자 몫이다(입력 파일이 사용자 실행 A의 결과). 8단계의 fixture 스모크 실행(수 초)만 에이전트가 한다.

| 단계 | 시험 먼저 | 구현 | 완료 조건 |
|---|---|---|---|
| 0 | — | 준비 확인: `git branch --show-current` = `feat/flow-e5`, `git status --short`가 `?? CLAUDE.local.md`·`?? docs/research/e5_research.md`·`?? docs/roadmap.md`·`?? docs/plans/flow_e5_plan.md`만. 3.3 명령 1이 통과 | Python 259 통과, Java `./gradlew test --no-daemon` 통과. **scipy·matplotlib가 없으면 멈추고 사용자에게 설치를 요청한다(에이전트는 설치하지 않는다)** |
| 1 | — | `requirements.txt` 끝에 `matplotlib==3.11.2  # E5 그래프 (src/flow/e5/report.py). numpy만 쓰고 pandas는 쓰지 않는다` | `git diff requirements.txt`가 한 줄 추가뿐 |
| 2~4 | **v1.4에서 삭제** (확정 6). v1.3의 E5 자체 timeline 생성 단계. 만든 코드·시험은 8.1절 I3에서 지운다. `src/flow/e5/__init__.py`는 남긴다 | — | — |
| 5 | `E5SweepTest`: fixture 7.2절 작성. (a) `replay`(기본값)가 40 step, 알림 순서가 7.2절 5개와 같음(사유·단계·값·셀), (b) 없는 파일 → `InvalidTimelineException`, (c) `count` 키를 지운 사본(@TempDir) → `InvalidTimelineException`(서버 검증기를 거침), (d) `props`가 반복 끔·부모 폴더·파일 이름을 담음 | `E5Sweep.replay`, `E5Sweep.props` | 4개 통과 (`--tests 'com.tripley.crowdsight.e5.*'`) |
| 6 | 같은 클래스: (a) `SweepSummary.of`(기본값) = `(2, 2, 1, 2, 3, 12, 4, 17, 13)`, (b) 알림 없는 재생 → 첫 초 null, `toCsv` 빈칸, (c) `instabilityRows` 20행·`is_default` true 1행(0.02, 3)·7.2절 격자 불안정 3행, (d) `inflowRows` 45행·기본 1행·7.2절 격자 유입 4행 | `SweepSummary`, `instabilityRows`, `inflowRows` | 통과 |
| 7 | 같은 클래스: (a) 네 머리줄 문자열이 9.1절과 정확히 같음, (b) `tickRows` 40행, t12 행 `events` `INFLOW:CAUTION`(켜지는 초에 알림), t13 행 `inflow_alert` true·`events` 빈칸, t3 행 `events` `GRADE_UP:CRITICAL`, t2 행 `unstable_cells` `c-0000`(작은 셀 빠짐), (c) `alertRows` 5행, `INFLOW` 행 `cell_ids` 빈칸, (d) `main(fixture, @TempDir)` → `e5_sweep_v02_ticks.csv`·`_alerts.csv`·`_sweep_instability.csv`·`_sweep_inflow.csv` 생김, 줄 끝 LF, (e) 인자 1개 → `IllegalArgumentException`, 메시지에 "사용법" | `tickRows`, `alertRows`, `write`, `main` | 통과 |
| 8 | (설정 단계, 명령으로 확인) | `build.gradle` `e5Sweep` 작업, `server/README.md` 3줄 | (1) `./gradlew test --no-daemon` 통과, (2) `./gradlew check --dry-run --no-daemon \| grep -c e5Sweep` → 0, (3) `./gradlew e5Sweep --args="src/test/resources/e5/e5_sweep_v02.json build/e5-smoke" --no-daemon` → `build/e5-smoke/`에 CSV 4개, (4) `./gradlew bootJar --no-daemon` 뒤 `"$JAVA_HOME/bin/jar" tf build/libs/crowdsight-server-0.0.1-SNAPSHOT.jar \| grep -c "crowdsight/e5"` → 0. **여기서 사용자에게 "실행 B·C(10장) 가능"을 알린다** |
| 9 | `test_e5_analysis.py`: `cell_values` null→NaN, `eligible_mask` 2.0 포함·1.99 제외, `zone_pressure` 판정 대상 최댓값·작은 셀 무시·모두 null이면 NaN, `pressure_quantiles` 손 계산(표본 [0.01, 0.02, 0.03, 0.04] 등), `streak_breaks` [0.03, 0.03, None, 0.03, 0.01] → (1, 1), 끝에서 끝난 연속 안 셈, `peak_times` 간격 규칙, `cell_table` 열·경계 셀, `load_timeline` 규격 위반 → `ValueError` | 해당 함수 | 통과 |
| 10 | `recompute_pressure` T=2 고정값, 입력 불변(깊은 비교), density 0 셀 pressure 0, T=30 재계산 == T=30으로 만든 파일 값(`recompute_check` 최대 차이 0, null 불일치 0), `window_stats` 3행 | `recompute_pressure`, `recompute_check`, `window_stats` | 통과 |
| 11 | `smooth` [0, 0, 3, 0, 0], 창 3 → [nan, 1, 1, 1, nan], 짝수 창 `ValueError`, `count_rate` 직선 2t → 안쪽 2.0, `lagged_corr` 펄스 15초 → `best_lag` 15·r ≈ 1(1e-9), 쌍 부족 → r None·`best_lag` None, `event_lags` t_in 20·t_cnt(50%) 35 → 15, 신호 없음 → None | lag 함수들 | 통과 |
| 12 | `test_e5_analysis.py`: `compare_alerts` 같음 → match, t 하나 다름 → diffs 1행, 서버 JSON의 다른 키 무시, value 1e-9 안 같음·None끼리 같음. `test_e5_report.py`: `read_runner_csv` 열 빠짐 → `ValueError`, 빈칸→None, `build_report` 키 목록(`write_runner_csvs`로 만든 합성 CSV), `write_csv` None→빈칸·bool→0/1·머리줄, `render_markdown`에 9.2절 제목·기본 행 굵게·서버 확인 절(있음/없음 두 경우), 같은 입력 두 번 → 같은 문자열 | `compare_alerts`, `build_report`, `read_runner_csv`, `write_csv`, `render_markdown` | 통과 (matplotlib 없이) |
| 13 | `test_e5_report.py`(`pytest.importorskip("matplotlib")`): `write_report`가 9.1절 D 파일을 모두 쓰고 PNG가 `\x89PNG`로 시작, 두 번 실행해 CSV·md 바이트 같음, 실행기 CSV 없음 → `FileNotFoundError`, `main` CLI(`sys.argv`), `data/raw` 출력 → `PermissionError` | `plot_*`, `write_report`, `main`, `_pyplot` | 통과 |
| 14 | — | 회귀·검증 (11장 표 전부) | 모두 기대대로 |

- 코드 단계는 2~13의 **12단계**다(v1.3 기준. 8단계는 Gradle 설정이라 명령으로 확인). 0·1은 준비, 14는 마무리 검증이다.
- 0~14는 v1.3에서 끝났다(구현·Reviewer 검토, 미커밋). v1.4 작업은 아래 8.1절이다.

### 8.1 v1.4: 커밋 → main 병합 → 자체 timeline 생성 제거 → 전체 시험

순서를 바꾸지 않는다. I1 커밋은 사용자 승인 뒤에만 한다(CLAUDE.md "커밋은 사용자가 요청할 때만").

| 단계 | 할 일 | 완료 조건 |
|---|---|---|
| I0 | 준비 확인: `git branch --show-current` = `feat/flow-e5`, `git fetch origin` 뒤 `git rev-parse origin/main` = `24537bb…`(다르면 새 병합 내용을 다시 보고 이 계획을 고친다). 병합 전 기준 시험 `conda run -n crowdsight python -m pytest tests -m "not slow" -q` | 408 통과, 5 제외 (v1.4 작성 시 측정. `tests/flow` 327, `tests/flow/e5` 68) |
| I1 | **사용자 승인 뒤** 15장 커밋 1~5를 순서대로 만든다. `docs/roadmap.md`, `CLAUDE.local.md`는 stage하지 않는다 | `git status --short`에 `?? CLAUDE.local.md`·`?? docs/roadmap.md`만 남음. `git log --oneline f0236fb..HEAD` 5줄 |
| I2 | `git merge origin/main` (아래 "병합 방식"). 충돌이 나면 아래 "예상 충돌"대로 푼다. 병합 커밋 메시지는 git 기본값 | `git log --oneline -1`이 병합 커밋, `git diff --stat origin/main HEAD -- src/counting src/predict infra web outputs docs/proposal.md`가 비어 있음(main 쪽을 그대로 받음) |
| I3 | 자체 timeline 생성 제거 (아래 "제거 내용"). 새 동작이 없어 빨강 단계는 없다. 대신 지우기 전·뒤 시험 수와 `grep`으로 확인한다 | `tests/flow/e5` 53 통과(68 − 15), `tests/flow` 312 통과(327 − 15), 아래 `grep` 0건 |
| I4 | 전체 시험 (병합된 트리). Python `conda run -n crowdsight python -m pytest tests -m "not slow" -q`, Java (Git Bash, `server/`) `JAVA_HOME=… ./gradlew test --no-daemon` | Python 실패·오류 0 (393 + main의 새 시험: `tests/counting/test_analyze.py`·`test_camera_fit.py` 각 2개, `tests/predict/test_ml_forecast.py` 16개 함수(일부 parametrize)). Java `BUILD SUCCESSFUL`. **`scikit-learn`·`joblib`가 없으면 `test_ml_forecast.py`가 실패한다. 그때 멈추고 3.2절 설치를 사용자에게 요청한다(에이전트는 설치하지 않는다)** |
| I5 | 11장 검증 표 + Reviewer 코드 리뷰(PR 전) | 11장 모두 기대대로 |

병합 방식: **merge** (rebase 아님). 이유: (1) I1 커밋은 v1.3 리뷰를 거친 단위라 그대로 둔다. rebase는 커밋 5개를 새로 만들고 충돌이 나면 커밋마다 다시 푼다. (2) 팀 PR이 병합 커밋 방식이라 이력 모양이 같다. (3) 아직 푸시 전이라 rebase도 안전하지만 얻는 것이 없다.

예상 충돌:
- `requirements.txt`만 양쪽이 고쳤다(main #56: `scikit-learn` 줄 주석 변경 + `joblib==1.6.0` 줄 추가, 우리: 끝에 `matplotlib==3.11.2` 줄 추가). 두 변경 사이에 바뀌지 않은 `streamlit` 줄이 있어 **자동 병합된다**. LF로 맞춘 사본에 `git merge-file`을 돌려 충돌 0을 확인했다(작업 트리는 CRLF지만 `core.autocrlf=true`라 커밋은 LF다). 결과 끝 4줄: `scikit-learn==1.9.1 … train_forecast.py도 사용`, `joblib==1.6.0 …`, `streamlit==1.67.0 …`, `matplotlib==3.11.2 …`.
- 충돌이 나면: main의 `scikit-learn`·`joblib` 두 줄을 그대로 두고, `matplotlib` 줄을 맨 끝에 한 번만 둔다. `git diff origin/main -- requirements.txt`가 `+matplotlib==3.11.2 …` 한 줄이어야 한다.
- 그 밖 파일은 충돌이 없다: main이 바꾼 71개 파일(`git diff --stat f0236fb origin/main`)에 `src/flow/`·`tests/flow/`·`server/`·`docs/plans/flow_e5_plan.md`·`docs/research/`가 없다.

제거 내용 (I3):
1. 지울 파일: `src/flow/e5/timeline.py`, `tests/flow/e5/test_e5_timeline.py` (`git rm`).
2. `tests/flow/e5/e5_helpers.py`에서 지울 것: `SYN_CFG`, `CENTRE_C0000`, `VIDEO_W`·`VIDEO_H`, `write_video`, `SeqDetector`, `ZeroFlow`, `import cv2`, `import numpy as np`. 남는 것: `make_timeline`, `write_runner_csvs`, `_write_rows`, 머리줄 상수 5개. 모듈 docstring 첫 문단을 "합성 timeline(규격 v0.2 모양)과 실행기 CSV 4개를 만든다."로 고친다(머리줄 약속 문장은 그대로).
   - 근거 (v1.4 `grep`): 위 이름은 `test_e5_timeline.py`와 `e5_helpers.py` 안에서만 쓰인다. `test_e5_analysis.py:18`은 `make_timeline`만, `test_e5_report.py:16`은 `make_timeline`·`write_runner_csvs`만 import한다. `numpy`는 지우는 도우미에서만 쓴다.
3. `src/flow/e5/analysis.py`·`report.py`는 바꾸지 않는다(자체 timeline 모듈을 import하지 않음, `FIRST_FULL_T`는 `analysis.py:21`에 따로 있음).
4. 확인 명령 (저장소 루트, Git Bash):
```bash
grep -rnIE "e5\.timeline|e5 import timeline|make_e5_timeline|build_density_timeline|run_summary|timeline_run|SeqDetector|ZeroFlow|SYN_CFG|\bwrite_video" src tests server/README.md   # 출력 없음
conda run -n crowdsight python -m pytest tests/flow -m "not slow" -q   # 312 passed
```

## 9. 출력 형식 (`outputs/e5/`)

### 9.1 파일
| 파일 | 만드는 곳 | 내용 |
|---|---|---|
| `E04_039_ticks.csv` | B (Java) | 기본값 초별 판정: `t,zone_grade,max_density,inflow_avg,inflow_alert,n_unstable,unstable_cells,events` |
| `E04_039_alerts.csv` | B (Java) | 기본값 알림 순서: `t,reason,level,value,cell_ids` |
| `E04_039_sweep_instability.csv` | B (Java) | 20행: `pressure,seconds,is_default,n_instability,n_grade_up,n_inflow,first_instability_t,first_grade_up_t,first_inflow_t,unstable_s,critical_s,inflow_on_s` |
| `E04_039_sweep_inflow.csv` | B (Java) | 45행: `ratio,window_seconds,min_samples,min_count,off_seconds,is_default,` + 같은 요약 9열 |
| `E04_039_e5.md` | D (Python) | 요약 (9.2절) |
| `E04_039_series.csv` | D | 초별: `t,count,count_smooth,count_rate,inflow_ratio,zone_pressure,n_pressure` |
| `E04_039_window.csv` | D | `window_s,nonnull_ratio,p95,over_ratio` |
| `E04_039_lag.csv` | D | `lag_s,r,n_pairs` |
| `E04_039_series.png`, `_sweep.png`, `_lag.png` | D | 6.4절 |
| `E04_039_notes.md` | 사용자 손 | 봉우리 초 표 + "영상에서 본 것" (제안 P14) |
- 실행기 CSV의 머리줄은 Python(`report.py` 열 상수)과 Java(`E5Sweep` 머리줄 상수)의 약속이다. 양쪽 시험이 같은 문자열을 확인한다(8장 7·12단계). 머리줄을 바꾸면 두 곳을 같이 고친다.
- 서버 알림 JSON(`data/processed/e5/E04_039_server_alerts.json`)은 실행마다 알림 ID·시각이 달라 올리지 않는다. 대조 결과만 md 4절에 남긴다.
- 원본 프레임 이미지·머리 좌표는 저장하지 않는다.
- E05_035·E05_038도 같은 파일 묶음이 앞부분만 바뀌어 생긴다(`E05_035_e5.md` 등).
- v1.4: E5 쪽 실행 기록 md는 없다(제안 P13 폐기). 처리 시간·환경은 통합 스크립트의 `outputs/e8/{video}_analysis_time.json`(이유노, git 추적)을 본다.

### 9.2 `E04_039_e5.md` 구성
```markdown
# E5 E04_039: 불안정 지표·기준값 민감도·유입 시간 차

| 항목 | 값 |
|---|---|
| timeline | data/processed/timeline/E04_039.json |
| 모델 | counter …, flow farneback-cv2 head-r6 |
| 길이·셀 | 180초, 셀 12개 (판정 대상 8개) |
| 서버 판정 | ./gradlew e5Sweep (서버 판정 클래스 그대로), 기본값 = application.yml |
| 환경 | numpy 2.4.6, matplotlib 3.11.2 |

정답 클립이 없어 감지 성능은 주장하지 않는다. 0.02/s²는 문헌 참고선이다.

## 1. 불안정 지표 P 시계열
그림 `E04_039_series.png`. (P 분포 표, 0.02의 백분위, 구역 P 봉우리 5개 표,
셀 표: 면적·판정 대상·경계·pressure null 비율·끊김 원인)

## 2. 기준값 민감도 (서버 판정 클래스 재생)
### 2.1 불안정 (20행 표, 기본 행 굵게)
### 2.2 유입 (창 5 행 표 15행; 전체는 CSV)
### 2.3 창 길이 T (3행 P 분포 + T=30 재계산 검증: 최대 차이, null 불일치)

## 3. 유입 → 인원 증가 시간 차
### 3.1 상호상관 (최대 r의 지연, r, 쌍 수. 표본 부족이면 "측정 불가")
### 3.2 사건 기준 (기준 3행 표: t_in, t_cnt, 신호 기준 차, 경보 기준 차)

## 4. 서버 확인 (G2 통합 시험 첫 단계)
(서버 알림 수, 실행기 알림 수, 일치 여부, 다른 행. 서버 JSON이 없으면 "하지 않음")

## 5. 한계
- 상승 사건이 1~2개라 시간 차는 일반화하지 않는다.
- 잡음 바닥을 빼지 않아 P에 측정 잡음이 들어 있다 (cells.py:84-86).
- 속도 축척 오차 k배 → P k²배 (가로 배율 5~10% 작을 수 있음,
  infra/homography/E04_039.json:52).
- E04_039 경계 셀은 화면 아래 줄 3개뿐이라 다른 방향 유입은 보지 못한다.
- 민감도는 서버가 가진 규칙만 바꿔 본 것이다. null 건너뜀 같은 변형은 없다.
```
- 해석(장면 대조, 기준값 판단)은 이 파일에 쓰지 않는다(다시 생성하면 지워진다). `E04_039_notes.md`와 PR 설명에 쓴다.

## 10. 사용자 실행 순서 (에이전트는 실행하지 않는다)

순서: **A timeline → B `e5Sweep` → C 서버 확인 → D 보고서.** v1.4에서 A만 바뀌었고 B·C·D는 같은 명령을 구역마다 돌린다. 8.1절 I4 뒤에 시작한다. 구역은 E04_039를 A~D 끝까지 먼저 하고, 그다음 E05_035·E05_038을 붙인다.

### A. timeline 받기 또는 만들기 (PowerShell, 저장소 루트)
**A-1 (기본) 이유노에게 받기**: 통합 스크립트 출력 `E04_039.json`·`E05_035.json`·`E05_038.json`을 `data/processed/timeline/`에 둔다. 3.3 명령 2로 `meta.models.flow`가 `farneback-cv2 head-r6`인지 확인한다.

**A-1' (대안) 이 PC에서 통합 스크립트 돌리기**: 3.1절 영상·가중치·P2PNet 코드가 있어야 한다. 이유노 PC 기준 E04_039 약 10.5분, E05 각 약 18~19분이다.
```powershell
conda activate crowdsight
python -m src.counting.analyze --homography infra/homography/E04_039.json --video data/processed/g1/E04_039.mp4 --out data/processed/timeline/E04_039.json
python -m src.counting.analyze --homography infra/homography/E05_035.json --video data/processed/g1/E05_035.mp4 --out data/processed/timeline/E05_035.json
python -m src.counting.analyze --homography infra/homography/E05_038.json --video data/processed/g1/E05_038.mp4 --out data/processed/timeline/E05_038.json
# 이유노의 추적 결과 파일을 덮어썼으므로 되돌린다 (E5 PR에 넣지 않는다)
git restore outputs/g1 outputs/e8
```
- `git status --short`에 `outputs/g1`·`outputs/e8` 변경이 없어야 한다. `--limit` 실행도 두 파일을 덮어쓰므로 같은 방법으로 되돌린다.
- 예측기는 `src/predict/config.yaml` 기본(`persistence`)을 쓴다. E5는 예측 값을 읽지 않으므로 `--predictor`를 주지 않는다.

**A-2 확인 (받은 파일이든 만든 파일이든)**: 속력 분포와 30초 창 뒤 pressure non-null 비율.
```powershell
python -c "import json,sys,numpy as np; [print(f, 'speed p50/p99/max', *np.round(np.percentile(s,[50,99,100]),2), 'pressure_nonnull', round(float(np.mean(late)),2)) for f in sys.argv[1:] for tl in [json.load(open(f,encoding='utf-8'))] for s in [np.array([np.hypot(c['vx'],c['vy']) for fr in tl['frames'] for c in fr['cells'] if c['vx'] is not None])] for late in [[c['pressure'] is not None for fr in tl['frames'][29:] for c in fr['cells'] if c['density']>0]]]" data/processed/timeline/E04_039.json data/processed/timeline/E05_035.json data/processed/timeline/E05_038.json
```
| 값 | 기대 | 어긋나면 |
|---|---|---|
| 셀 수 (3.3 명령 2) | E04_039 12 (판정 대상 8) | 다른 영상·구역 설정. 멈추고 이유노 확인 |
| `speed p50` | 약 0.3~1.5 m/s (가정) | 3 m/s 이상이면 행렬 부호·축척 문제 의심. 멈추고 이유노 확인 |
| `speed max` | E05는 6 m/s 넘는 값이 이미 보고됨(12.1절) | 기록만 한다. E5는 그대로 분석하고 `outputs/e5/{video}_notes.md`(손으로 쓰는 메모, 제안 P14)에 적는다. 생성 md는 바꾸지 않는다 |
| `pressure_nonnull` (t ≥ 29, density > 0) | 0보다 큼 | 머리가 적어 창을 못 채움 → 14장 위험 1행 |

### B. 기준값 민감도 (PowerShell, `server/`, 구역마다 수 초)
```powershell
$env:JAVA_HOME = 'C:\Program Files\Eclipse Adoptium\jdk-21.0.13.9-hotspot'
cd server
.\gradlew.bat e5Sweep --args="../data/processed/timeline/E04_039.json ../outputs/e5"
.\gradlew.bat e5Sweep --args="../data/processed/timeline/E05_035.json ../outputs/e5"
.\gradlew.bat e5Sweep --args="../data/processed/timeline/E05_038.json ../outputs/e5"
```
- `outputs/e5/`에 구역마다 `{video}_ticks.csv`·`_alerts.csv`·`_sweep_instability.csv`·`_sweep_inflow.csv`가 생긴다. 타임라인이 규격에 어긋나면 서버와 같은 `InvalidTimelineException` 메시지로 멈춘다.

### C. 서버 확인 (G2 통합 시험 첫 단계, 화면 불필요, 약 3분)
실제 timeline → 서버 재생 → 판정 → 알림까지가 실행기와 같은지 보는 첫 통합 확인이다. 웹 화면은 띄우지 않는다. 세 구역을 한 번에 띄운다(파일당 구역 1개, `application.yml:13`).
```powershell
# 창 1 (server/): 반복 끄고, 알림 보관 한도를 넉넉히, 세 구역
.\gradlew.bat bootRun --args='--crowdsight.replay.loop=false --crowdsight.unacked-alert-limit=10000 --crowdsight.timeline-files=E04_039.json,E05_035.json,E05_038.json'
# 로그에 세 구역 모두 "재생 상태 zone=… state=ENDED"가 나올 때까지 기다린다 (가장 긴 E04_039 180초)
# 창 2 (저장소 루트): 구역마다 낸 알림 전체를 받는다
New-Item -ItemType Directory -Force data/processed/e5 | Out-Null  # curl -o는 폴더를 만들지 않는다
curl.exe -s http://localhost:8080/api/zones/zone-e04-039/alerts -o data/processed/e5/E04_039_server_alerts.json
curl.exe -s http://localhost:8080/api/zones/zone-e05-035/alerts -o data/processed/e5/E05_035_server_alerts.json
curl.exe -s http://localhost:8080/api/zones/zone-e05-038/alerts -o data/processed/e5/E05_038_server_alerts.json
# 창 1에서 Ctrl+C
```
- 구역 ID는 `count_video` meta 규칙(`zone-{video 소문자, _→-}`)이다. 3.3 명령 2 출력으로 확인한다.
- `crowdsight.alert-log`(`server/logs/alerts.jsonl`)은 확인(ack) 기록만이라 쓰지 않는다(0.2, 제안 P16). 확인 버튼을 누르지 않았으므로 이 파일은 생기지 않는다.
- 콘솔의 `알림 zone=… t=… reason=… level=…` INFO 줄(`AlertStore.java:45`)은 눈으로 맞춰 보는 보조 자료다.

### D. 보고서 (PowerShell, 저장소 루트, 구역마다 수 초)
```powershell
python -m src.flow.e5.report --timeline data/processed/timeline/E04_039.json --sweep-dir outputs/e5 --server-alerts data/processed/e5/E04_039_server_alerts.json --out outputs/e5
python -m src.flow.e5.report --timeline data/processed/timeline/E05_035.json --sweep-dir outputs/e5 --server-alerts data/processed/e5/E05_035_server_alerts.json --out outputs/e5
python -m src.flow.e5.report --timeline data/processed/timeline/E05_038.json --sweep-dir outputs/e5 --server-alerts data/processed/e5/E05_038_server_alerts.json --out outputs/e5
```
- C를 건너뛰었으면 `--server-alerts`를 빼면 된다(md 4절에 "하지 않음").
- E05 `*_sweep_instability.csv`·`*_e5.md` 2절이 이유노 리뷰(12.1절)가 요청한 민감도 표다.

## 11. 검증 체크리스트 (14단계, v1.4는 8.1절 I5)

v1.4: main 병합·제거 뒤의 트리에서 돌린다. 비교 기준은 `main` 대신 `origin/main`(병합한 `24537bb`)이다. Python은 저장소 루트(Git Bash), Java는 `server/`(Git Bash, `JAVA_HOME` 지정).

| # | 명령 | 기대 |
|---|---|---|
| 1 | `conda run -n crowdsight python -m pytest tests -m "not slow" -q` | 실패·오류 0 (전체: counting·flow·predict 포함. `tests/flow` 312, `tests/flow/e5` 53) |
| 2 | `conda run -n crowdsight python -m pytest tests/flow/e5/test_e5_report.py tests/predict/test_ml_forecast.py -q -rs` | `SKIPPED` 없음 (matplotlib·scikit-learn·joblib 설치 확인) |
| 3 | `awk 'length > 79 {print FILENAME": "FNR}' src/flow/e5/*.py tests/flow/e5/*.py` | 출력 없음 |
| 4 | `grep -nE "^\s*def " src/flow/e5/*.py \| grep -v -- "->"` (여러 줄 시그니처는 눈으로) | 반환 타입힌트 빠진 함수 없음 |
| 5 | `grep -rnE "np\.save\|savetxt\|imwrite\|pickle" src/flow/e5/*.py` | 출력 없음 (머리 점·프레임 저장 없음) |
| 6 | `grep -rn "pandas" src/flow tests/flow requirements.txt` | 출력 없음 |
| 7 | `grep -rnE "Instant\|time\.time\(\)" src/flow/e5/*.py` | 출력 없음 (경과 시간은 `perf_counter`) |
| 8 | `./gradlew clean build --no-daemon` (server/) | `BUILD SUCCESSFUL` (기존 시험 + `E5SweepTest` 통과) |
| 9 | `grep -h -o 'tests="[0-9]*" skipped="[0-9]*" failures="[0-9]*" errors="[0-9]*"' build/test-results/test/*.xml` | 모든 줄 `failures="0" errors="0"` |
| 10 | `ls build/test-results/test/ \| grep -i e5` | `TEST-com.tripley.crowdsight.e5.E5SweepTest.xml`만 (실행기 `E5Sweep`은 시험으로 돌지 않음) |
| 11 | `./gradlew check --dry-run --no-daemon \| grep -c e5Sweep` | 0 (`check`에 묶이지 않음) |
| 12 | `./gradlew e5Sweep --args="src/test/resources/e5/e5_sweep_v02.json build/e5-smoke" --no-daemon && ls build/e5-smoke` | CSV 4개 |
| 13 | `./gradlew bootJar --no-daemon && "$JAVA_HOME/bin/jar" tf build/libs/crowdsight-server-0.0.1-SNAPSHOT.jar \| grep -c "crowdsight/e5"` | 0 (bootJar에 없음) |
| 14 | `grep -rnE "Instant\.now\|currentTimeMillis" src/test/java/com/tripley/crowdsight/e5` | 출력 없음 |
| 15 | 바뀐 `.java` 파일에 120자 초과 줄 없음 (`awk 'length > 120' src/test/java/com/tripley/crowdsight/e5/*.java`) | 출력 없음 |
| 16 | stage 뒤 `git -C .. ls-files --eol server \| grep -v 'i/lf'` | `gradle-wrapper.jar`, `gradlew.bat`만 |
| 17 | `git diff --stat origin/main -- server/src/main src/counting infra src/predict docs/proposal.md outputs/g1 outputs/e8 web` (저장소 루트) | 출력 없음 |
| 18 | `git diff origin/main -- requirements.txt` | `+matplotlib==3.11.2 …` 한 줄 |
| 19 | `git status --short` | `CLAUDE.local.md`·`docs/roadmap.md`가 stage되지 않음, `server/logs/`·`server/build/e5-smoke` 없음(build는 git 제외), `outputs/g1`·`outputs/e8` 변경 없음 |
| 19a | 8.1절 I3의 `grep -rnIE …` (src·tests·server/README.md) | 출력 없음 (자체 timeline 생성 흔적 0) |
| 19b | `git ls-files src/flow/e5 tests/flow/e5` | `__init__.py`·`analysis.py`·`report.py`, `e5_helpers.py`·`test_e5_analysis.py`·`test_e5_report.py`만 |
| 19c | `git log --oneline --merges origin/main..HEAD` | 병합 커밋 1개 (`origin/main` 병합) |
| 20 | (실행 D 뒤) `outputs/e5/E04_039_e5.md`의 셀 표 (E05 두 구역은 셀 수만 기록, 기대값 없음) | 셀 12개, 왼쪽 열 4.0·4.0·4.0·2.6㎡ 판정 대상, 경계 셀 `c-0000`·`c-0001`·`c-0002` (조사 A.6과 같음) |
| 21 | (실행 D 뒤) 세 md의 4절 | 구역마다 서버 알림과 실행기 알림이 같음. 다르면 다른 행을 보고 조영준이 원인 확인(타임라인 파일이 같은지 먼저) |
| 22 | (실행 D 두 번) D가 만든 CSV·md `md5sum` | 같음 (결정적) |

## 12. 결과 뒤 할 일 (TDD 범위 밖)

| 할 일 | 문서·파일 | 담당 | 비고 |
|---|---|---|---|
| 장면 대조 메모 | `outputs/e5/E04_039_notes.md` | 조영준 | 봉우리 초를 영상에서 보고 적는다 |
| 0.02/3초 판단 (api-spec 10절 #2) | `docs/api-spec.md` 10절 | 조영준 (이유노와) | 유지면 "닫힘 (E5): 유지, 근거 outputs/e5". 바꾸면 `application.yml:25-26` 값·주석과 `TestProperties`(기본값 = yml, `CrowdsightServerApplicationIntegrationTest`가 확인)를 같은 서버 PR에서 |
| `[토론]` null 건너뜀 변형 (서버 계획 `[토론]` 4, server_impl_plan #11) | `docs/api-spec.md` 4.3 | 조영준 | 서버에 없는 규칙이라 격자에서 뺐다. 셀 표의 끊김 통계(null로 끊김 vs 기준 이하)를 보고, 필요하면 `InstabilityTracker`를 바꾸는 서버 계획을 따로 세운다. 그 뒤 `e5Sweep`을 다시 돌리면 같은 표가 나온다 |
| `[토론]` T(창 길이)별 알림 수 | — | 조영준 | 이번에는 P 분포만 낸다(제안 P7). 필요하면 T별 timeline을 써서 `e5Sweep`에 넣는다 |
| `counterflow` (10절 #8) | `docs/api-spec.md` 10절 | 조영준 (이유노 확인) | "닫힘 (E5): MVP 미사용. 흐름 모듈이 값을 쓰지 않는다" |
| 2㎡ 기준 (10절 #17) | `docs/api-spec.md` 10절 | 조영준 (이유노 확인) | "닫힘 (E5): 실제 셀은 왼쪽 열 모두 판정 대상, 기준 유지" |
| G2 통합 시험 다음 단계 | — | 조영준·나예린·이유노 | 10장 C는 서버까지만 본다. 다음은 화면 연결, 알림 지연 p95(E8) |
| `timeline-spec.md` 4절 `counterflow` 문구 | `docs/timeline-spec.md` | **이유노** | 요청만 (불안정 판정에 쓰지 않음) |
| `proposal.md:136` "약 20~25초" | `docs/proposal.md` | **이유노** | 요청만. 초안: "E5(11-xx) 측정에서 `E04_039`의 유입 신호(5초 평균 > 0.6)는 인원 증가(기준선 + 50%)보다 X초 앞섰다(상호상관 최대 지연 Y초, r = Z). 상승 사건이 1개라 일반화하지 않는다." 원래 수치의 측정 방법도 함께 묻는다 |
| E05_035·E05_038 결과 정리 | `outputs/e5/E05_035_*`·`E05_038_*` | 조영준 | v1.4에서 10장 명령에 포함. 민감도 표를 12.1절 리뷰 답으로 이유노에게 전달 |
| E05 오경보·속도 이상치 수정 | 별도 계획 (12.1절) | 조영준 (흐름), 이유노 (`analyze.py`) | 이 계획 범위 밖 |

### 12.1 이유노 리뷰 (11-18): E05 오경보·속도 이상치 (참고, 수정은 범위 밖)
- 리뷰 내용 (사용자 전달): E05에서 (1) 머리가 드문 셀에서 `pressure` > 0.02 불안정 오경보, (2) 속력 이상치(6.4 m/s). 기준값 민감도 표를 요청했다.
- 코드로 본 원인 (v1.4 확인, 수정하지 않음):
  - `min_heads` 기본값 1 (`src/flow/run_flow.py:67`). 머리 1개만 있어도 셀 `vx`·`vy`가 채워지고 30초 창에 들어간다. 머리 하나의 패치 흐름 잡음이 그대로 `Var(v)`가 된다.
  - `noise_var`를 넘기지 않음 (`src/counting/analyze.py:56-58`, `run_flow.py:65` 기본 `None`). 잡음 바닥을 빼지 않아 `speed_var`·`pressure`에 측정 잡음이 남는다(`cells.py:84-86`).
- E5와의 관계: E5 `e5Sweep` 불안정 격자(`*_sweep_instability.csv`, md 2.1절)가 리뷰가 요청한 민감도 표다. md 1절 셀 표(면적·`pressure` null 비율)와 A-2 확인의 `speed max`가 원인 자료다. E5는 위 두 값을 바꾸지 않고 현재 통합 스크립트 출력을 그대로 잰다.
- 수정은 별도 계획에서 한다(이 계획에서 만들지 않음): (가) 흐름 쪽 `min_heads` 기본값·속력 상한 검토 (조영준, `src/flow/`), (나) `analyze.py`가 `noise_var`·`min_heads`를 넘기게 하기 (이유노 파일, 이유노 동의 필요). 수정 뒤 timeline을 다시 만들고 B~D를 다시 돌리면 전후 표가 나온다.

## 13. 통합 스크립트(결정 8)와의 관계, 이유노에게 알릴 것

- v1.4: 통합 스크립트(`src/counting/analyze.py`, #53)가 main에 들어와 E5는 그 출력만 읽는다(확정 6). E5 자체 timeline 생성은 지운다(8.1절 I3). 그래서 `run_density`와 겹치던 반복문도 없어진다.
- 이유노에게 알릴 것 (이 계획에서 고치지 않음):
  1. E5 결과는 통합 스크립트 출력(`min_heads` 1, `noise_var` 없음)을 잰 것이다. 12.1절 수정 뒤에는 timeline을 다시 받아 E5를 다시 돌린다.
  2. `analyze.py`는 `--limit` 실행에서도 추적 파일 `outputs/g1/{video}_counts.csv`·`outputs/e8/{video}_analysis_time.json`을 덮어쓴다. 다른 팀원이 돌릴 때 실수로 커밋하기 쉽다(제안만: 빠른 확인 실행은 기록하지 않기).
  3. `eval_e1.py:20` `import scipy.io`를 `gt_count` 안으로 옮기면 `run_density`가 scipy 없이 import된다.
  4. `requirements.txt` `scipy==1.17.1` 고정 (제안 P10).

## 14. 위험·가정

| 위험 | 대응 |
|---|---|
| 머리가 적은 셀은 30초 창 유효 24칸을 못 채워 `pressure`가 거의 null → 불안정이 켜지지 않음 | 셀 표의 null 비율로 보인다. 끊김 통계가 null 건너뜀 `[토론]` 자료가 된다. 정답이 아니라 결과 공개다 |
| t≈45 전 `inflow_ratio`가 대부분 null → 상호상관 쌍 부족 | `n_pairs` 열과 "측정 불가" 표시. 사건 기준 표는 그대로 나온다 |
| 이 PC에서 통합 스크립트를 돌리면 오래 걸림 (E05 각 약 18~19분, 이유노 PC) | 기본은 이유노에게 timeline을 받는다(10장 A-1) |
| 받은 timeline이 통합 스크립트 출력이 아님(밀도만, 옛 파일) | 3.3 명령 2로 `models.flow` = `farneback-cv2 head-r6`, 길이·셀 수 확인 |
| 통합 스크립트 실행이 추적 파일 `outputs/g1`·`outputs/e8`을 덮어써 E5 PR에 섞임 | 10장 A-1' 끝 `git restore outputs/g1 outputs/e8`, 검증 17·19번 |
| 이 환경에 `scikit-learn`·`joblib`가 없어 병합 뒤 `tests/predict/test_ml_forecast.py` 실패 | 8.1절 I4에서 멈추고 3.2절 설치를 사용자에게 요청 |
| `git merge origin/main`에서 `requirements.txt` 충돌 | 시뮬레이션으로 자동 병합 확인. 나면 8.1절 "예상 충돌" 규칙으로 푼다 |
| PR 전에 main이 또 바뀜 | I0에서 `origin/main` 해시를 확인하고, 바뀌었으면 PR 전에 한 번 더 병합한다 |
| E05 결과에 오경보·속도 이상치가 그대로 나옴 (12.1절) | 의도한 것: 현재 통합 스크립트 출력을 잰다. `{video}_notes.md`와 PR 설명에 12.1절 원인을 적고, 수정은 별도 계획 |
| E05가 60~61초라 30초 창 뒤 P가 약 31초, 상관 쌍 부족 | P 분포·민감도는 그대로 내고, 시간 차는 "측정 불가"로 둔다 |
| 실행기가 test 소스셋 도우미(`TestProperties`·`TimelineFixtures`)에 기댐 | 같은 소스셋이고 기본값이 yml과 같음을 기존 시험이 확인한다. 도우미가 바뀌면 `E5SweepTest`가 실패한다 |
| Python 열 상수와 Java 머리줄이 어긋남 | 양쪽 시험이 같은 문자열을 확인(8장 7·12단계), `read_runner_csv`가 열 빠짐을 `ValueError`로 알린다 |
| 실행기가 조합마다 파일을 다시 읽어 느림·로그가 많음 | 65회 × 180프레임 읽기는 수 초(가정). 로그는 INFO 3줄 × 66회로 많지만 결과에는 영향이 없다 |
| 서버 확인에서 알림이 보관 한도(기본 100)를 넘어 오래된 것이 버려짐 | `--crowdsight.unacked-alert-limit=10000`으로 띄운다 |
| 서버 확인을 `alert-log`로 하려는 오해 | 0.2·10장 C에 "확인 기록만"을 적었다. REST로 받는다 |
| `./gradlew test`가 실행기를 시험으로 돌림 | `@Test`가 없어 JUnit Platform이 고르지 않는다. 검증 10번으로 확인 |
| 같은 PC의 서버가 `data/processed/timeline/E04_039.json`을 읽음 | 의도한 것(제안 P2). 통합 스크립트 출력이라 서버 기본 재생과 같은 파일이다 |
| 다른 PC에 한글 글꼴 없음 | 글꼴 목록 대체, 한글만 네모. 실행은 됨 |
| matplotlib 없는 팀원 PC에서 시험 실패 | PNG 시험만 `importorskip`으로 건너뜀. 나머지는 그대로 |
| `count` 평활 10% 기준이 초반 잡음에 걸림 | 기준 3개를 함께 보여 기준 선택 영향을 드러낸다 |

가정:
- (가정) A-2 `speed p50` 기대 0.3~1.5 m/s (걷기 약 1.1 m/s, 서 있는 사람 섞임).
- (가정) 받은 timeline은 main `24537bb`의 통합 스크립트로 만든 것이다(흐름 인자 기본값).
- (가정) 유입 격자의 `min_samples`는 기본 3/5 비율 유지.
- (가정) 사건 기준 기준선은 t < 30 (E04_039 상승은 t≈40부터).

## 15. 커밋 제안 (커밋·푸시·PR은 사용자가 요청할 때만)
8.1절 순서를 따른다. I1(병합 전)에 1~5, I2에 병합 커밋, I3에 6, 실행 뒤 7.

병합 전 (I1, 사용자 승인 뒤):
1. `chore: E5 그래프용 matplotlib 추가` (`requirements.txt`)
2. `feat: E5 입력 timeline 생성 진입점 (밀도 + 흐름)` (`src/flow/e5/__init__.py`, 자체 timeline 모듈, `tests/flow/e5/e5_helpers.py`, 그 시험 모듈). v1.3 리뷰를 거친 단위라 남기고 6에서 지운다
3. `feat: E5 기준값 민감도 실행기 e5Sweep (서버 판정 클래스 재사용)` (`server/build.gradle`, `server/README.md`, `server/src/test/java/com/tripley/crowdsight/e5/*`, `server/src/test/resources/e5/e5_sweep_v02.json`). 서버 쪽만 담아 서버 리뷰가 따로 되게 한다
4. `feat: E5 불안정 시계열·유입 시간 차 분석과 보고서` (`src/flow/e5/analysis.py`, `src/flow/e5/report.py`, `tests/flow/e5/test_e5_analysis.py`, `tests/flow/e5/test_e5_report.py`)
5. `docs: E5 조사·계획 문서` (`docs/research/e5_research.md`, 이 문서 v1.4)

병합 (I2): `git merge origin/main` 병합 커밋 (메시지는 git 기본값).

병합 뒤:
6. (I3) `refactor: E5 자체 timeline 생성 제거, 통합 분석 스크립트 출력 사용` (자체 timeline 모듈·그 시험 모듈 삭제, `tests/flow/e5/e5_helpers.py` 도우미 정리)
7. (실행 뒤) `docs: E5 결과 (E04_039·E05_035·E05_038)` (`outputs/e5/`). `outputs/g1`·`outputs/e8`은 넣지 않는다

- PR 기준 `main`. Reviewer 코드 리뷰(최종 diff)를 거친 뒤 PR을 만든다. PR diff에서는 2와 6이 상쇄돼 자체 timeline 모듈이 보이지 않는다. 서버 리뷰를 따로 받고 싶으면 3번만 `feat/server-e5-sweep`으로 떼어 먼저 PR할 수 있다(사용자 결정). `docs/roadmap.md`, `CLAUDE.local.md`는 올리지 않는다.
- 대안 (사용자 결정): 2를 만들지 않고 I1 전에 지우기(커밋 6도 없음). 이력이 짧아지지만 계획 순서(병합 뒤 제거·전체 시험)와 달라지고, `e5_helpers.py`를 커밋 4 전에 손봐야 한다.

## 16. 변경 이력
| 버전 | 날짜 | 내용 |
|---|---|---|
| v1 | 11-16 | 첫 작성. 사용자 확정 1~4 반영, 제안 P1~P14. 조사 문서 주장을 소스에서 다시 확인(0장), scipy·matplotlib 버전은 pip dry-run으로 확인(설치 안 함) |
| v1.1 | 11-16 | 사용자 점검: E5 전용 코드를 `src/flow/e5/` 패키지로, 시험을 `tests/flow/e5/`로 옮김(`test_e5_` 접두사 유지). 확정 5 추가, 4.1절(import 규칙, `tests/flow/e5/`에 `__init__.py`·`conftest.py` 두지 않음) 추가. 경로·실행 명령·스니펫 import·검증·커밋 제안 갱신 |
| v1.2 | 11-16 | 사용자 결정: 판정 규칙의 Python 재구현을 지우고 서버 Java 판정 클래스를 재사용. 서버 test 소스셋에 실행기 `E5Sweep`·`SweepSummary`·`E5SweepTest`와 fixture, Gradle 작업 `e5Sweep`(test·check에 묶지 않음) 추가. 확정 2 교체, 0.2절을 재생 경로 확인으로 교체. 제안 P4(20행, null 건너뜀은 `[토론]`으로), P6(Java 계산), P7(T는 P 분포만), P8(`inflow_avg`는 실행기 값) 수정, P15~P18 추가. 실제 서버 확인 단계(C, G2 첫 단계) 추가: `alert-log`는 확인 기록만이라 REST로 알림을 받고 `report.py`가 대조. 실행 순서 A → B → C → D. TDD 12단계(2~13). 출력·검증·위험·커밋 제안 갱신 |
| v1.3 | 11-16 | 구현·Reviewer 검토 뒤 정정(사용자 지시 "다 고쳐"). 8장 7(b): t12는 유입 알림이 나는 초(`AlertDetector`), 켜짐 유지·빈 `events`는 t13. `report.py`는 실행기 CSV를 Java와 같이 **timeline 파일 이름**으로 찾는다(`video_id`로 찾으면 `E04_039_limit40.json` 실행 때 못 찾거나 예전 CSV를 읽음). 서버 알림 JSON은 `utf-8-sig`로 읽고 목록이 아니면 거부. `E5SweepTest`의 `inflow_on_s` 10은 t16 평균 4.2/7이 부동소수점으로 0.5999…가 되는 서버 계산 그대로임을 주석으로 남김. matplotlib가 필요 없는 오류 시험 2개의 `importorskip` 제거. md 2.3절에 non-null 비율 분모(모든 t) 명시. `build_report` 키 `cell_pressure`·`inflow_avg` 추가, 로그 축 눈금은 격자 값(한글 글꼴에 수학 빼기 기호 없음) |
| v1.4 | 11-18 | 사용자 결정(확정 6): E5 입력을 이유노 통합 분석 스크립트(`python -m src.counting.analyze`, main #53) 출력으로 바꾸고 E5 자체 timeline 생성(모듈·시험·전용 도우미)을 지운다. 확정 1 대체, P1·P13 폐기, P2·P12 수정. `origin/main` `24537bb` 병합 계획(8.1절 I0~I5): 커밋 → merge(rebase 아님) → 제거 → 전체 시험. `requirements.txt`는 자동 병합(시뮬레이션 확인). 0.1절을 통합 스크립트 확인으로 교체(필드·`models.flow`·추적 파일 덮어쓰기·처리 시간), 6.1절을 입력 필드 표로 교체. 10장 A를 "받기 또는 `analyze.py`"로, B·C·D를 세 구역(E04_039·E05_035·E05_038)으로 확장. 12.1절 이유노 리뷰(E05 오경보·6.4 m/s)와 코드상 원인(`min_heads` 1, `noise_var` 미전달) 추가, 수정은 범위 밖. `scikit-learn`·`joblib` 설치 필요(3.2절). 파일 목록·검증·위험·커밋 제안 갱신 |
| v1.4a | 11-18 | 사용자 결정: 15장 대안대로 커밋 2를 만들지 않고 I3(자체 timeline 제거)를 커밋 전에 했다. 순서는 I3 → 커밋(requirements·서버 실행기·분석·문서) → `git merge origin/main` → 전체 시험 → Reviewer |
| v1.5 | 11-19 | 불안정 밀도 하한(#63, `fix_instability_false_alarm_plan.md` 9절·D3)에 맞춤: `E5Sweep`이 `InstabilitySettings(pressure, seconds, minDensity)`로 만들고 불안정 격자에 `min_density` ∈ {0, 2.0, 3.0}을 더해 60행(기본 행 0.02·3·3.0). `_sweep_instability.csv` 머리줄에 `min_density`(seconds 다음) 추가, `report.py` 2.1 표는 기본 하한 행 전체 + 기본 seconds의 다른 하한 행, 그림은 기본 하한 행만. fixture c-0000 밀도 1.0 → 3.0 |
