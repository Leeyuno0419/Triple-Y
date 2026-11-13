# 서버 S4 불안정 → 심각, 유입 경보 구현 계획 (`feat/server-instability-inflow`)

| 항목 | 내용 |
|---|---|
| 작성일 | 2026-11-13 |
| 기준 | `docs/plans/server_impl_plan.md`(결정 기록 4·6·8, 1장, 2장 S4, 4장 `instability.*`·`inflow.*`, 5장 동시성, 6장 null, 9장 `[토론]` 2·3·11), `docs/api-spec.md` v0.2(3.1 `hello.thresholds`, 3.2 `zone_state`, 4.2~4.4), `docs/plans/server_s3_ws_plan.md`(1장 #4·#6, 8장, 12장), `docs/plans/server_s2_grade_plan.md`(1장 #3·#4, 7장), `docs/proposal-detail.md` 3.3(판정 규칙)·3.4(3) 군중난류 지표, `docs/decisions-2026-11-11.md`(결정 6), `docs/timeline-spec.md` v0.2(4·5절), `src/flow/run_flow.py`·`timeline_flow.py`·`inflow.py`(읽기만) |
| 대상 | `server/` (`main` `0dc264f`(S0~S3, #47)에서 분기 + S3 리뷰 반영 커밋 2개 `73f6f28`·`87252c8`), `docs/plans/` |
| 범위 | `crowdsight.instability.*`·`crowdsight.inflow.*` 설정, 셀 불안정(압력 기준을 N초 연속 초과) → 관측 등급 심각, 구역 유입 경보(5초 평균, `count` < 3이면 끔, 10초 연속 거짓이면 끔), `CellEvaluation.unstable`, `ZoneEvaluation.inflowAvg`·`inflowAlert`, `hello.thresholds.pressure`·`inflow_ratio`, `zone.inflow_alert` 실제 값. **알림 메시지(S5), ack·로그(S6), 재생 제어 REST(S7) 없음** |
| 상태 | 계획. 사용자 승인(2026-11-13) |

## 0. 확인한 사실 (코드·문서·JDK로 확인)
- 작업 트리:
  - 브랜치 `feat/server-instability-inflow`. `main..HEAD`는 `73f6f28`(S3 리뷰 반영), `87252c8`(S3 2차 리뷰 반영) 2개다. 이 PR에 함께 들어간다(11장).
  - untracked 파일은 `CLAUDE.local.md`와 이 계획 문서다. `CLAUDE.local.md`는 stage하지 않는다.
- S3 코드 상태 (S4가 붙는 자리):
  - `ZoneGrader(List<CellMeta> cells, GradeSettings settings)`. 셀마다 `GradeHysteresis`를 가진다. `evaluate`는 `requireSameCells`로 셀 수·ID를 먼저 검사하고, 그다음 상태를 바꾼다. 관측 등급은 `density == null ? null : GradeRule.ofDensity(...)`다.
  - `CellEvaluation(cellId, grade, gradePred60s, eligible, state)`. `ZoneEvaluation(t, zoneGrade, maxDensity, cells)`. Javadoc에 "불안정·유입 성분은 S4에서 더한다"가 있다.
  - `ZoneEvaluation`·`CellEvaluation`을 만드는 곳은 `ZoneGrader` 하나다.
  - `new ZoneGrader(...)` 호출: main `ZoneRegistry.register` 1곳, 테스트 `ZoneGraderTest`(2), `ZoneRuntimeTest`, `ReplaySchedulerTest`, `MessageFactoryTest`, `MessageJsonTest` 6곳.
  - `ZoneRuntime.evaluate`는 `tick.discontinuity()`(첫 프레임·반복·이동)이면 `grader.reset()`을 먼저 부른다. 그래서 `ZoneGrader.reset()`이 불안정·유입 상태도 비우면 api-spec 4.2 "반복·이동 때 불안정 연속 횟수, 유입 5초 평균·경보 초기화"가 된다. `ZoneRuntime`은 바꾸지 않는다.
  - `MessageFactory.hello`는 `new ThresholdsView(props.grade().density())`, `zoneState`는 `new ZoneView(..., false, frame.count())`이고 주석 `// inflow_alert는 S4에서 실제 값`이 있다.
  - `ThresholdsView(DensityThresholds density)`. Javadoc에 "S4가 pressure·inflowRatio 성분을 더한다"가 있다.
  - `CrowdsightProperties(timelineDir, timelineFiles, timeZone, replay, grade, ws, corsOriginPatterns)`. Javadoc에 "instability·inflow·alert-log는 그 값을 쓰는 PR(S4~S6)에서 추가한다"가 있다. 중첩 설정이 비면 null로 묶이고 compact constructor가 거부한다(`rejectsMissingGrade`가 이 동작에 기댄다).
  - `GradeSettings`는 grade 패키지 record이고 `CrowdsightProperties.grade`로 바로 묶인다. 값 검사는 record가 하고, 메시지에 키 이름(`up-seconds` 등)을 쓴다. `CrowdsightPropertiesTest`는 `rootCause().hasMessageContaining(키)`로 확인한다.
  - `application.yml` 주석: `# crowdsight.* 설정은 그 값을 읽는 클래스와 같은 PR에서 추가한다 (S4: instability·inflow, S6: alert-log)`.
  - `TestProperties`: `GRADE`, `TIME_ZONE`, `WS`, `CORS` 상수와 `of`·`replay`·`ws`·`full`. "S3~S6이 성분을 늘리면 여기만 고친다".
  - `TimelineFixtures.timeline(...)`(private)은 프레임의 `inflowRatio`·`count`를 늘 null로 만든다.
  - `ReplayScheduler.tickZone` DEBUG 로그: `재생 zone={} t={} discontinuity={} wrapped={} grade={} max_density={}`.
  - `MessageFactory.API_SCHEMA_VERSION = "0.2"`. api-spec v0.2 3.1은 이미 `thresholds.pressure`·`inflow_ratio`를 정의한다.
- api-spec v0.2:
  - 3.1 `thresholds: { density: {...}, pressure: 0.02, inflow_ratio: 0.6 }`. 표시용이다.
  - 3.2 `zone`: `{grade, max_density, inflow_ratio, inflow_alert, count}`. `cells[]` 키는 10개이고 **`unstable` 키가 없다**. `inflow_ratio`는 타임라인 값 그대로, `inflow_alert`는 5초 평균으로 판정한다.
  - 4.3: 셀 `pressure`가 `thresholds.pressure`를 **3초 연속 넘으면** 심각 조건이다. 관측 등급 = max(밀도 등급, 불안정이면 심각)이고, 여기에 4.2 히스테리시스를 적용한다. `pressure`가 null이거나 기준 이하이면 연속 0이다. `counterflow`는 판정에 쓰지 않는다.
  - 4.4: 켬 = 최근 5초 평균 > 0.6이고 `count` ≥ 3. 평균은 non-null 3개 이상일 때만, 창이 다 찬 뒤에만(초기화 뒤 첫 평균 t4). `count` null이면 켜지 않는다. 끔 = 조건이 10초 연속 거짓(평균 null·`count` < 3·`count` null인 초 포함).
  - 3.3: `INFLOW`(값 = 5초 평균), `INSTABILITY`(판정 대상 셀, 값 = 불안정 셀 최대 `pressure`)는 S5가 만든다. S4는 그 입력(`inflowAvg`, `inflowAlert`, `unstable`)만 만든다.
- `docs/proposal-detail.md` 3.3: "난류: 군중 압력이 기준을 3초 이상 넘으면 감지로 보고, 사라져도 10초 유지한다". 3.4(3): `P_c = ρ*_c × Var_c(v)` [1/s²], θ_P = 0.02/s²(하지 사고 값, E5로 조정). `server_impl_plan.md` "조사 반영"은 "10초 유지"를 셀 등급 내림 10초 히스테리시스로 대체했다(별도 유지 타이머 없음).
- 흐름 모듈 출력 (`src/flow/`, 읽기만):
  - `pressure` = `round(round(density, 2) × speed_var, 4)`(4자리). 셀에 사람이 없으면(`density` 2자리 반올림이 0) `pressure` 0. 셀 유효 머리가 `min_heads`보다 적거나 영상이 먼저 끝나면 null.
  - `inflow_ratio`는 2자리 반올림. 움직이는 경계 머리가 `inflow_min_heads`보다 적으면 null. 영상이 먼저 끝난 프레임도 null.
  - `counterflow`는 쓰지 않아 실제 파일에서 늘 null이다.
  - 서버 검증기는 `inflow_ratio` 0~1 또는 null, `count` ≥ 0 또는 null, `pressure` 숫자 또는 null을 보장한다. 그래서 NaN·음수 `count`는 판정에 들어오지 않는다.
  - `src/counting/fake_timeline.py`: `inflow_ratio` = `round(0.1 + 0.5 × walking, 4)` 최대 0.6이라 `> 0.6`을 넘지 못한다(README "최대 약 0.54"). 가짜 데이터로는 유입 경보가 켜지지 않는다. 그래서 단위 테스트와 합성 타임라인으로 시험한다.
- JDK: `ArrayDeque`는 null 원소를 받지 않는다(`addLast(null)` → `NullPointerException`). 유입 창은 null(관측 없음)도 한 칸을 차지해야 하므로 `ArrayDeque<Double>`을 쓸 수 없다 → `Double[]` 원형 버퍼.
- 부동소수: `0.7 + 0.8 + 0.7 + 0.9`는 double에서 `3.1`과 정확히 같지 않을 수 있다. 평균을 비교하는 테스트는 `isCloseTo(x, within(1e-9))`를 쓴다. 경계값(평균 == 기준) 테스트는 이진수로 정확한 값(0.5)으로 만든다.
- fixture `valid_v02.json`을 기본 설정(압력 0.02·3초, 유입 0.6·5초·3개·10초·3명)으로 판정한 결과 (손 계산):

| t | c-0000 `pressure` / 연속 | c-0001 `pressure` / 연속 | c-0102 `pressure` / 연속 | `inflow_ratio` | `count` | 창 non-null | 5초 평균 | `inflow_alert` |
|---|---|---|---|---|---|---|---|---|
| 0 | 0.005 / 0 | 0 / 0 | 0.002 / 0 | null | 6.5 | — | null (창 덜 참) | false |
| 1 | 0.009 / 0 | 0.0015 / 0 | null / 0 | 0.3 | 11.0 | — | null | false |
| 2 | 0.016 / 0 | null / 0 | 0.008 / 0 | 0.45 | 15.0 | — | null | false |
| 3 | 0.032 / 1 | 0.005 / 0 | 0.024 / 1 | 0.7 | 22.8 | — | null | false |
| 4 | 0.0504 / 2 | 0.009 / 0 | 0.033 / 2 | 0.65 | null | 4 | (0.3+0.45+0.7+0.65)/4 = 0.525 | false |

- 결론: fixture에서는 불안정·유입 경보가 켜지지 않는다. `unstable`은 모두 false이고 셀·구역 등급은 S3 0장 표와 같다. 그래서 S3 `zone_state` 예시(`server_s3_ws_plan.md` 7.2·7.3)와 통합 테스트 기대값은 그대로다. 바뀌는 출력은 `hello.thresholds` 하나다.

## 1. 이번 계획에서 정한 것 (계획 대비)
| # | 항목 | 결정 | 이유 |
|---|---|---|---|
| 1 | 설정 record | grade 패키지에 `InstabilitySettings(double pressure, int seconds)`, `InflowSettings(double ratio, int windowSeconds, int minSamples, int offSeconds, double minCount)`. `CrowdsightProperties`에 `instability`, `inflow` 성분(`grade` 바로 뒤). 값 검사는 각 record의 compact constructor | `GradeSettings`와 같은 방식(S2 결정 #3). grade 패키지는 Spring 없이 남는다. 계획 4장은 `1 ≤ min-samples ≤ window-seconds` 검사를 `CrowdsightProperties`에 두었는데, 값을 가진 record가 검사하는 쪽으로 옮긴다(9장 정정) |
| 2 | 판정기 생성자 | `InstabilityTracker(InstabilitySettings)`, `InflowMonitor(InflowSettings)` | 계획 2장 S4는 원시 값 생성자였다. 설정 record를 받으면 값 검사가 record 한 곳에만 있다(`GradeHysteresis`처럼 생성자에서 같은 검사를 반복하지 않는다). 테스트는 `new InflowSettings(...)`로 다른 값을 쓴다 |
| 3 | `ZoneGrader` 생성자 | `ZoneGrader(List<CellMeta> cells, GradeSettings grade, InstabilitySettings instability, InflowSettings inflow)`. 셀마다 `InstabilityTracker`, 구역에 `InflowMonitor` 1개 | 계획 2장 S4 "`ZoneGrader` 생성자에 불안정 설정 추가". 유입도 `ZoneEvaluation`에 담기므로 같은 곳에서 판정한다. `ZoneRuntime`·`ReplayScheduler`의 초기화 경로를 그대로 쓴다 |
| 4 | 관측 등급 | `unstable ? CRITICAL : (density == null ? null : ofDensity(density))` | 계획의 `max(ofDensity, unstable ? CRITICAL : NORMAL)`과 같은 결과다(CRITICAL이 최고 등급). 방어용 `density` null 셀이 불안정이면 null로 건너뛰지 않고 심각으로 센다 |
| 5 | 불안정 비교 | `pressure > 기준` (초과). 같으면 연속 0 | api-spec 4.3 "넘으면", 6장 "기준 이하이면 0". 흐름 출력이 4자리라 0.02와 같은 값이 실제로 나온다 |
| 6 | 불안정 연속 상한 | `streak`는 `seconds`에서 멈춘다 | 30분 반복은 초기화되지만 `loop: false` 장시간 재생에도 넘치지 않는다. 한 줄이다 |
| 7 | 불안정 해제 | 별도 "10초 유지" 타이머 없음. `unstable`은 조건이 깨진 초에 바로 false가 되고, 셀 등급은 내림 히스테리시스(10초에 한 단계)로 내려간다 | `server_impl_plan.md` "조사 반영"(상세 3.3 "불안정 10초 유지"를 히스테리시스로 대체). 심각은 최소 10초 유지된다 |
| 8 | 작은 셀의 불안정 | 모든 셀이 자기 `unstable`을 계산하고 자기 등급에 반영한다. 구역 등급에는 판정 대상 셀만 들어간다(결정 4 그대로) | 작은 셀도 자기 `grade`를 보낸다(api-spec 3.2). S5 `INSTABILITY`는 판정 대상 셀만 본다(api-spec 3.3) → `CellEvaluation.eligible`로 거른다 |
| 9 | 유입 창 | `Double[]` 원형 버퍼(크기 `window-seconds`), null도 한 칸. 관측 수가 창 크기보다 작으면 평균 null. 다 차면 non-null이 `min-samples` 이상일 때 그 평균 | 결정 기록 8. `ArrayDeque`는 null을 못 넣는다(0장) |
| 10 | 유입 켬·끔 | 조건 = `avg != null && avg > ratio && count != null && count >= minCount`. 조건이 참이면 켜고 거짓 연속 0. 켜진 상태에서 거짓이면 연속 +1, `off-seconds`에 닿으면 끄고 연속 0. 꺼진 상태의 거짓은 세지 않는다 | api-spec 4.4. `count`는 "3명 이상"이라 `>=`, 평균은 "넘고"라 `>` |
| 11 | `ZoneEvaluation` 성분 | `(t, zoneGrade, maxDensity, inflowAvg, inflowAlert, cells)`. `inflowAvg`는 `Double`(null 가능) | 계획 2장 S4 이름. S5 `INFLOW` 값이 `inflowAvg`다 |
| 12 | `CellEvaluation` 성분 | `(cellId, grade, gradePred60s, eligible, unstable, state)` | 계획 2장 S4. S5 `INSTABILITY` 입력 |
| 13 | `zone_state.cells[].unstable` | **보내지 않는다**. `CellView`는 그대로 10키 | api-spec 3.2에 없는 키다. 화면에는 셀 `grade`(심각)로 보인다. 보낼지는 `[토론]` 1 |
| 14 | 5초 평균 전송 | `zone_state`에 넣지 않는다. `zone.inflow_ratio`는 타임라인 원래 값 그대로 | api-spec 3.2. 평균은 S5 `INFLOW.value`로 나간다. 화면 그래프에 평균선을 둘지는 `[토론]` 2 |
| 15 | `hello.thresholds` | `ThresholdsView(DensityThresholds density, double pressure, double inflowRatio)` → JSON `{density, pressure, inflow_ratio}`. 값은 `instability.pressure`, `inflow.ratio` | api-spec 3.1. S3 결정 #4에서 S4로 미룬 것 |
| 16 | `hello.schema_version` | `"0.2"` 그대로 | api-spec v0.2가 이미 두 키를 정의한다. S3가 일부만 보냈을 뿐 메시지 형식은 바뀌지 않는다 |
| 17 | 판정 순서 | `evaluate`: 셀 검사 → 셀마다 [불안정 갱신 → 관측 등급 → 히스테리시스] → 유입 갱신 | 셀 검사에서 거부된 프레임은 유입 창도 움직이지 않는다(테스트 `rejectedFrameNotObserved`) |
| 18 | 재생 DEBUG 로그 | 끝에 `inflow_avg={} inflow_alert={}`를 더한다 | 5초 평균은 메시지 어디에도 없어 bootRun에서 확인할 곳이 이 로그뿐이다. 한 줄 수정 |
| 19 | 테스트 도우미 | `TestProperties.INSTABILITY`, `INFLOW` 상수와 `grader(List<CellMeta>)`. `TimelineFixtures.timelineWithInflow(duration, inflowRatio, count)` | `new ZoneGrader` 호출 6곳이 인자 4개가 된다. `TestProperties`는 "성분이 늘면 여기만 고친다"가 목적이다 |

## 2. 구조와 파일

### 2.1 추가·수정 파일
```text
server/
├─ README.md                                                     수정 (판정 기준 절)
├─ src/main/resources/application.yml                            수정 (instability.*, inflow.*)
├─ src/main/java/com/tripley/crowdsight/
│  ├─ config/  CrowdsightProperties                              수정 (instability, inflow)
│  ├─ grade/   InstabilitySettings, InflowSettings, InstabilityTracker, InflowMonitor, InflowStatus   추가
│  │           CellEvaluation (unstable), ZoneEvaluation (inflowAvg, inflowAlert), ZoneGrader          수정
│  ├─ replay/  ZoneRegistry (생성자 인자), ReplayScheduler (DEBUG 로그)                                 수정
│  └─ ws/      MessageFactory (thresholds, inflow_alert)                                              수정
│      ws/message/ ThresholdsView (pressure, inflowRatio), HelloMessage·ZoneView (Javadoc만)           수정
└─ src/test/java/com/tripley/crowdsight/
   ├─ CrowdsightServerApplicationIntegrationTest                 수정 (+1)
   ├─ config/   CrowdsightPropertiesTest (+5), TestProperties (INSTABILITY, INFLOW, grader)
   ├─ grade/    InstabilityTrackerTest, InflowMonitorTest        추가
   │            ZoneGraderTest                                   수정 (+7, 1개 기대값 추가)
   ├─ replay/   ZoneRuntimeTest (+1), ReplaySchedulerTest (도우미만)
   ├─ timeline/ TimelineFixtures (timelineWithInflow)
   └─ ws/       MessageFactoryTest (1개 수정, +1), MessageJsonTest (예시·키 수정, 도우미),
                ZoneWebSocketIntegrationTest (helloFirst 단언 +2)
docs/plans/server_s4_instability_inflow_plan.md                  (이 문서)
docs/plans/server_impl_plan.md                                   정정 (9장)
```

### 2.2 1초 흐름 (S4, 바뀐 곳만 굵게)
```text
ReplayScheduler.tickAll() → tickZone(zone)
  ZoneRuntime.tick()
    ZonePlayer.tick()              → Tick(frame, discontinuity, wrapped)
    discontinuity이면 ZoneGrader.reset()   ← **히스테리시스 + 불안정 연속 + 유입 창·경보 모두 비움**
    ZoneGrader.evaluate(frame)
      requireSameCells
      셀 i: **unstable = InstabilityTracker[i].update(pressure)**
            **observed = unstable ? CRITICAL : ofDensity(density)**
            grade = GradeHysteresis[i].update(observed)
      **InflowStatus = InflowMonitor.update(frame.inflowRatio, frame.count)**
      → ZoneEvaluation(t, zoneGrade, maxDensity, **inflowAvg, inflowAlert**, cells[**unstable**])
  [playback] → zoneState: MessageFactory.zoneState → ZoneView(**inflowAlert = eval.inflowAlert**)
접속: MessageFactory.hello → ThresholdsView(density, **pressure, inflowRatio**)
```

### 2.3 스레드 규칙
- 바뀌지 않는다. `InstabilityTracker`·`InflowMonitor`는 `ZoneGrader` 안에 있고 재생 스레드(겹치지 않는 주기 작업 하나)만 부른다. 잠금 없음.
- `hello`(Tomcat 스레드)는 `CrowdsightProperties`(불변 record)만 읽는다. 판정 상태는 읽지 않는다.

## 3. 설정

### 3.1 `application.yml` (수정분)
`grade:` 다음, `ws:` 앞에 넣는다. 맨 위 주석은 `(S6: alert-log)`만 남긴다.
```yaml
# crowdsight.* 설정은 그 값을 읽는 클래스와 같은 PR에서 추가한다 (S6: alert-log)
crowdsight:
  # ... (timeline-dir ~ grade 그대로)
  instability:
    pressure: 0.02                           # 군중 압력 기준(1/s²). 넘는 초가 이어지면 셀 심각 (가정, E5로 조정)
    seconds: 3                               # 기준을 이 초만큼 연속 넘으면 불안정 (api-spec 4.3)
  inflow:
    ratio: 0.6                               # 5초 평균 inflow_ratio가 이 값을 넘으면 경보 조건 (가정)
    window-seconds: 5                        # 평균 창(초). 시작·초기화 뒤 창이 다 차야 평균을 낸다 (결정 기록 8)
    min-samples: 3                           # 창 안 non-null 값이 이 개수 이상일 때만 평균 (결정 기록 8, 가정)
    off-seconds: 10                          # 켜진 뒤 조건이 이 초만큼 연속 거짓이면 끔 (가정)
    min-count: 3                             # 구역 인원 count가 이보다 적으면 켜지 않음 (결정 6)
  # ws, cors-origin-patterns 그대로
```

### 3.2 `grade/InstabilitySettings.java` (추가)
```java
package com.tripley.crowdsight.grade;

/**
 * 셀 불안정 판정 설정 (api-spec 4.3). crowdsight.instability.*로 바인딩한다.
 * hello.thresholds.pressure로도 그대로 보낸다.
 *
 * @param pressure 군중 압력 기준(1/s²). 이 값을 넘어야(초과) 그 초를 센다
 * @param seconds  기준을 연속으로 넘어야 하는 초 (1 이상)
 */
public record InstabilitySettings(double pressure, int seconds) {

    public InstabilitySettings {
        if (!(pressure > 0)) {   // NaN도 거부
            throw new IllegalArgumentException("pressure 는 0보다 커야 합니다: " + pressure);
        }
        if (seconds < 1) {
            throw new IllegalArgumentException("seconds 는 1 이상이어야 합니다: " + seconds);
        }
    }
}
```

### 3.3 `grade/InflowSettings.java` (추가)
```java
package com.tripley.crowdsight.grade;

/**
 * 구역 유입 경보 설정 (api-spec 4.4, 결정 6, 결정 기록 8). crowdsight.inflow.*로 바인딩한다.
 * hello.thresholds.inflow_ratio로 ratio를 보낸다.
 *
 * @param ratio         5초 평균이 이 값을 넘으면(초과) 경보 조건. 0 이상 1 미만
 * @param windowSeconds 평균 창(초, 1 이상). 시작·초기화 뒤 이 개수만큼 관측이 쌓여야 평균을 낸다
 * @param minSamples    창 안 non-null 값이 이 개수 이상일 때만 평균 (1 이상 windowSeconds 이하)
 * @param offSeconds    켜진 뒤 조건이 이 초만큼 연속 거짓이면 끈다 (1 이상)
 * @param minCount      구역 인원 count가 이 값 이상일 때만 켠다 (0 이상)
 */
public record InflowSettings(double ratio, int windowSeconds, int minSamples, int offSeconds, double minCount) {

    public InflowSettings {
        if (!(ratio >= 0 && ratio < 1)) {
            throw new IllegalArgumentException("ratio 는 0 이상 1 미만이어야 합니다: " + ratio);
        }
        if (windowSeconds < 1) {
            throw new IllegalArgumentException("window-seconds 는 1 이상이어야 합니다: " + windowSeconds);
        }
        if (minSamples < 1 || minSamples > windowSeconds) {
            throw new IllegalArgumentException("min-samples 는 1 이상 window-seconds 이하여야 합니다: min-samples="
                    + minSamples + ", window-seconds=" + windowSeconds);
        }
        if (offSeconds < 1) {
            throw new IllegalArgumentException("off-seconds 는 1 이상이어야 합니다: " + offSeconds);
        }
        if (!(minCount >= 0)) {
            throw new IllegalArgumentException("min-count 는 0 이상이어야 합니다: " + minCount);
        }
    }
}
```
- `ratio`를 1 미만으로 제한한 이유: `inflow_ratio`는 0~1이라 `> 1.0`은 영원히 거짓이다. 설정 실수를 시작 때 알린다.

### 3.4 `config/CrowdsightProperties.java` (수정분)
```java
import com.tripley.crowdsight.grade.GradeSettings;
import com.tripley.crowdsight.grade.InflowSettings;
import com.tripley.crowdsight.grade.InstabilitySettings;

/**
 * crowdsight.* 설정 (application.yml). 기준값·시간·경로는 이 record 한 곳에만 둔다.
 * 값 검사는 compact constructor에서 한다 (validation 스타터 안 씀). 틀리면 서버가 시작하지 않는다.
 * grade·instability·inflow는 grade 패키지의 record로 바로 묶고, 그 값 검사는 해당 record가 한다.
 * alert-log는 그 값을 쓰는 PR(S6)에서 추가한다.
 *
 * ... (기존 @param)
 * @param grade              등급 판정 설정 (crowdsight.grade.*)
 * @param instability        셀 불안정 판정 설정 (crowdsight.instability.*)
 * @param inflow             유입 경보 설정 (crowdsight.inflow.*)
 * @param ws                 WebSocket 설정 (crowdsight.ws.*)
 * ...
 */
@ConfigurationProperties("crowdsight")
public record CrowdsightProperties(String timelineDir, List<String> timelineFiles, String timeZone, Replay replay,
                                   GradeSettings grade, InstabilitySettings instability, InflowSettings inflow,
                                   Ws ws, List<String> corsOriginPatterns) {

    public CrowdsightProperties {
        // ... (grade null 검사 뒤)
        if (instability == null) {
            throw new IllegalArgumentException("crowdsight.instability 가 없습니다.");
        }
        if (inflow == null) {
            throw new IllegalArgumentException("crowdsight.inflow 가 없습니다.");
        }
        // ... (ws 이하 그대로)
    }
```

## 4. 판정

### 4.1 `grade/InstabilityTracker.java` (추가)
```java
package com.tripley.crowdsight.grade;

import java.util.Objects;

/**
 * 셀 하나의 불안정 판정 (api-spec 4.3). pressure가 기준을 seconds초 연속 넘으면(초과) 불안정이다.
 * pressure가 null(관측 없음)이거나 기준 이하이면 연속을 0으로 되돌린다. 조건이 깨진 초에 바로 false가 된다.
 * 심각 등급이 얼마나 남는지는 GradeHysteresis 내림 규칙이 정한다 (별도 유지 타이머 없음).
 * 스레드 규칙: 재생 스레드 하나만 부른다. 잠금 없음.
 */
public final class InstabilityTracker {

    private final double threshold;
    private final int seconds;
    private int streak;   // 기준을 넘은 연속 초. seconds에서 멈춘다

    public InstabilityTracker(InstabilitySettings settings) {
        Objects.requireNonNull(settings, "settings");
        this.threshold = settings.pressure();
        this.seconds = settings.seconds();
    }

    /** 이번 초의 pressure를 반영하고 불안정이면 true를 돌려준다. */
    public boolean update(Double pressure) {
        if (pressure != null && pressure > threshold) {
            if (streak < seconds) {
                streak++;
            }
        } else {
            streak = 0;
        }
        return streak >= seconds;
    }

    /** 연속을 0으로 되돌린다 (반복·이동). */
    public void reset() {
        streak = 0;
    }
}
```

### 4.2 `grade/InflowStatus.java`, `grade/InflowMonitor.java` (추가)
```java
package com.tripley.crowdsight.grade;

/**
 * 한 초의 유입 판정 결과.
 *
 * @param average 최근 windowSeconds초 inflow_ratio 평균. 창이 덜 찼거나 non-null 값이 minSamples개 미만이면 null
 * @param on      유입 경보가 켜져 있는지
 */
public record InflowStatus(Double average, boolean on) {
}
```
```java
package com.tripley.crowdsight.grade;

import java.util.Arrays;
import java.util.Objects;

/**
 * 구역 유입 경보 (api-spec 4.4, 결정 6, 결정 기록 8).
 * 평균: 생성·reset 뒤 관측이 windowSeconds개 쌓이기 전에는 null (창이 다 찬 뒤에만 계산).
 *       그 뒤 최근 windowSeconds초(이번 초 포함) 중 null이 아닌 값이 minSamples개 이상이면 그 평균, 아니면 null.
 *       inflow_ratio null인 초도 창 한 칸을 차지한다.
 * 조건: 평균 != null && 평균 > ratio && count != null && count >= minCount.
 * 켬: 조건이 참인 초. 끔: 켜진 뒤 조건이 offSeconds초 연속 거짓 (평균 null·count 부족·count null인 초도 거짓).
 * 스레드 규칙: 재생 스레드 하나만 부른다. 잠금 없음.
 */
public final class InflowMonitor {

    private final InflowSettings settings;
    private final Double[] window;   // 원형 버퍼. null = 그 초 관측 없음 (ArrayDeque는 null을 못 넣는다)
    private int next;                // 다음에 쓸 칸
    private int observed;            // 생성·reset 뒤 관측 수. 창 크기에서 멈춘다
    private boolean on;
    private int falseStreak;         // 켜진 뒤 조건이 거짓인 연속 초

    public InflowMonitor(InflowSettings settings) {
        this.settings = Objects.requireNonNull(settings, "settings");
        this.window = new Double[settings.windowSeconds()];
    }

    /** 이번 초 값을 창에 넣고 평균·경보 상태를 돌려준다. */
    public InflowStatus update(Double inflowRatio, Double count) {
        window[next] = inflowRatio;
        next = (next + 1) % window.length;
        if (observed < window.length) {
            observed++;
        }
        Double average = average();
        boolean condition = average != null && average > settings.ratio()
                && count != null && count >= settings.minCount();
        if (condition) {
            on = true;
            falseStreak = 0;
        } else if (on && ++falseStreak >= settings.offSeconds()) {
            on = false;
            falseStreak = 0;
        }
        return new InflowStatus(average, on);
    }

    /** 창·연속·경보를 모두 비운다 (반복·이동). */
    public void reset() {
        Arrays.fill(window, null);
        next = 0;
        observed = 0;
        on = false;
        falseStreak = 0;
    }

    private Double average() {
        if (observed < window.length) {
            return null;
        }
        double sum = 0;
        int n = 0;
        for (Double v : window) {
            if (v != null) {
                sum += v;
                n++;
            }
        }
        return n >= settings.minSamples() ? sum / n : null;
    }
}
```
- 합은 칸 순서로 더하므로 시간 순서와 다를 수 있다. 결과 차이는 1e-15 수준이고 테스트는 허용 오차로 비교한다(0장).

### 4.3 `grade/CellEvaluation.java`, `grade/ZoneEvaluation.java` (수정)
```java
/**
 * 셀 하나의 한 초 판정 결과.
 *
 * @param cellId       셀 ID
 * @param grade        히스테리시스를 거친 셀 등급. 판정 대상이 아닌 작은 셀도 계산한다 (api-spec 3.2)
 * @param gradePred60s density_pred_60s의 등급 (히스테리시스 없음). 예측이 null이면 null
 * @param eligible     판정 대상(walkable_area_m2 ≥ min-walkable-area-m2)인지. 구역 등급·max_density·S5 INSTABILITY에 쓴다
 * @param unstable     pressure가 기준을 seconds초 연속 넘었는지 (api-spec 4.3). zone_state에는 보내지 않는다
 * @param state        타임라인 셀 값 그대로 (zone_state cells[]로 옮김)
 */
public record CellEvaluation(String cellId, Grade grade, Grade gradePred60s, boolean eligible, boolean unstable,
                             CellState state) {
}
```
```java
/**
 * 구역 1개의 한 초 판정 결과. zone_state(S3)·알림(S5)의 입력이다.
 *
 * @param t           프레임 t
 * @param zoneGrade   판정 대상 셀 등급의 최댓값. 대상 셀이 없으면 NORMAL
 * @param maxDensity  판정 대상 셀 중 null이 아닌 밀도의 최댓값. 없으면 null
 * @param inflowAvg   inflow_ratio 최근 5초 평균 (InflowMonitor). 창이 덜 찼거나 값이 모자라면 null
 * @param inflowAlert 유입 경보가 켜져 있는지
 * @param cells       셀별 결과 (meta 순서)
 */
public record ZoneEvaluation(int t, Grade zoneGrade, Double maxDensity, Double inflowAvg, boolean inflowAlert,
                             List<CellEvaluation> cells) {

    public ZoneEvaluation {
        cells = List.copyOf(cells);
    }
}
```

### 4.4 `grade/ZoneGrader.java` (수정분)
```java
/**
 * 구역 1개의 셀 등급·구역 등급·유입 경보 판정 (api-spec 4.1~4.4).
 * 셀마다 GradeHysteresis·InstabilityTracker를, 구역에 InflowMonitor 1개를 가진다.
 * 셀 관측 등급 = 불안정이면 CRITICAL, 아니면 밀도 등급. 여기에 히스테리시스를 적용한다.
 * 스레드 규칙: evaluate·reset은 재생 스레드 하나만 부른다. 잠금 없음.
 */
public final class ZoneGrader {

    private final List<String> cellIds;
    private final boolean[] eligible;
    private final GradeHysteresis[] hysteresis;
    private final InstabilityTracker[] instability;
    private final InflowMonitor inflow;
    private final DensityThresholds thresholds;
    private final int eligibleCount;

    /**
     * @param cells       meta.cells (frame.cells와 같은 순서)
     * @param grade       등급 설정
     * @param instability 불안정 설정
     * @param inflow      유입 경보 설정
     */
    public ZoneGrader(List<CellMeta> cells, GradeSettings grade, InstabilitySettings instability,
                      InflowSettings inflow) {
        Objects.requireNonNull(cells, "cells");
        Objects.requireNonNull(grade, "grade");
        Objects.requireNonNull(instability, "instability");
        int n = cells.size();
        this.cellIds = cells.stream().map(CellMeta::cellId).toList();
        this.eligible = new boolean[n];
        this.hysteresis = new GradeHysteresis[n];
        this.instability = new InstabilityTracker[n];
        int count = 0;
        for (int i = 0; i < n; i++) {
            eligible[i] = cells.get(i).walkableAreaM2() >= grade.minWalkableAreaM2();
            hysteresis[i] = new GradeHysteresis(grade.upSeconds(), grade.downSeconds());
            this.instability[i] = new InstabilityTracker(instability);
            if (eligible[i]) {
                count++;
            }
        }
        this.eligibleCount = count;
        this.thresholds = grade.density();
        this.inflow = new InflowMonitor(inflow);   // null이면 InflowMonitor가 NPE
    }

    public ZoneEvaluation evaluate(Frame frame) {
        List<CellState> states = frame.cells();
        requireSameCells(frame.t(), states);
        List<CellEvaluation> cells = new ArrayList<>(states.size());
        Grade zoneGrade = Grade.NORMAL;
        Double maxDensity = null;
        for (int i = 0; i < states.size(); i++) {
            CellState state = states.get(i);
            Double density = state.density();
            boolean unstable = instability[i].update(state.pressure());
            Grade grade = hysteresis[i].update(observedGrade(density, unstable));
            if (eligible[i]) {
                zoneGrade = Grade.max(zoneGrade, grade);
                if (density != null && (maxDensity == null || density > maxDensity)) {
                    maxDensity = density;
                }
            }
            Grade predicted = GradeRule.ofPrediction(state.densityPred60s(), thresholds);
            cells.add(new CellEvaluation(state.cellId(), grade, predicted, eligible[i], unstable, state));
        }
        InflowStatus status = inflow.update(frame.inflowRatio(), frame.count());
        return new ZoneEvaluation(frame.t(), zoneGrade, maxDensity, status.average(), status.on(), cells);
    }

    /** 모든 셀을 NORMAL로, 불안정 연속·유입 창·경보를 처음으로 되돌린다 (첫 프레임·반복·이동). */
    public void reset() {
        for (GradeHysteresis h : hysteresis) {
            h.reset();
        }
        for (InstabilityTracker tracker : instability) {
            tracker.reset();
        }
        inflow.reset();
    }

    /** 셀 관측 등급. 불안정이면 CRITICAL, 아니면 밀도 등급. 밀도 null이면 null(그 초는 건너뜀, 결정 기록 4). */
    private Grade observedGrade(Double density, boolean unstable) {
        if (unstable) {
            return Grade.CRITICAL;
        }
        return density == null ? null : GradeRule.ofDensity(density, thresholds);
    }

    // eligibleCount(), requireSameCells(...) 그대로
}
```
- 필드 `instability`와 생성자 인자 `instability`가 이름이 같다. 생성자 안에서는 `this.instability[i]`로 쓴다(위 코드). 헷갈리면 필드를 `trackers`로 바꿔도 된다 (TDD가 고른다, 동작 같음).

### 4.5 `replay/ZoneRegistry.java`, `replay/ReplayScheduler.java` (수정분)
```java
// ZoneRegistry.register
ZoneGrader grader = new ZoneGrader(timeline.meta().cells(), props.grade(), props.instability(), props.inflow());
```
```java
// ReplayScheduler.tickZone
log.debug("재생 zone={} t={} discontinuity={} wrapped={} grade={} max_density={} inflow_avg={} inflow_alert={}",
        zone.zoneId(), s.tick().frame().t(), s.tick().discontinuity(), s.tick().wrapped(),
        s.evaluation().zoneGrade(), s.evaluation().maxDensity(), s.evaluation().inflowAvg(),
        s.evaluation().inflowAlert());
```

## 5. 메시지

### 5.1 `ws/message/ThresholdsView.java` (수정)
```java
package com.tripley.crowdsight.ws.message;

import com.tripley.crowdsight.grade.DensityThresholds;

/**
 * hello.thresholds (api-spec 3.1). 표시용(범례·그래프 기준선)이고 판정은 서버가 한다.
 *
 * @param density     밀도 등급 기준 (crowdsight.grade.density)
 * @param pressure    군중 압력 기준 (crowdsight.instability.pressure)
 * @param inflowRatio 유입 비율 5초 평균 기준 (crowdsight.inflow.ratio). JSON 키 inflow_ratio
 */
public record ThresholdsView(DensityThresholds density, double pressure, double inflowRatio) {
}
```

### 5.2 `ws/MessageFactory.java` (수정분)
```java
    /** 접속한 화면에 보낼 hello. 재생 상태는 지금 snapshot이다. */
    public HelloMessage hello(ZoneRuntime zone) {
        ZonePlayer player = zone.player();
        ThresholdsView thresholds = new ThresholdsView(props.grade().density(), props.instability().pressure(),
                props.inflow().ratio());
        return new HelloMessage(API_SCHEMA_VERSION, zone.zoneId(), player.timeline().metaJson(),
                playbackView(player.snapshot()), thresholds, List.of());
    }

    /** 한 초 판정 결과. frameTs는 frameTs()로 tick마다 한 번 만든다. */
    public ZoneStateMessage zoneState(String zoneId, ZoneStep step, String frameTs) {
        Frame frame = step.tick().frame();
        ZoneEvaluation eval = step.evaluation();
        ZoneView zone = new ZoneView(eval.zoneGrade(), eval.maxDensity(), frame.inflowRatio(), eval.inflowAlert(),
                frame.count());
        List<CellView> cells = eval.cells().stream().map(MessageFactory::cellView).toList();
        return new ZoneStateMessage(zoneId, eval.t(), frameTs, zone, cells);
    }
```
- Javadoc만 고치는 곳:
  - `HelloMessage` `@param thresholds`: "표시용 기준값 (density, pressure, inflow_ratio)".
  - `ZoneView` 클래스 설명: "inflowRatio·count는 타임라인 값 그대로, inflowAlert는 5초 평균 판정 (api-spec 4.4)". `@param inflowAlert`: "유입 경보 (ZoneEvaluation.inflowAlert)".
  - `ZoneRuntime` Javadoc은 그대로("S5에서 AlertDetector를 더한다").

## 6. 테스트
공통 표기: N=NORMAL, C=CAUTION, A=ALERT, CR=CRITICAL, T=true, F=false. 평균 비교는 `isCloseTo(x, within(1e-9))`. 기본 설정은 `TestProperties.INSTABILITY`(0.02, 3), `INFLOW`(0.6, 5, 3, 10, 3.0).

### 6.1 테스트 도우미
`config/TestProperties` (수정분):
```java
    /** application.yml crowdsight.instability 기본값과 같다 (bindsDefaultInstabilityInflowSettings가 확인). */
    public static final InstabilitySettings INSTABILITY = new InstabilitySettings(0.02, 3);

    /** application.yml crowdsight.inflow 기본값과 같다. */
    public static final InflowSettings INFLOW = new InflowSettings(0.6, 5, 3, 10, 3.0);

    /** 기본 설정(등급·불안정·유입)으로 판정기를 만든다. */
    public static ZoneGrader grader(List<CellMeta> cells) {
        return new ZoneGrader(cells, GRADE, INSTABILITY, INFLOW);
    }

    private static CrowdsightProperties full(String dir, List<String> files, long intervalMs, boolean loop,
                                             CrowdsightProperties.Ws ws) {
        return new CrowdsightProperties(dir, files, TIME_ZONE, new CrowdsightProperties.Replay(intervalMs, loop),
                GRADE, INSTABILITY, INFLOW, ws, CORS);
    }
```
- `new ZoneGrader(x, TestProperties.GRADE)` 6곳을 `TestProperties.grader(x)`로 바꾼다: `ZoneGraderTest.grader`·`gradesFixtureTimeline`, `ZoneRuntimeTest.runtime`, `ReplaySchedulerTest.runtime`, `MessageFactoryTest.fixtureRuntime`, `MessageJsonTest.helloMetaPassthrough`.

`timeline/TimelineFixtures` (수정분):
```java
    /** 셀 없이 매 초 같은 inflow_ratio·count를 넣은 타임라인 (유입 시험용). 검증기를 거치지 않는다. */
    public static ZoneTimeline timelineWithInflow(int duration, double inflowRatio, double count) {
        return timeline(duration, List.of(), t -> List.of(), inflowRatio, count);
    }

    public static ZoneTimeline timelineOf(int duration) {
        return timeline(duration, List.of(), t -> List.of(), null, null);
    }
    // timelineWithDensity도 마지막 두 인자 null, null

    private static ZoneTimeline timeline(int duration, List<CellMeta> cells, IntFunction<List<CellState>> frameCells,
                                         Double inflowRatio, Double count) {
        // ... frames: new Frame(t, inflowRatio, count, frameCells.apply(t))
    }
```

`grade/ZoneGraderTest` 프레임 도우미 (추가):
```java
    /** metas 순서의 셀로 프레임을 만든다. 밀도·압력은 셀마다, inflow_ratio·count는 구역 값. 예측은 null. */
    private static Frame frame(int t, List<CellMeta> metas, Double[] densities, Double[] pressures,
                               Double inflowRatio, Double count) {
        List<CellState> cells = new ArrayList<>();
        for (int i = 0; i < metas.size(); i++) {
            cells.add(new CellState(metas.get(i).cellId(), densities[i], null, null, null, pressures[i], null, null));
        }
        return new Frame(t, inflowRatio, count, cells);
    }

    private static List<Boolean> unstables(ZoneEvaluation e) {
        return e.cells().stream().map(CellEvaluation::unstable).toList();
    }
```

### 6.2 `grade/InstabilityTrackerTest` (추가)
`tracker = new InstabilityTracker(TestProperties.INSTABILITY)`.

| 메서드 | `@DisplayName` | 입력 (t0부터) | 기대 |
|---|---|---|---|
| `activeAfterThreeSeconds` | "기준을 3초 연속 넘으면 불안정이다" | 0.03 × 4 | [F, F, T, T] |
| `nullBreaksStreak` | "pressure null은 연속을 끊는다" | 0.03, 0.03, null, 0.03, 0.03, 0.03 | [F, F, F, F, F, T] |
| `equalToThresholdBreaksStreak` | "기준과 같은 값은 넘은 것이 아니다" | 0.03, 0.02, 0.03, 0.03, 0.03 | [F, F, F, F, T] |
| `endsAsSoonAsBelow` | "기준 아래로 내려간 초에 바로 풀린다" | 0.03 × 3, 0.01, 0.03 | [F, F, T, F, F] |
| `resetClearsStreak` | "초기화하면 연속이 0부터 다시 쌓인다" | 0.03 × 2, reset, 0.03 × 3 | reset 뒤 [F, F, T] |
| `oneSecondSetting` | "seconds 1이면 넘은 초에 바로 불안정이다" | `new InstabilitySettings(0.02, 1)`, 0.03, 0.0 | [T, F] |

### 6.3 `grade/InflowMonitorTest` (추가)
`monitor = new InflowMonitor(TestProperties.INFLOW)`. 도우미 `run(Double[] ratios, Double count)` → `List<InflowStatus>`.

| 메서드 | `@DisplayName` | 입력 (t0부터, count) | 기대 |
|---|---|---|---|
| `onAt5sAverage` | "5초 평균이 기준을 넘는 초에 켠다" | 0.4 × 3, 0.8 × 3, count 5 | t0~t3 평균 null·꺼짐, t4 평균 0.56 꺼짐, t5 평균 0.64 켜짐 |
| `nullUntilWindowFull` | "창이 다 차기 전에는 평균이 null이다" | 0.7 × 5, count 5 | t0~t3 평균 null·꺼짐 (t2부터 non-null 3개여도), t4 평균 0.7 켜짐 |
| `nullInWindow` | "창 안 null은 빼고 평균을 낸다" | 0.7, null, 0.8, 0.7, 0.9, count 5 | t0~t3 null·꺼짐, t4 평균 0.775 켜짐 |
| `tooFewSamplesStaysOff` | "창 안 값이 3개 미만이면 평균은 null이다" | 0.9, null, null, null, 0.9, null × 5, count 5 | 매 초 평균 null, 꺼짐 |
| `strictlyAboveRatio` | "평균이 기준과 같으면 켜지 않는다" | `new InflowSettings(0.5, 5, 3, 10, 3.0)`, 0.5 × 5, 이어서 0.75, count 5 | t4 평균 0.5 꺼짐, t5 평균 0.55 켜짐 |
| `blockedBelowMinCount` | "구역 인원이 3명 미만이면 켜지 않는다" | 0.7 × 5, count 2.9 | t4 평균 0.7, 꺼짐 |
| `countBoundaryIncluded` | "구역 인원이 정확히 3명이면 켤 수 있다" | 0.7 × 5, count 3.0 | t4 켜짐 |
| `nullCountBlocks` | "count null이면 켜지 않는다" | 0.7 × 5, count null | t4 평균 0.7, 꺼짐 |
| `offAfter10s` | "켜진 뒤 조건이 10초 연속 거짓이면 끈다" | 0.8 × 5, 이후 0.1 × 11, count 5 | t4 켜짐, t5 평균 0.66 참·켜짐, t6 0.52 거짓, t14 켜짐, t15 꺼짐 |
| `nullAverageCountsTowardOff` | "평균 null인 초도 끄는 연속에 센다" | 0.8 × 5, 이후 null × 12, count 5 | t4 켜짐, t5·t6 평균 0.8(값 4·3개), t7부터 평균 null, t15 켜짐, t16 꺼짐 |
| `trueResetsOffStreak` | "중간에 조건이 참이면 끄는 연속이 처음부터 다시 쌓인다" | 0.8 × 25. count: t0~t4 5, t5~t13 2, t14 5, t15~t24 2 | t4 켜짐, t13 켜짐(거짓 9초), t14 켜짐, t23 켜짐, t24 꺼짐 |
| `resetClears` | "초기화하면 창·경보가 비워진다" | 0.7 × 5(t4 켜짐), reset, 0.7 × 5, count 5 | reset 뒤 처음 4초 평균 null·꺼짐, 5번째 초 평균 0.7 켜짐 |

손 계산 (`offAfter10s`): t6 창 [0.8, 0.8, 0.8, 0.1, 0.1] = 2.6/5 = 0.52 → 거짓 1초. t15가 거짓 10초째 → 끔.
손 계산 (`trueResetsOffStreak`): 평균은 t4부터 늘 0.8. t5~t13 거짓 9초, t14 참(연속 0), t15~t24 거짓 10초 → t24 끔.

### 6.4 `grade/ZoneGraderTest` (수정·추가)
도우미는 6.1. `ONE = List.of(meta("c-0000", 4.0))`.

| 메서드 | `@DisplayName` | 입력 (t0부터) | 기대 |
|---|---|---|---|
| `instabilityToCritical` | "불안정 셀은 관측 등급이 심각이 되어 2초 뒤 심각으로 오른다" | `ONE`, 밀도 1.0, pressure 0.03, t0~t3 | `unstable` [F, F, T, T], 셀 [N, N, N, CR], 구역 [N, N, N, CR] |
| `instabilityOverridesDensity` | "불안정이면 밀도 등급보다 심각이 우선한다" | `ONE`, 밀도 4.5, pressure 0.03, t0~t3 | 셀 [N, A, A, CR] |
| `instabilityReleaseUsesDownHysteresis` | "불안정이 풀려도 심각은 10초 뒤 한 단계씩 내려간다" | `ONE`, 밀도 1.0. pressure t0~t3 0.03, t4~t13 0.0 | t4부터 `unstable` F. t12 CR, t13 A |
| `smallCellUnstableExcludedFromZone` | "작은 셀의 불안정은 자기 등급만 올리고 구역 등급에서 빠진다" | `METAS`, 밀도 [1.0, 1.0, 1.0], pressure [0.0, 0.0, 0.03], t0~t3 | t3 셀 [N, N, CR], `unstable` [F, F, T], 구역 N |
| `zoneCarriesInflow` | "유입 평균과 경보를 구역 결과에 담는다" | `ONE`, 밀도 1.0, pressure 0.0, inflow 0.8, count 5.0, t0~t4 | `inflowAvg` [null × 4, 0.8], `inflowAlert` [F, F, F, F, T] |
| `resetClearsInstabilityAndInflow` | "초기화하면 불안정 연속과 유입 창도 비운다" | `ONE`, 밀도 1.0, pressure 0.03, inflow 0.8, count 5.0, 5초(t4 `unstable` T·경보 켜짐), reset, 같은 프레임 1초 | reset 뒤 `unstable` F, 셀 N, `inflowAvg` null, `inflowAlert` F |
| `rejectedFrameNotObserved` | "거부한 프레임은 유입 창에 들어가지 않는다" | `METAS`, inflow 0.8, count 5.0. 정상 3초 → 셀 2개짜리 프레임(예외) → 정상 2초 | 4번째 정상 프레임 `inflowAvg` null(관측 4개), 5번째 0.8 |
| `gradesFixtureTimeline` (기대값 추가) | 그대로 | fixture 5초 | 기존 단언 + 모든 초 `unstable` [F, F, F], `inflowAvg` [null, null, null, null, 0.525], `inflowAlert` 모두 F |
- 기존 9개(`smallCellExcluded` 등)는 도우미만 바뀌고 기대값은 그대로다. 그 프레임의 pressure·inflow는 null이라 불안정·유입이 켜지지 않는다.
- `instabilityReleaseUsesDownHysteresis` 손 계산: 기록 [N, N, CR, CR] 뒤 t4~t13 관측 N 10개 → t13에 최근 10개가 모두 CR보다 낮아 A로 내리고 기록을 비운다.

### 6.5 `replay/ZoneRuntimeTest` (추가)
| 메서드 | `@DisplayName` | 입력 | 기대 |
|---|---|---|---|
| `resetsInflowOnWrap` | "반복으로 처음에 돌아오면 유입 창과 경보도 초기화한다" | `timelineWithInflow(5, 0.8, 5.0)`, loop, tick 10번 | t [0..4, 0..4], `inflowAlert` [F, F, F, F, T, F, F, F, F, T], `inflowAvg` 6번째(반복 t0)가 null |

### 6.6 `ws/MessageFactoryTest` (수정·추가)
| 메서드 | `@DisplayName` | 입력 | 기대 |
|---|---|---|---|
| `helloFromFixture` (수정) | "hello는 meta 원본·재생 상태·기준값·빈 미확인 알림을 담는다" | tick 전 `hello(runtime)` | thresholds == `new ThresholdsView(new DensityThresholds(3.0, 4.0, 5.0), 0.02, 0.6)`. 나머지 그대로 |
| `zoneStateCarriesInflowAlert` | "zone.inflow_alert는 판정 결과를 옮긴다" | `fixtureRuntime(timelineWithInflow(5, 0.8, 5.0))`, tick 4번 / 5번 | t3 `zone().inflowAlert()` F, t4 T. `zone().inflowRatio()` 0.8, `count()` 5.0 |
- `zoneStateAtT4`·`zoneStateAtT0KeepsNulls`는 그대로 통과해야 한다(fixture에서 경보 꺼짐, 0장).

### 6.7 `ws/MessageJsonTest` (수정)
- `HELLO_SAMPLE`의 thresholds를 7.1절로 바꾼다: `"thresholds": { "density": {...}, "pressure": 0.02, "inflow_ratio": 0.6 }`.
- `helloKeys`: thresholds 키 = {density, pressure, inflow_ratio}. `inflowRatio`가 `inflow_ratio`로 나가는지(전역 SNAKE_CASE) 여기서 확인한다.
- `zoneStateKeys`·`zoneStateMatchesSamples`는 그대로 통과해야 한다. 셀 키는 10개 그대로(`unstable` 없음, 1장 #13).

### 6.8 `config/CrowdsightPropertiesTest` (수정·추가, `Binder`)
`defaults()`에 키를 더한다: `crowdsight.instability.pressure`=0.02, `.seconds`=3, `crowdsight.inflow.ratio`=0.6, `.window-seconds`=5, `.min-samples`=3, `.off-seconds`=10, `.min-count`=3.

| 메서드 | `@DisplayName` | 입력 | 기대 |
|---|---|---|---|
| (S1~S3 16개) | 그대로 | 기본 맵 | 그대로 통과 |
| `bindsInstabilityAndInflowKeys` | "instability·inflow 키를 설정 record로 묶는다" | 기본 맵 | `instability()` == `TestProperties.INSTABILITY`, `inflow()` == `TestProperties.INFLOW` |
| `rejectsInvalidInstability` (`@CsvSource({"pressure, 0", "pressure, -0.01", "seconds, 0"})`) | "불안정 기준·초가 틀리면 거부한다" | `crowdsight.instability.{key}`=값 | `BindException`, 원인 메시지에 `{key}` |
| `rejectsInvalidInflow` (`@CsvSource({"ratio, 1.0", "ratio, -0.1", "window-seconds, 0", "min-samples, 0", "off-seconds, 0", "min-count, -1"})`) | "유입 설정 값이 틀리면 거부한다" | `crowdsight.inflow.{key}`=값 | 원인 메시지에 `{key}` |
| `rejectsMinSamplesAboveWindow` | "min-samples가 창보다 크면 거부한다" | `min-samples`=6 | 원인 메시지에 `min-samples`와 `window-seconds` |
| `rejectsMissingSection` (`@ValueSource(strings = {"instability", "inflow"})`) | "instability·inflow 설정이 없으면 거부한다" | `crowdsight.{key}.` 키 모두 제거 | 원인 메시지 `crowdsight.{key}` |

`CrowdsightServerApplicationIntegrationTest` 추가:

| 메서드 | `@DisplayName` | 기대 |
|---|---|---|
| `bindsDefaultInstabilityInflowSettings` | "application.yml의 불안정·유입 기본값을 읽는다" | `props.instability()` == `TestProperties.INSTABILITY`, `props.inflow()` == `TestProperties.INFLOW` |

### 6.9 통합 테스트 (`ws/ZoneWebSocketIntegrationTest`)
- `helloFirst`에 단언 2개를 더한다: `thresholds.pressure` == 0.02, `thresholds.inflow_ratio` == 0.6.
- `zoneStateMatchesFixtureAtT4`(`inflow_alert` false, 셀 등급 [C, N, A], 셀 키 10개)는 그대로 통과해야 한다. fixture t4 평균 0.525, `count` null이라 경보가 꺼져 있다(0장).

## 7. 출력 예시 (PR 설명·나예린 님 전달용)
`MessageJsonTest`가 7.1과 같은지 트리로 확인한다.

### 7.1 `hello` (fixture, 재생 t=2에 접속) — S3 7.1에서 `thresholds`만 바뀜
```json
{
  "type": "hello",
  "schema_version": "0.2",
  "zone_id": "zone-test",
  "meta": { "...": "S3 계획 7.1과 같다" },
  "playback": { "state": "playing", "t": 2, "loop": true, "duration_s": 5 },
  "thresholds": {
    "density": { "caution": 3.0, "alert": 4.0, "critical": 5.0 },
    "pressure": 0.02,
    "inflow_ratio": 0.6
  },
  "unacked_alerts": []
}
```
- `MessageJsonTest.HELLO_SAMPLE`에는 `meta`를 줄이지 않고 S3 그대로 둔다.

### 7.2 `zone_state` (fixture)
- t0·t4는 `server_s3_ws_plan.md` 7.2·7.3과 같다. fixture에서는 불안정·유입 조건이 켜지지 않는다(0장 표).

### 7.3 유입 경보가 켜진 `zone` (합성 타임라인 `timelineWithInflow(5, 0.8, 5.0)` t4, `zoneStateCarriesInflowAlert`)
```json
"zone": { "grade": "NORMAL", "max_density": null, "inflow_ratio": 0.8, "inflow_alert": true, "count": 5.0 }
```
- `inflow_ratio`는 그 초의 원래 값이다. 경보 판정에 쓴 5초 평균은 보내지 않는다(S5 `INFLOW.value`로 나간다).

### 7.4 불안정 셀 (설명용, `ZoneGraderTest.instabilityToCritical` t3 상황)
```json
{ "cell_id": "c-0000", "grade": "CRITICAL", "density": 1.0, "vx": null, "vy": null, "speed_var": null,
  "pressure": 0.03, "counterflow": null, "density_pred_60s": null, "grade_pred_60s": null }
```
- 밀도는 정상이어도 셀 `grade`가 `CRITICAL`이다. 화면은 별도 `unstable` 키 없이 `grade`로 표시한다(`[토론]` 1).

## 8. 이후 PR이 붙일 곳 (S4에서 만들지 않음)
| PR | 붙는 곳 | 내용 |
|---|---|---|
| S5 | `AlertDetector.detect(ZoneEvaluation)` | `INFLOW`: `inflowAlert` F → T, level CAUTION, value `inflowAvg`(소수 자리 반올림 여부는 S5), `cell_ids` [] |
| S5 | 같음 | `INSTABILITY`: `eligible && unstable`인 셀이 하나라도 F → T. level CRITICAL, value 그 셀들의 최대 `state().pressure()`, `cell_ids` = 그 셀들(meta 순서) |
| S5 | 같음 | `GRADE_UP`: 불안정으로 구역이 심각이 되면 `INSTABILITY`(t2) 뒤 `GRADE_UP` 심각(t3)이 따로 온다 (api-spec 3.3, `[토론]` 3) |
| S5 | `ZoneRuntime` | discontinuity면 `grader.reset()`과 함께 `AlertDetector.reset()` |
| S7 | `/api/health` | 필요하면 구역별 `inflow_alert`. 지금은 계획에 없음 |
| E5 이후 | `application.yml` | `instability.pressure`·`seconds`를 E5 결과로 바꾼다. 코드 변경 없음 |

## 9. `server_impl_plan.md` 정정 (이 PR의 docs 커밋)
1. 1.1절 패키지 `grade/`: `InstabilitySettings, InflowSettings, InstabilityTracker, InflowMonitor, InflowStatus`를 넣는다.
2. 1.2절 흐름: `ZoneGrader.evaluate(frame) → ZoneEvaluation (S2, S4: 셀마다 InstabilityTracker, 구역 InflowMonitor)`. discontinuity 줄은 "ZoneGrader.reset()(히스테리시스·불안정·유입 모두)".
3. 2장 S2 코드 블록 주석 정리:
   - 211행 `// 불안정 설정(pressure·seconds)은 S4가 crowdsight.instability.* 별도 record로 추가` → `InstabilitySettings(double pressure, int seconds)`, `InflowSettings(double ratio, int windowSeconds, int minSamples, int offSeconds, double minCount)` (S4).
   - 238행 `CellEvaluation(..., boolean eligible, boolean unstable /* S4 */, CellState state)`.
   - 240행 `ZoneEvaluation(int t, Grade zoneGrade, Double maxDensity, Double inflowAvg, boolean inflowAlert, List<CellEvaluation> cells)` (inflowAvg·inflowAlert는 S4).
   - 242행 `ZoneGrader(List<CellMeta> cells, GradeSettings grade, InstabilitySettings instability, InflowSettings inflow)` (S4부터).
4. 2장 S3: 328행 `ThresholdsView(DensityThresholds density, double pressure, double inflowRatio)`(pressure·inflowRatio는 S4). 347행 "S3의 `inflow_alert`는 항상 false (S4에서 실제 값)"은 그대로 둔다(S3 당시 사실).
5. 2장 S4:
   - 코드 블록 생성자를 `InstabilityTracker(InstabilitySettings settings)`, `InflowMonitor(InflowSettings settings)`로 바꾼다.
   - 388행 "셀 관측 등급 = `unstable ? CRITICAL : ofDensity(density)` (같은 결과, density null이면 null)".
   - 393행 "`CrowdsightProperties`: `1 ≤ min-samples ≤ window-seconds` 검사" → "`InflowSettings`가 `1 ≤ min-samples ≤ window-seconds`, `0 ≤ ratio < 1`, 초 ≥ 1, `min-count` ≥ 0을 검사. `InstabilitySettings`가 `pressure` > 0, `seconds` ≥ 1을 검사".
   - 불안정 비교는 초과(`>`), 기준과 같으면 연속 0이라고 적는다. `unstable`·5초 평균은 `zone_state`로 보내지 않는다고 적는다.
   - 테스트 표 끝에 "상세는 `docs/plans/server_s4_instability_inflow_plan.md` 6장"을 단다. 표에 `InflowMonitorTest.trueResetsOffStreak`, `ZoneGraderTest.instabilityReleaseUsesDownHysteresis`, `ZoneRuntimeTest.resetsInflowOnWrap`를 더한다.
6. 4장 설명 문단: compact constructor 검사 목록의 `1 ≤ inflow.min-samples ≤ inflow.window-seconds`를 "(`InflowSettings`가 검사)"로 고친다. yml 주석은 3.1절과 같게 한다.
7. 6장 null 표 `pressure` 행: "null이거나 기준 이하(같은 값 포함)이면 불안정 연속 0. 사람 없는 셀은 0이라 역시 끊는다".

## 10. TDD 단계
공통 (Git Bash, `server/`):
```bash
cd /c/Users/Woori/Desktop/project/Triple-Y/server && JAVA_HOME="/c/Program Files/Eclipse Adoptium/jdk-21.0.13.9-hotspot" ./gradlew test --tests '<패턴>' --no-daemon
```
> **에이전트는 `bootRun`을 실행하지 않는다** (포그라운드·백그라운드 모두). 확인은 `test`·`build`로 한다.

각 단계의 Red는 "테스트 먼저 작성 → 컴파일 실패 또는 단언 실패 확인"이다.

| 단계 | 할 일 (Red → Green) | `--tests` | 완료 조건 |
|---|---|---|---|
| 0 | 브랜치 확인: `git switch feat/server-instability-inflow`, `git log --oneline main..HEAD`가 `87252c8`·`73f6f28` 2개 | — | `git status --short`에 `?? CLAUDE.local.md`·`?? docs/plans/server_s4_instability_inflow_plan.md`만 있음. 시작 전 전체 `./gradlew test --no-daemon` 통과 |
| 1 | `CrowdsightPropertiesTest` 추가 5개·`defaults()`, `bindsDefaultInstabilityInflowSettings`, `TestProperties.INSTABILITY·INFLOW·full` → `InstabilitySettings`, `InflowSettings`, `CrowdsightProperties`(instability·inflow), yml | `'com.tripley.crowdsight.config.*'` 다음 `'com.tripley.crowdsight.CrowdsightServerApplicationIntegrationTest'` | config 21메서드 통과(신규 5메서드 = 13회), 앱 통합 6메서드 통과 |
| 2 | `InstabilityTrackerTest` → `InstabilityTracker` | `'com.tripley.crowdsight.grade.InstabilityTrackerTest'` | 6메서드 통과 |
| 3 | `InflowMonitorTest` → `InflowStatus`, `InflowMonitor` | `'com.tripley.crowdsight.grade.InflowMonitorTest'` | 12메서드 통과 |
| 4 | `ZoneGraderTest` 도우미·신규 7개·`gradesFixtureTimeline` 기대값, `TestProperties.grader`, 테스트 호출 6곳 교체 → `CellEvaluation`, `ZoneEvaluation`, `ZoneGrader`, `ZoneRegistry.register` | `'com.tripley.crowdsight.grade.*'` 다음 `'com.tripley.crowdsight.replay.*'` | grade 전부 통과(`ZoneGraderTest` 17메서드). replay 기존 테스트 통과 |
| 5 | `TimelineFixtures.timelineWithInflow`, `ZoneRuntimeTest.resetsInflowOnWrap` (Green은 4단계 코드로 이미 통과해야 한다. 실패하면 `reset` 누락) | `'com.tripley.crowdsight.replay.ZoneRuntimeTest'` | 3메서드 통과 |
| 6 | `MessageFactoryTest`(수정 1, 추가 1), `MessageJsonTest`(예시·키), `helloFirst` 단언 → `ThresholdsView`, `MessageFactory`, Javadoc(`HelloMessage`·`ZoneView`) | `'com.tripley.crowdsight.ws.Message*'` 다음 `'com.tripley.crowdsight.ws.ZoneWebSocketIntegrationTest'` | Message 14메서드(16회), 통합 10메서드(11회) 통과 |
| 7 | `ReplayScheduler` DEBUG 로그(4.5절). 테스트 없음 | `'com.tripley.crowdsight.replay.*'` | 기존 통과 |
| 8 | 전체 실행 | 없음 (`./gradlew test --no-daemon`) | 모든 테스트 통과 |
| 9 | README 판정 절(아래), `server_impl_plan.md` 9장 정정 | — | 문구만 |
| 10 | 전체 검증 (아래 표) | — | 모두 기대대로 |

README 추가 절 (`## WebSocket (S3)` 아래):
````markdown
## 판정 기준 (S4)
- 기준값은 `application.yml`의 `crowdsight.grade.*`(밀도), `crowdsight.instability.*`(군중 압력), `crowdsight.inflow.*`(유입)에 있다. 화면은 `hello.thresholds`로 같은 값을 받는다.
- 불안정: 셀 `pressure`가 0.02를 3초 연속 넘으면 그 셀은 심각 조건이다. `null`이거나 기준 이하면 연속이 끊긴다. 심각은 조건이 풀려도 10초에 한 단계씩 내려간다.
- 유입 경보(`zone.inflow_alert`): `inflow_ratio` 최근 5초 평균(값 3개 이상일 때)이 0.6을 넘고 `count`가 3명 이상이면 켜진다. 10초 연속 조건이 거짓이면 꺼진다. 반복·이동 뒤 처음 4초는 평균이 없다.
- DEBUG 로그 `재생 zone=… inflow_avg=… inflow_alert=…`로 5초 평균을 확인한다 (평균은 메시지로 보내지 않는다).
- 가짜 타임라인은 `inflow_ratio`가 0.6을 넘지 않아 유입 경보가 켜지지 않는다. 판정은 단위 테스트로 확인한다.
````

10단계 검증:

| # | 명령 (`server/`) | 기대 |
|---|---|---|
| 1 | `JAVA_HOME=… ./gradlew clean build --no-daemon` | `BUILD SUCCESSFUL` |
| 2 | `grep -h -o 'tests="[0-9]*" skipped="[0-9]*" failures="[0-9]*" errors="[0-9]*"' build/test-results/test/*.xml` | 모든 줄 `failures="0" errors="0"` |
| 3 | `grep -rn 'springframework' src/main/java/com/tripley/crowdsight/grade` | 출력 없음 |
| 4 | `grep -rnE '0\.02\b\|0\.6\b' src/main/java` | 출력 없음 (기준값은 yml에만) |
| 5 | `grep -rn 'inflow_alert는 S4' src/main` | 출력 없음 (S3 자리 주석 제거) |
| 6 | `grep -rnE 'Instant\.now\|currentTimeMillis' src/main` | 출력 없음 |
| 7 | `grep -rnE '@(Data\|Getter\|Setter\|Builder\|Value\|AllArgsConstructor\|NoArgsConstructor)\b' src` | 출력 없음 |
| 8 | `grep -rn 'com.fasterxml.jackson.databind' src` | 출력 없음 |
| 9 | `grep -rnP '\t' src README.md` | 출력 없음 |
| 10 | 바뀐 `.java` 파일에 120자 초과 줄 없음 (문자 수 기준) | 출력 없음 |
| 11 | stage 뒤 `git -C .. ls-files --eol server \| grep -v 'i/lf'` | `gradle-wrapper.jar`, `gradlew.bat`만 |
| 12 | `git -C .. status --short` | `CLAUDE.local.md`가 stage되지 않음 |

커밋 제안:
1. `feat: 불안정·유입 판정 설정 추가` (`InstabilitySettings`, `InflowSettings`, `CrowdsightProperties`, yml, `TestProperties`, 설정 테스트)
2. `feat: 불안정 심각 판정과 유입 경보 (S4)` (`InstabilityTracker`, `InflowMonitor`, `InflowStatus`, 평가 record, `ZoneGrader`, `ZoneRegistry`, `ReplayScheduler` 로그, 메시지, 테스트)
3. `docs: S4 계획 추가, 구현 계획 정정, README 판정 설명`

## 11. PR 설명 (초안)
제목: `feat: 불안정 심각 판정과 유입 경보 (S4)` / 기준 `main` ← `feat/server-instability-inflow` (쌓인 PR 아님)

> **함께 들어가는 커밋**: S3 리뷰 반영 `73f6f28`(join 경쟁·drop 중복·`WsPingScheduler` final), `87252c8`(join 끊김 로그 중복·경쟁 테스트 스레드 종료). #47 병합 뒤 나온 리뷰 수정이라 `main`에 없어서 이 브랜치에 cherry-pick했다. 이 두 커밋을 다른 PR로 먼저 병합하면 이 브랜치를 `main`에 rebase해 빠지게 한다.

- 목적: 셀 군중 압력이 기준을 3초 연속 넘으면 그 셀을 심각으로 올리고, 구역 유입 비율 5초 평균으로 유입 경보를 켜고 끈다. 화면은 `hello.thresholds`에서 압력·유입 기준값을, `zone_state.zone.inflow_alert`에서 실제 경보 상태를 받는다.
- 변경:
  - 설정 `crowdsight.instability.*`(압력 0.02, 3초), `crowdsight.inflow.*`(0.6, 5초 창, 값 3개 이상, 10초 끔, 3명 이상). 값 검사는 `InstabilitySettings`·`InflowSettings`
  - `grade/`: `InstabilityTracker`(셀 연속 초과), `InflowMonitor`(원형 버퍼 5초 평균, 켬·끔), `InflowStatus`. `ZoneGrader`가 셀 관측 등급 = 불안정이면 심각, 아니면 밀도 등급으로 판정하고 유입을 같이 판정한다. `reset`이 모두 비운다(반복·이동)
  - `CellEvaluation.unstable`, `ZoneEvaluation.inflowAvg`·`inflowAlert` (S5 알림 입력)
  - `hello.thresholds`에 `pressure`·`inflow_ratio`, `zone.inflow_alert` 실제 값. `hello.schema_version`은 `"0.2"` 그대로(api-spec v0.2가 이미 정의한 키)
  - 재생 DEBUG 로그에 `inflow_avg`·`inflow_alert`
- 바뀌지 않은 것: `zone_state` 셀 키(10개, `unstable` 없음), `zone.inflow_ratio`(원래 값). fixture에서는 두 조건이 켜지지 않아 S3 출력 예시가 그대로다.
- 출력 예시: 계획 7.1(`hello`), 7.3(`inflow_alert` true인 `zone`).
- 참고 결정: 결정 6(`count` 3명 미만 제외), 결정 기록 8(창이 다 찬 뒤 non-null 3개 이상이면 평균), api-spec 4.2~4.4, 조사 반영("불안정 10초 유지" → 내림 히스테리시스).

> [!IMPORTANT]
> **CS 이슈**
> | **주제** | **내용** |
> |---|---|
> | **슬라이딩 윈도우와 원형 버퍼** | 최근 5초를 `Double[]` 원형 버퍼로 둔다. 갱신 O(1), 평균 O(창 크기). `ArrayDeque`는 null 원소를 받지 않아 "관측 없음" 칸을 표현할 수 없다 |
> | **결측값(null)과 0의 구분** | `pressure` null(머리 부족)은 "모름"이고 0(사람 없음)은 "측정값 0"이다. 둘 다 불안정 연속을 끊지만, 유입 창에서 null은 평균에서 빠지고 칸만 차지한다. 값이 3개 미만이면 평균 자체를 내지 않는다 |
> | **히스테리시스(슈미트 트리거)** | 유입 경보는 켜기(1초 참)와 끄기(10초 연속 거짓)가 비대칭이라 기준 근처에서 깜빡이지 않는다. 불안정은 연속 3초(디바운스)로 켜고, 해제는 등급 내림 10초 규칙에 맡긴다 |
> | **연속 카운터(run-length)** | 불안정은 "연속 초"만 세므로 정수 하나로 충분하다. 상한을 두어 장시간 재생에도 넘치지 않는다 |
> | **부동소수 비교** | 기준은 초과(`>`)다. 흐름 출력이 4자리라 0.02와 같은 값이 실제로 나온다. 평균 테스트는 허용 오차로 비교하고, 경계 테스트는 이진수로 정확한 0.5를 쓴다 |
> | **상태 초기화와 불연속** | 반복·이동으로 `t`가 끊기면 히스테리시스·불안정 연속·유입 창을 함께 비운다. 이전 재생의 값이 새 재생의 평균에 섞이지 않는다 |
> | **스레드 한정** | 판정 상태는 재생 주기 작업 하나만 건드린다. 잠금이 없다. `hello`는 불변 설정 record만 읽는다 |
> | **설정 검증 (fail-fast)** | 틀린 기준값(`min-samples` > 창, `ratio` ≥ 1 등)은 바인딩 때 예외로 서버 시작을 멈춘다. 시연 중에 "경보가 영원히 안 켜지는" 설정 실수를 막는다 |

| 선택 | 대안 | 고른 이유 |
|---|---|---|
| 판정기가 설정 record를 받음 | 원시 값 생성자(계획 초안) | 값 검사가 record 한 곳에만 있다 |
| 유입 판정을 `ZoneGrader` 안에 | `ZoneRuntime`에 따로 | 초기화 경로(`grader.reset()`)와 결과 묶음(`ZoneEvaluation`)이 하나다 |
| 관측 = 불안정이면 CR, 아니면 밀도 등급 | `max(ofDensity, …)` | 결과가 같고 밀도 null 처리가 분명하다 |
| `unstable`·5초 평균을 메시지에 안 넣음 | `cells[].unstable`, `zone.inflow_avg` 추가 | api-spec v0.2 형식을 지킨다. 넣을지는 화면과 정한다 |
| 별도 "10초 유지" 타이머 없음 | 불안정 해제 뒤 10초 `unstable` 유지 | 셀 등급 내림 10초 히스테리시스가 이미 심각을 10초 이상 유지한다(조사 반영) |
| 원형 버퍼 | `LinkedList<Double>`(null 허용) | 크기 고정, 할당 없음 |

리뷰 요청:
- 관측 등급 규칙과 작은 셀 불안정 처리(자기 등급만, 구역 제외)
- 유입 끄는 연속에 평균 null·`count` 부족 초를 넣는 것(api-spec 4.4 가정)
- `pressure` == 기준을 "넘지 않음"으로 보는 것
- `unstable`·5초 평균을 메시지에 넣지 않은 것

남은 일:
- S5(`alert`: `INFLOW`·`INSTABILITY`·`GRADE_UP`, `unacked_alerts`)
- E5 결과로 `instability.pressure`·`seconds` 조정 (조영준)
- 실제 E04_039·E05_035 타임라인에서 `pressure` null이 연속을 끊는 빈도 확인 `[토론]`

## 12. 위험·가정·`[토론]`
| 위험 | 대응 |
|---|---|
| 실제 흐름 출력에서 `pressure` null이 잦으면 3초 연속이 자주 끊겨 불안정이 거의 켜지지 않는다 | 규칙은 api-spec 4.3대로 유지. E5 때 null 빈도를 보고 `seconds`를 줄이거나 null을 건너뛰는 규칙으로 바꿀지 정한다(`[토론]` 4). 바꿔도 `InstabilityTracker.update` 한 곳이다 |
| 0.02/s²는 측정 방법(머리 높이 평면, 패치 반경)에 따라 크기가 달라 그대로 맞지 않을 수 있다 | yml 값만 바꾼다. 화면은 `hello.thresholds.pressure`로 같은 값을 받는다 |
| 가짜·fixture 데이터로는 경보가 켜지지 않아 통합 테스트가 켜진 상태를 못 본다 | 단위(`InflowMonitorTest`, `ZoneGraderTest`)와 합성 타임라인(`ZoneRuntimeTest`, `MessageFactoryTest`)으로 켜진 상태와 메시지 연결을 확인한다 |
| `CrowdsightProperties` 성분이 늘어 `TestProperties.full` 외에 직접 만드는 곳이 있으면 컴파일이 깨진다 | 0장: 직접 만드는 곳은 `TestProperties.full` 하나다 |
| `ZoneEvaluation`·`CellEvaluation` 성분 순서가 바뀌어 위치 인자가 섞임 | 만드는 곳은 `ZoneGrader` 하나다. 테스트는 접근자로 읽는다 |
| 평균 합산 순서(원형 버퍼 칸 순서) 때문에 S5 `INFLOW.value`가 마지막 자리에서 달라질 수 있다 | 판정에는 영향이 없다(기준과 1e-15 차이로 같은 경우만 다름). 표시 반올림은 S5가 정한다 |

가정:
- (가정) 유입 끄는 연속에 평균 null·`count` < 3·`count` null인 초도 거짓으로 센다(api-spec 4.4).
- (가정) 꺼진 상태에서 거짓인 초는 세지 않는다. 그래서 끔 조건은 "켜진 뒤" 10초 연속 거짓이다.
- (가정) 불안정이 풀린 초에 `unstable`은 바로 false다. S5 `INSTABILITY` 해제·재전송도 이 값으로 정한다.
- (가정) 기준값 0.02, 3초, 0.6, 3개, 10초는 api-spec 8절 가정 값 그대로다.

`[토론]`:

| # | 안건 | 초안 | 누구와 |
|---|---|---|---|
| 1 | `zone_state.cells[]`에 `unstable`(bool)을 보낼지. 화면이 "난류" 표시(깜빡임)를 밀도 심각과 구분하려면 필요하다 | 보내지 않음(api-spec v0.2 유지). 필요하면 api-spec v0.3에서 키 추가 | 나예린 |
| 2 | 판정에 쓴 5초 평균(`inflow_avg`)을 `zone_state.zone`에 보낼지. 그래프 기준선(0.6)과 비교하는 값이 원래 값이면 경보 시점과 그래프가 어긋나 보인다 | 보내지 않음. 원래 값과 기준선만 그림 | 나예린 |
| 3 | 불안정이 `INSTABILITY`(t2)와 `GRADE_UP` 심각(t3)을 둘 다 만드는 것 (api-spec 10절 9번) | S5에서 명세대로 둘 다 | 이유노, 나예린 |
| 4 | `pressure` null이 3초 연속을 끊는 규칙 (계획 9장 `[토론]` 11). 끊김이 잦으면 "null은 건너뜀(연속 유지)"으로 바꿀지 | 끊음 유지, E5 때 빈도 확인 | 조영준, 이유노 |
| 5 | 압력 기준 0.02와 3초 (api-spec 10절 2번) | E5 결과로 조정 | 이유노 |
| 6 | 불안정 판정에 `counterflow` (api-spec 10절 8번, `timeline-spec.md` 4절 문구) | 쓰지 않음. 흐름 모듈이 값을 쓰지 않아 늘 null | 이유노 |
| 7 | 작은 셀(2㎡ 미만)의 불안정이 자기 셀 등급을 심각으로 올리는 것. 화면 히트맵에 빨강으로 보이지만 구역 등급·알림에는 없다 | 결정 4와 같게 자기 등급만 | 이유노, 나예린 |
| 8 | 유입 `ratio` 설정 범위 `0 ≤ ratio < 1` | 이대로 | 조영준 |

---

### Critical Files for Implementation
- C:\Users\Woori\Desktop\project\Triple-Y\server\src\main\java\com\tripley\crowdsight\grade\ZoneGrader.java
- C:\Users\Woori\Desktop\project\Triple-Y\server\src\main\java\com\tripley\crowdsight\config\CrowdsightProperties.java
- C:\Users\Woori\Desktop\project\Triple-Y\server\src\main\java\com\tripley\crowdsight\ws\MessageFactory.java
- C:\Users\Woori\Desktop\project\Triple-Y\server\src\test\java\com\tripley\crowdsight\config\TestProperties.java
- C:\Users\Woori\Desktop\project\Triple-Y\server\src\main\resources\application.yml
