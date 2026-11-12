# CrowdSight 서버(Spring Boot) MVP 구현 계획

| 항목 | 내용 |
|---|---|
| 작성일 | 2026-11-11 |
| 기준 문서 | `docs/api-spec.md` v0.1, `docs/timeline-spec.md` v0.2, `docs/decisions-2026-11-11.md`, `docs/proposal.md` v3.1 |
| 대상 | `server/` (Spring Boot 4.1.2, Spring Framework 7.0.10, Java 21, Gradle 9.8.2 Groovy DSL) |
| 상태 | 계획. 조영준 결정 반영(11-11), main #32~#40 재점검 반영(11-11). `[토론]`은 팀원과 정한다 |
| 조사 | `docs/research/server_research.md` (검증표 3절 반영), `docs/research/server_recheck_2026-11-11.md` (main 병합분 재점검, 2절 영향 표 반영) |

## 결정 기록 (조영준, 11-11)
| # | 안건 | 결정 |
|---|---|---|
| 1 | 느린 화면 | Tomcat 차단 전송 제한 2초: 세션 생성 때 네이티브 세션 사용자 속성 `org.apache.tomcat.websocket.BLOCKING_SEND_TIMEOUT` = 2000L. 넘기면 그 세션만 닫고 화면은 재접속해 `hello`로 복구. 데코레이터 한도는 재생 스레드 혼자 보낼 때 검사되지 않으므로 이것에 기대지 않는다 |
| 2 | 허용 출처 | `setAllowedOriginPatterns("http://localhost:*", "http://127.0.0.1:*")`, 값은 `crowdsight.cors-origin-patterns` 설정 |
| 3 | Java 규칙 | 3장 제안 + Lombok (`@RequiredArgsConstructor`, `@Slf4j`). DTO는 `record` 유지. 버전은 Boot 의존성 관리 |
| 4 | 히스테리시스 null | 건너뜀 (등급 유지, 연속 유지) |
| 5 | PR 순서 | S4(불안정·유입)는 S3 뒤 |
| 6 | S0 범위 | `crowdsight.*` 설정과 `@ConfigurationPropertiesScan`은 S1부터 쓰는 PR에서 |
| 7 | v0.2 검증 | 서버 타임라인 검증을 `src/predict/schema.py`·`web/src/lib/validate.ts`(main, #35)와 같게 한다. `schema_version` 둘째 자리 ≥ 2이면 `frames[].count`·`cells[].counterflow` 키 필수(값 null 가능), v0.1이면 키 생략 허용(null로 읽음). `counterflow` 0~1, `count` ≥ 0 |
| 8 | 유입 평균 | 창이 다 찬 뒤에만 평균을 낸다: 시작·초기화(반복·이동) 뒤 5초 관측이 쌓이기 전에는 평균 null(초기화 뒤 첫 평균은 t4). 그 뒤 최근 5초 중 non-null `inflow_ratio`가 `min-samples`(기본 3, `crowdsight.inflow.min-samples`)개 이상이면 그 값들의 평균, 아니면 평균 null·조건 거짓. 평균 null인 초도 끄는 연속에 센다 |

- 본문의 "결정 4·6·9"는 `docs/decisions-2026-11-11.md`의 팀 결정 번호다. 이 표는 "결정 기록 N"으로 인용한다.

## 조사 반영 (server_research.md 3절)
- 테스트 엔진은 JUnit Jupiter 6.0.3 (JUnit 5 아님).
- `TimelineValidator`는 `JsonNode.isIntegralNumber()`로 정수 필드를 검사한다. Jackson이 `t: 1.5`를 조용히 1로 바꾸기 때문. 테스트 `rejectsFractionalT`.
- `interval_s == 1`은 `schema.py`·`validate.ts`에 없는 서버 추가 규칙이다.
- `broadcast`는 `IOException`과 `RuntimeException`(한도 초과 `SessionLimitExceededException` 포함)을 모두 잡아 `close(CloseStatus.SESSION_NOT_RELIABLE)` 후 뺀다. 테스트 케이스 추가.
- bootRun 가짜 타임라인은 `fake_E04_039.json`으로 만들고 실행 인자로 지정한다 (명령: 조사 1.3절).
- 상세 3.3 "불안정 10초 유지"는 셀 등급 내림 10초 히스테리시스로 대체한다.
- S6 테스트에 `@AutoConfigureMockMvc`를 명시한다.
- 웹은 #35로 v0.2 필드를 반영했다 → 8장 #6 해결. 남은 불일치(8장 #1~#5, #7~#13)는 S3 전에 다시 확인한다 (재점검 3.3절).

## 0. 확인한 사실
- 의존성: Spring Framework 7.0.10, Tomcat 11.0.27, **Jackson 3.1.7** (`tools.jackson.core:jackson-databind`).
  - 코드는 `tools.jackson.databind.*` (`JsonMapper`, `JsonNode`, `PropertyNamingStrategies`).
  - 어노테이션은 `com.fasterxml.jackson.annotation.*` (jackson-annotations 2.21).
  - Jackson 3 `JacksonException`은 unchecked. Boot 4는 `JsonMapper` 빈을 자동 생성. `readTree(Path)`, `treeToValue(TreeNode, Class)` 있음.
- WebSocket(jar 확인): `TextWebSocketHandler`, `WebSocketConfigurer`, `@EnableWebSocket`, `ConcurrentWebSocketSessionDecorator(session, int, int, OverflowStrategy)`, `PingMessage`, `StandardWebSocketClient.execute(handler, uriTemplate, vars...)` (CompletableFuture).
- 테스트: `spring-boot-starter-test`에 JUnit Jupiter 6.0.3, AssertJ, Mockito, Awaitility 4.3.0, JSONassert, json-path. 의존성 추가 없음.
- MockMvc 어노테이션 패키지: `org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc`.
- `docs/api-spec.md`는 main에 있다 (#22 병합). D1은 main에서 새 브랜치로 고친다.
- `src/counting/fake_timeline.py`: `inflow_ratio` 최대 0.6, 기준 `> 0.6`이라 가짜 데이터로는 유입 경보가 켜지지 않는다 → 유입 경보는 손으로 만든 fixture로 시험.
- 로컬에 `data/processed/timeline/` 없음. bootRun 전에 가짜 타임라인 생성.
- 생산자(`run_density.py`, `fake_timeline.py`)는 `schema.py`의 `SCHEMA_VERSION`을 써서 `"0.2"`로 저장하고 `count`·`counterflow` 키를 모두 쓴다. 예측 모듈을 거쳐도 두 키가 남는다 (#35).
- 흐름 출력(#36·#37): 경계에 움직이는 머리가 `inflow_min_heads`보다 적으면 `inflow_ratio` null(소수 2자리), 셀 머리가 `min_heads`보다 적으면 `vx`·`vy`·`speed_var`·`pressure` null. `counterflow`는 쓰지 않아 실제 파일에서 늘 null.

## 1. 구조

### 1.1 패키지
```text
com.tripley.crowdsight
├─ CrowdsightServerApplication      @SpringBootApplication @ConfigurationPropertiesScan
├─ config/    CrowdsightProperties, WebSocketConfig, ClockConfig, ReplaySchedulerConfig, CorsConfig
├─ timeline/  ZoneTimeline, Meta, CellMeta, Models, Prediction, Frame, CellState,
│             TimelineLoader, TimelineValidator, InvalidTimelineException
├─ replay/    ZonePlayer, PlaybackState, PlaybackSnapshot, Tick, ZoneRuntime, ZoneRegistry, ReplayScheduler
├─ grade/     Grade, GradeRule, GradeSettings, GradeHysteresis, ZoneGrader, CellEvaluation, ZoneEvaluation,
│             InstabilityTracker, InflowMonitor                              (Spring 의존 없음)
├─ alert/     Alert, AlertReason, AlertDetector, AlertIdGenerator, AlertStore, AlertLogWriter, AlertController
├─ ws/        ZoneWebSocketHandler, ZoneSessions, MessageFactory, FrameTimestamps,
│             message/ (HelloMessage, ZoneStateMessage, ZoneView, CellView, AlertMessage, PlaybackMessage, ThresholdsView)
└─ api/       ZoneController, HealthController
```
- `grade/`, `replay/` 핵심(`ZonePlayer`, `ZoneRuntime`)은 순수 Java. 테스트에 Spring 컨텍스트 불필요.
- Spring은 `config/`, `ws/`, `api/`, 조립 클래스(`ZoneRegistry`, `ReplayScheduler`)에만.

### 1.2 1초 처리 흐름 (재생 스레드 1개)
```text
ReplayScheduler.tickAll()                                ← scheduleAtFixedRate(interval-ms)
  └─ for each ZoneRuntime (구역마다 try/catch)
       ZonePlayer.tick()        → Tick(frame, discontinuity) 또는 없음(일시정지·끝)
       discontinuity이면 ZoneGrader.reset(), AlertDetector.reset()
       ZoneGrader.evaluate(frame) → ZoneEvaluation                         (S2, S4)
       AlertDetector.detect(eval) → List<Alert>                           (S5)
       MessageFactory → [playback?] → zone_state → alert…                 (S3, S5)
       ZoneSessions.broadcast(zoneId, json)  JSON 문자열은 한 번만 만든다
```
- 판정 상태는 재생 스레드만 읽고 쓴다 → 잠금 불필요.
- REST 제어(S7)는 `ZonePlayer`의 `synchronized` 메서드로 "다음 tick에 할 일"만 표시.

## 2. PR 단위 (결정 8 순서)

순서: **D1 → S0 → S1 → S2 → S3 → S4 → S5 → S6 → S7**.

| PR | 브랜치 | 내용 | 목표일 |
|---|---|---|---|
| D1 | `feat/api-spec-v02` | api-spec을 결정 4·6·9와 `count`에 맞게 고침 (7장) | 11-12 |
| S0 | `feat/server-skeleton` | 뼈대 커밋, `application.yml`, `.gitignore`에 `logs/`, CLAUDE.md server 규칙 | 11-12 |
| S1 | `feat/server-timeline-replay` | 타임라인 읽기·검증, 1초 재생 | 11-12 |
| S2 | `feat/server-grade` | 셀 등급, 히스테리시스, 구역 등급, 예측 등급 | 11-12 |
| S3 | `feat/server-ws-zone-state` | WS `hello`, `zone_state`, `playback`, ping | 11-13 (1차 연결) |
| S4 | `feat/server-instability-inflow` | 불안정 → 심각, 유입 경보 (5초 평균, `count` < 3이면 끔) | 11-16 |
| S5 | `feat/server-alert` | `alert`, 미확인 알림, `hello.unacked_alerts` | 11-16 |
| S6 | `feat/server-alert-ack` | `POST /api/alerts/{id}/ack`, `GET .../alerts`, `logs/alerts.jsonl` | 11-17 |
| S7 | `feat/server-playback-api` | 재생 제어 REST, `/api/zones`, `/meta`, `/health` | 11-18 |

- S4는 S3 뒤: G1 타임라인은 `pressure`·`inflow_ratio`가 null이라 11-13 연결에 불필요.
- 쌓인 PR은 CLAUDE.md 규칙대로 병합 전에 `into main` 확인.

### S0. 뼈대 (`feat/server-skeleton`)
1. `git switch main; git pull` → `git switch -c feat/server-skeleton`.
2. `server/`와 `.gitignore`만 stage. `src/flow/` 수정분은 넣지 않는다.
- `application.properties` 삭제, `application.yml` 생성. S0에는 `spring.*`·`server.port`만, `crowdsight.*`는 쓰는 PR에서 추가.
- `@ConfigurationPropertiesScan`은 S1에서 `CrowdsightProperties`와 함께.
- 루트 `.gitignore` 서버 절에 `server/logs/`.
- `server/.editorconfig`(공백 4칸, yml 2칸, LF), `server/.gitattributes`에 `* text=auto eol=lf`. Spotless 안 씀.
- CLAUDE.md "코드 컨벤션"에 `server/` 규칙 (3장 + 결정 3).
- `server/README.md`: JAVA_HOME·실행 명령 (Git Bash, PowerShell).
- 테스트: `CrowdsightServerApplicationIntegrationTest.contextLoads` 통과.

### S1. 타임라인 읽기·검증과 재생 (`feat/server-timeline-replay`)
```java
// timeline/ — 이름 변환은 전역 SNAKE_CASE(4장), 60s 필드만 직접 지정
@JsonIgnoreProperties(ignoreUnknown = true)
public record Meta(String zoneId, String cameraId, String videoId, int durationS, int intervalS,
                   double cellSizeM, Models models, Prediction prediction, List<CellMeta> cells) {}

@JsonIgnoreProperties(ignoreUnknown = true)
public record CellMeta(String cellId, int row, int col, double walkableAreaM2,
                       List<List<Double>> imagePolygon) {}

@JsonIgnoreProperties(ignoreUnknown = true)
public record Frame(int t, Double inflowRatio, Double count, List<CellState> cells) {}

/** 초별 셀 상태. density 외의 측정·예측 값은 null(관측 없음)일 수 있다. */
@JsonIgnoreProperties(ignoreUnknown = true)
public record CellState(String cellId, Double density, Double vx, Double vy, Double speedVar,
                        Double pressure, Double counterflow,
                        @JsonProperty("density_pred_60s") Double densityPred60s) {}

/** 구역 1개의 타임라인. metaJson은 hello.meta로 그대로 보낸다 (api-spec 3.1). */
public record ZoneTimeline(String schemaVersion, Meta meta, List<Frame> frames,
                           JsonNode metaJson, Path source) {
    public String zoneId() { return meta.zoneId(); }
    public int durationS() { return meta.durationS(); }
}
```
```java
/** 설정한 타임라인 파일을 읽고 검증한다. 하나라도 틀리면 서버를 시작하지 않는다. */
@Component
public class TimelineLoader {
    public TimelineLoader(JsonMapper jsonMapper, CrowdsightProperties props) { ... }
    /** timeline-dir + timeline-files 전부. 같은 zone_id 두 번이면 예외. */
    public List<ZoneTimeline> loadAll();
    /** readTree(Path) → TimelineValidator.validate(tree) → treeToValue(...) */
    ZoneTimeline load(Path file);
}

/** schema.py validate_timeline과 같은 규칙 + v0.2. JsonNode 단계에서 '키 없음'과 'null'을 구분. */
final class TimelineValidator {
    static void validate(JsonNode root, String fileName);   // InvalidTimelineException (한국어 메시지)
}
```
검증 규칙 (`src/predict/schema.py`, `web/src/lib/validate.ts` main #35 기준 + 추가, 결정 기록 7):
- `schema_version` 앞자리 `"0"`. `meta` 9개 키. `interval_s` == 1. `duration_s` == `frames` 개수. `frames[i].t` == `i`.
- 셀: `cell_id` `c-\d{2}\d{2}`이고 row·col과 일치, `walkable_area_m2` > 0, `image_polygon` 0~1 좌표 4개, 중복 없음.
- `frames[].cells`는 `meta.cells`와 같은 순서·전체.
- `density` 숫자 필수 (null 거부). `vx`, `vy`, `speed_var`, `pressure`, `density_pred_60s` 키 필수, 값 숫자 또는 null.
- 버전 둘째 자리: `schema.py` `_schema_minor`와 같게 `.`으로 나눈 둘째 조각이 숫자면 그 값, 없거나 숫자가 아니면 0.
- 둘째 자리 ≥ 2(v0.2 이상): `frames[].count`와 `cells[].counterflow` 키 필수, 값은 null 가능. 둘째 자리 < 2(v0.1): 두 키 생략 허용, 없으면 null로 읽는다.
- `count`는 있으면 0 이상의 숫자 또는 null. `counterflow`는 있으면 0~1 숫자 또는 null. `inflow_ratio` 0~1 또는 null.
- `t < history_s − 1`이면 `density_pred_60s` null. 모르는 키 무시.

```java
public enum PlaybackState { PLAYING, PAUSED, ENDED }
public record PlaybackSnapshot(PlaybackState state, int t, boolean loop, int durationS) {}
/** discontinuity: 첫 프레임·반복·이동 직후 → 판정 상태 초기화. wrapped: 반복으로 0으로 돌아옴. */
public record Tick(Frame frame, boolean discontinuity, boolean wrapped) {}

public final class ZonePlayer {
    public ZonePlayer(ZoneTimeline timeline, boolean loop);
    /** PLAYING이면 현재 t 프레임을 주고 t+1. 끝에서 loop면 0, 아니면 ENDED. */
    public synchronized Optional<Tick> tick();
    public synchronized PlaybackSnapshot snapshot();
    /** 마지막 tick에서 상태가 바뀌었으면(ENDED, 반복) 한 번만 준다. playback 메시지용. */
    public synchronized Optional<PlaybackSnapshot> pollStateChange();
}

/** 모든 구역을 interval-ms마다 1번씩 진행. 구역 하나가 예외를 던져도 나머지·다음 tick은 계속. */
@Component
public class ReplayScheduler implements SmartLifecycle {
    public ReplayScheduler(ZoneRegistry zones, ThreadPoolTaskScheduler replayTaskScheduler,
                           CrowdsightProperties props, ZoneBroadcaster broadcaster /* S3부터 */);
    void tickAll();             // 패키지 공개: 테스트가 직접 부름
    public void start(); public void stop(); public boolean isRunning();
}
```
- `ReplaySchedulerConfig`: `ThreadPoolTaskScheduler` poolSize S1 1, S3 2 (재생 1, ping 1), 이름 `replay-`.
- 서버 추가 검증 규칙 (`schema.py`·`validate.ts`보다 엄격, S1 계획 4.3절): `schema_version` 문자열만, `zone_id`·`camera_id`·`video_id` 비지 않은 문자열, `interval_s` == 1, `cell_size_m` > 0, `models` 객체, `duration_s`·`horizon_s`·`row`·`col`·`t`는 JSON 정수만(1.0 거부), `frames` 1개 이상.
- S1에서 `tickAll`은 `zone=... t=...` DEBUG 로그만.

fixture: `server/src/test/resources/timeline/valid_v02.json` 하나. 오류 사례는 테스트 안에서 `ObjectNode`로 고친다. `zone_id` "zone-test", `duration_s` 5, `history_s` 2, 셀 `c-0000`(4.0), `c-0001`(4.0), `c-0102`(1.5). `schema_version` "0.2"이므로 모든 프레임에 `count`, 모든 셀에 `counterflow` 키를 넣는다(값 null 가능).

테스트 상세는 `docs/plans/server_s1_timeline_replay_plan.md` 6장.

### S2. 등급 판정 (`feat/server-grade`)
```java
public enum Grade {
    NORMAL("정상"), CAUTION("주의"), ALERT("경계"), CRITICAL("심각");
    public String label();
    public Grade lower();                  // 한 단계 아래. NORMAL은 그대로
    public static Grade max(Grade a, Grade b);
}
public record DensityThresholds(double caution, double alert, double critical) {}  // caution < alert < critical
public record GradeSettings(DensityThresholds density, int upSeconds, int downSeconds,
                            double minWalkableAreaM2, double pressure, int instabilitySeconds) {}

public final class GradeRule {
    /** 밀도 → 조건 등급. 기준값 이상이면 그 등급 (3.0 → CAUTION). */
    public static Grade ofDensity(double density, DensityThresholds th);
    /** 예측 등급: 히스테리시스 없음. null이면 null. */
    public static Grade ofPrediction(Double densityPred60s, DensityThresholds th);
}

/** 셀 하나의 등급 히스테리시스. 재생 스레드 전용. */
public final class GradeHysteresis {
    public GradeHysteresis(int upSeconds, int downSeconds);
    /**
     * observed null이면 세지 않고 현재 등급 유지(연속도 끊지 않음).
     * 올림: 최근 upSeconds개 관측이 모두 현재보다 높으면 그중 가장 낮은 등급으로.
     * 내림: 최근 downSeconds개 관측이 모두 현재보다 낮으면 한 단계만 내리고 기록을 비운다.
     */
    public Grade update(Grade observed);
    public Grade current();
    public void reset();                   // NORMAL, 기록 비움
}
```
- `ArrayDeque<Grade> recent`, 최대 `max(up, down)`. `lastN(n)`은 크기 ≥ n일 때만. 올림 먼저, 안 올렸을 때만 내림. 올린 뒤 기록 비우지 않음.
```java
public record CellEvaluation(String cellId, Grade grade, Grade gradePred60s, boolean unstable,
                             boolean eligible, CellState state) {}
public record ZoneEvaluation(int t, Grade zoneGrade, Double maxDensity, List<CellEvaluation> cells,
                             Double inflowRatio, Double count, boolean inflowAlert /* S4 전까지 false */,
                             Double inflowAvg /* S4 */) {}
public final class ZoneGrader {
    public ZoneGrader(List<CellMeta> cells, GradeSettings settings);
    public ZoneEvaluation evaluate(Frame frame);
    public void reset();
}
```
- 판정 대상(`eligible`) = `walkable_area_m2 >= 2.0` (결정 4). 구역 등급 = 대상 셀 히스테리시스 등급 최댓값, 없으면 NORMAL. `maxDensity` = 대상 셀 최대 밀도, 없으면 null.
- 작은 셀도 자기 등급은 계산해 `cells[]`로 보낸다.
- `ZoneRuntime`이 Player와 Grader를 묶고 discontinuity면 `grader.reset()`.

기준 3/4/5, 올림 2초, 내림 10초, 최소 면적 2.0:

| 테스트 | 밀도 (t0부터) | 기대 |
|---|---|---|
| `GradeRuleTest` | 0, 2.99, 3.0, 3.99, 4.0, 4.99, 5.0 | N, N, C, C, A, A, CR |
| `upAfterTwoSeconds` | 4.2, 4.5 | N, A |
| `spikeIgnored` | 4.5, 2.0, 4.5, 2.0 | N, N, N, N |
| `upToLowerOfStreak` | 4.1, 3.9, 4.1, 4.1 | N, C, C, A |
| `jumpDirectly` | 5.5, 5.5 | N, CR |
| `downOneStepPer10s` | 4.5, 4.5, 2.0 × 20 | t1 A, t10 A, t11 C, t20 C, t21 N |
| `downInterrupted` | 4.5, 4.5, 2.0 × 9, 4.0 (t11), 2.0 × 10 | t20 A, t21 C |
| `criticalStepsDownOnly1` | 5.5, 5.5, 3.5 × 30 | t11 A, t21 C, t31 C |
| `nullSkipped` | 4.5, null, 4.5 | N, N, A |
| `resetClears` | 4.5, 4.5, reset, 4.5 | 마지막 N |
| `ZoneGraderTest.smallCellExcluded` | [c-0000, c-0001, c-0102(1.5)] t0 [3.2, 1.0, 6.0], t1 [3.4, 1.0, 6.0] | t1 셀 [C, N, CR], 구역 C, max 3.4 |
| `areaBoundaryIncluded` | 면적 2.0, 4.5 × 2 | 구역 A |
| `predictionNoHysteresis` | t0 pred 4.6 | `grade_pred_60s` A |
| `predictionNull` | pred null | null |
| `noEligibleCells` | 모두 1.5㎡ | 구역 N, max null |
| `orderPreserved` | 셀 3 | meta 순서 |
| `ZoneRuntimeTest.resetOnWrap` | duration 3, 매 초 4.5, loop | t1 A, t2 A, (반복) t0 N, t1 A |

### S3. WebSocket `hello`, `zone_state` (`feat/server-ws-zone-state`)
```java
@Configuration @EnableWebSocket
public class WebSocketConfig implements WebSocketConfigurer {
    public void registerWebSocketHandlers(WebSocketHandlerRegistry registry) {
        registry.addHandler(zoneHandler, "/ws/zones/*")
                .setAllowedOriginPatterns(props.corsOriginPatterns().toArray(String[]::new));
    }
}

/** /ws/zones/{zone_id}. 접속하면 hello를 보낸 뒤 방송 대상에 넣는다. 화면 → 서버 메시지는 무시. */
@Component
public class ZoneWebSocketHandler extends TextWebSocketHandler {
    private static final UriTemplate PATH = new UriTemplate("/ws/zones/{zoneId}");
    public void afterConnectionEstablished(WebSocketSession session);   // 없는 구역: close(new CloseStatus(4404, "unknown zone"))
    public void afterConnectionClosed(WebSocketSession session, CloseStatus status);
    public void handleTransportError(WebSocketSession session, Throwable ex);
}

/** 구역별 접속자. 세션은 ConcurrentWebSocketSessionDecorator로 감싼다. */
@Component
public class ZoneSessions implements ZoneBroadcaster {
    public void join(String zoneId, WebSocketSession raw, String helloJson);   // 감싸기 → hello → 집합 추가
    public void leave(WebSocketSession raw);
    public void broadcast(String zoneId, String json);    // 실패 세션은 닫고 뺀다
    public void pingAll();
    public int sessionCount();
}
```
- hello를 먼저 보내고 집합에 넣는다 (zone_state가 hello보다 먼저 가지 않게).
- 느린 화면(결정 1): 세션 생성 때 `BLOCKING_SEND_TIMEOUT` 2000L. 데코레이터는 스레드 안전용으로만 감싼다.
- `zone_id`는 `UriTemplate.match(session.getUri().getPath())`.
```java
public record HelloMessage(String type, String schemaVersion, String zoneId, JsonNode meta,
                           PlaybackView playback, ThresholdsView thresholds, List<AlertMessage> unackedAlerts) {}
public record PlaybackView(String state, int t, boolean loop, int durationS) {}   // "playing"|"paused"|"ended"
public record ThresholdsView(DensityThresholds density, double pressure, double inflowRatio) {}
public record ZoneStateMessage(String type, String zoneId, int t, String frameTs, ZoneView zone, List<CellView> cells) {}
public record ZoneView(Grade grade, Double maxDensity, Double inflowRatio, boolean inflowAlert, Double count) {}
public record CellView(String cellId, Grade grade, Double density, Double vx, Double vy, Double speedVar,
                       Double pressure, Double counterflow,
                       @JsonProperty("density_pred_60s") Double densityPred60s,
                       @JsonProperty("grade_pred_60s") Grade gradePred60s) {}
public record PlaybackMessage(String type, String zoneId, String state, int t, boolean loop) {}

/** frame_ts: 밀리초 3자리 + 오프셋 (+09:00). */
public final class FrameTimestamps {
    static final DateTimeFormatter FMT = DateTimeFormatter.ofPattern("yyyy-MM-dd'T'HH:mm:ss.SSSXXX");
    public static String now(Clock clock) { return FMT.format(ZonedDateTime.now(clock)); }
}
```
- `ClockConfig`: `Clock.system(ZoneId.of(props.timeZone()))`. `Instant.now()` 직접 호출 금지.
- 반복으로 0 또는 끝: `playback` 먼저, 그다음 `zone_state`.
- S3의 `inflow_alert`는 항상 false (S4에서 실제 값).

| 테스트 | 입력 | 기대 |
|---|---|---|
| `FrameTimestampsTest` | `Clock.fixed(2026-11-18T05:02:31.512Z, Asia/Seoul)` | `"2026-11-18T14:02:31.512+09:00"` |
| 같은 | `05:02:31Z` | `"...14:02:31.000+09:00"` |
| `MessageJsonTest.cellKeys` | vx null | 키 {cell_id, grade, density, vx, vy, speed_var, pressure, counterflow, density_pred_60s, grade_pred_60s}, `"vx":null` 포함 |
| `MessageJsonTest.zoneKeys` | ZoneView | {grade, max_density, inflow_ratio, inflow_alert, count}, grade `"ALERT"` |
| `MessageJsonTest.helloMetaPassthrough` | `meta.foo`=1 | `hello.meta.foo`==1, `thresholds.density.alert`==4.0 |
| `ZoneSessionsTest.dropsFailingSession` | 세션 2, 1개 IOException | 실패 세션 닫고 빠짐, 다른 세션 받음, count 1 |
| `ZoneRuntimeTest.wrapEmitsPlayback` | duration 5, loop | t=4 뒤 [playback(playing, 0), zone_state(0)] |
| `ZoneWebSocketIntegrationTest` (RANDOM_PORT, `interval-ms=100`, `timeline-dir=src/test/resources/timeline`) | `ws://localhost:{port}/ws/zones/zone-test` | 첫 메시지 hello, `meta.cells` 3, 이어서 zone_state t, t+1 mod 5 |
| 같은 | `/ws/zones/nope` | 2초 안 닫힘, 4404 |
| 같은 | 클라이언트 2 | 같은 tick 같은 t |

### S4. 불안정, 유입 경보 (`feat/server-instability-inflow`)
```java
/** pressure가 기준을 seconds초 연속 넘으면 active. null이나 기준 이하면 연속 0. */
public final class InstabilityTracker {
    public InstabilityTracker(double pressureThreshold, int seconds);
    public boolean update(Double pressure);
    public void reset();
}
/**
 * 유입 경보 (결정 6, 결정 기록 8). 재생 스레드 전용.
 * 평균: 생성·reset 뒤 관측이 windowSeconds개 쌓이기 전에는 null (창이 다 찬 뒤에만 계산).
 *       그 뒤 최근 windowSeconds초(이번 초 포함) 값 중 null이 아닌 것이 minSamples개 이상이면 그 평균, 아니면 null.
 * 조건: 평균 != null && 평균 > ratio && count != null && count >= minCount.
 * 켬: 조건이 참인 초. 끔: 켜진 뒤 조건이 offSeconds초 연속 거짓 (평균 null·count 부족·count null인 초도 거짓으로 센다).
 */
public final class InflowMonitor {
    public InflowMonitor(double ratio, int windowSeconds, int minSamples, int offSeconds, double minCount);
    public InflowStatus update(Double inflowRatio, Double count);
    public void reset();                   // 창·연속·on 모두 비움 (반복·이동)
}
public record InflowStatus(Double average, boolean on) {}
```
- 셀 관측 등급 = `max(ofDensity(density), unstable ? CRITICAL : NORMAL)`.
- 5초 평균(결정 기록 8): 최근 5초 중 non-null 값이 3개(`min-samples`) 이상이면 그 평균, 아니면 null(조건 거짓). 창은 최근 5초 그대로이고 null도 한 칸을 차지한다.
- 창이 다 찬 뒤에만 평균을 낸다(결정 기록 8): 시작·초기화(반복·이동) 뒤 t0~t3은 평균 null, 첫 평균은 t4. `inflow_ratio` null인 초도 관측 1초로 센다.
- 끄는 연속에는 평균 null·`count < 3`·`count` null인 초도 포함 (가정). `counterflow`는 판정에 안 씀 `[토론]` (흐름 모듈이 쓰지 않아 실제 파일은 늘 null).
- `pressure` null(셀 머리 부족, 흐름 창이 덜 찬 첫 구간)은 불안정 연속을 끊는다. 규칙은 유지하고 실제 데이터의 끊김 빈도를 E5 때 확인한다 `[토론]`.
- `CrowdsightProperties`: `1 ≤ min-samples ≤ window-seconds` 검사.

| 테스트 | 입력 | 기대 |
|---|---|---|
| `InstabilityTrackerTest` | 0.03 × 3 | [F, F, T] |
| 같은 | 0.03, 0.03, null, 0.03, 0.03, 0.03 | t5만 T |
| 같은 | 0.03, 0.02, 0.03, 0.03, 0.03 | t4 처음 T |
| `ZoneGraderTest.instabilityToCritical` | 밀도 1.0, pressure 0.03, t0~t3 | [N, N, N, CR] |
| `InflowMonitorTest.onAt5sAverage` | 0.4 × 3, 0.8 × 3, count 5 | t0~t3 평균 null, t4 0.56 꺼짐, t5 0.64 켜짐 |
| `nullUntilWindowFull` | 0.7 × 5, count 5 | t0~t3 평균 null 꺼짐 (non-null 3개 이상이어도), t4 평균 0.7 켜짐 |
| `nullInWindow` | 0.7, null, 0.8, 0.7, 0.9, count 5 | t0~t3 평균 null 꺼짐, t4 0.775 켜짐 |
| `tooFewSamplesStaysOff` | 0.9, null, null, null, 0.9, null × 5, count 5 | 매 초 평균 null(창 안 값 ≤ 2개), 꺼짐 |
| `blockedBelowMinCount` | 0.7 × 5, count 2.9 | t4 평균 0.7, 꺼짐 |
| `nullCountBlocks` | 0.7 × 5, count null | t4 평균 0.7, 꺼짐 |
| `offAfter10s` | 0.8 × 5, 이후 0.1, count 5 | t4 켜짐, t5 평균 0.66 참, t6 0.52부터 거짓, t14 켜짐, t15 꺼짐 |
| `nullAverageCountsTowardOff` | 0.8 × 5, 이후 null, count 5 | t4 켜짐, t5·t6 평균 0.8 참(값 4·3개), t7부터 평균 null(거짓), t15 켜짐, t16 꺼짐 |
| `resetClears` | 0.7 × 5(t4 켜짐), reset, 0.7 × 5 | reset 뒤 처음 4초 평균 null·꺼짐, 5번째 초 평균 0.7 켜짐 |

### S5. 알림 (`feat/server-alert`)
```java
public enum AlertReason { GRADE_UP, INFLOW, INSTABILITY }
public record Alert(String alertId, String zoneId, int t, String frameTs, Grade level, AlertReason reason,
                    String message, double value, List<String> cellIds) {}
public final class AlertDetector {
    public AlertDetector(String zoneId, AlertIdGenerator ids, Clock clock);
    public List<Alert> detect(ZoneEvaluation eval);
    public void reset();
}
/** a-yyyyMMdd-NNNN (서버 시작부터 1씩, 날짜는 Clock 기준). */
public final class AlertIdGenerator { public String next(); }
/** 구역별 미확인 알림, 구역당 최대 100 (넘으면 오래된 것부터). */
@Component public class AlertStore { add, unacked(zoneId), find(alertId), ack(alertId, Instant) /* S6 */ }
```
- **GRADE_UP**: 구역 등급 ≥ ALERT이고 이번 사건의 최고 단계보다 높을 때. ALERT 아래로 내려가면 해제. `value` = max_density, `cell_ids` = 대상 셀 중 등급 ≥ level (meta 순서), message `"구역 등급이 주의 → 경계로 올랐다"`.
- **INFLOW**: on이 F → T. level CAUTION, value 5초 평균.
- **INSTABILITY**: 대상 셀 중 하나라도 unstable F → T (구역 단위). level CRITICAL, value 불안정 셀 최대 pressure. 남아 있으면 재전송 없음.
- 한 tick 안 순서 `zone_state` → `alert`. `hello.unacked_alerts` = `AlertStore.unacked(zoneId)`.

| 테스트 | 입력 | 기대 |
|---|---|---|
| `gradeUpRules` | 구역 등급 N, C, A, CR, A, CR, C, A | t2 ALERT, t3 CRITICAL, t7 ALERT |
| `gradeUpPayload` | t2 셀 [A(4.3), C(3.5), CR(6.0, 1.5㎡)] | value 4.3, cell_ids ["c-0000"] |
| `inflowEdge` | on [F,F,F,F,T,T] | t4만 INFLOW, value 0.66 |
| `instabilityEdge` | c-0000 [F,F,T,T], c-0001 [F,F,F,T] | t2만 |
| `idFormat` | Clock 2026-11-18 | "a-20261118-0001", "-0002" |
| `storeCap` | 101개 | 100개, 첫 알림 빠짐 |
| `ZoneRuntimeTest.alertAfterState` | 등급 오르는 tick | [zone_state, alert] |
| `ZoneRuntimeTest.alertRepeatsNextLoop` | duration 5, loop, 4.5 | 반복마다 t1에 GRADE_UP 1개 |
| `ZoneRuntimeTest.thirtyMinuteLoop` | duration 10, tick 1800 | 예외 없음, 마지막 t 9, store ≤ 100 |

### S6. 알림 확인 (`feat/server-alert-ack`)
- `POST /api/alerts/{alertId}/ack` → 200 `{"alert_id","acked_at"}`, 없으면 404. `GET /api/zones/{zoneId}/alerts?unacked=true`.
- `AlertLogWriter`: `crowdsight.alert-log`에 JSON 한 줄, `synchronized`, `Files.writeString(..., CREATE, APPEND)`, 부모 폴더 생성.
- CORS: `WebMvcConfigurer.addCorsMappings("/api/**")`.

| 테스트 (MockMvc + `@TempDir`) | 기대 |
|---|---|
| 첫 확인 | 200, acked_at = 고정 Clock, 로그 1줄 {alert_id, zone_id, t, level, reason, sent_at, acked_at} |
| 두 번째 | 200, 처음 acked_at, 로그 1줄 |
| 없는 ID | 404 |
| 확인 뒤 `?unacked=true` | 빠짐 |

### S7. 재생 제어와 조회 (`feat/server-playback-api`)
- `ZonePlayer`: `play()`, `pause()`, `seek(int t)`, `setLoop(boolean)` (`synchronized`). seek는 `pendingDiscontinuity`. 상태 바뀌면 `playback`.
- `GET /api/zones` → `[{zone_id, video_id, duration_s}]`, `GET /api/zones/{id}/meta`, `POST /api/zones/{id}/playback` (seek 범위 밖 400).
- `GET /api/health` → `{status, zones:[{zone_id, state, t}], sessions, last_tick_ms, max_tick_ms}`.
- 테스트: pause → tick 빈 값 + playback(paused) 1번 / seek 90 → 다음 t 90, 구역 N / seek −1·180(duration 180) → 400 / loop false → 끝에서 ENDED.

## 3. Java 규칙 제안 `[결정 필요]`
| 항목 | 제안 |
|---|---|
| 들여쓰기 | 공백 4칸, 줄 120자. `.editorconfig`만 (Spotless 안 씀) |
| 이름 | 클래스 `PascalCase`, 메서드·필드 `camelCase`, 상수 `UPPER_SNAKE`, 패키지 소문자 한 단어 |
| JSON | 키 `snake_case`, 전역 `spring.jackson.property-naming-strategy: SNAKE_CASE`. `density_pred_60s`·`grade_pred_60s`만 `@JsonProperty`. 메시지마다 키 집합 테스트 |
| DTO | `record`. 상태 있는 클래스는 `final` + 스레드 규칙 Javadoc |
| null | 없을 수 있는 숫자는 `Double`. 필드·레코드에 `Optional` 금지, 반환형만 |
| 주석 | 공개 클래스·메서드 한국어 Javadoc, 식별자 영어 |
| 주입 | 생성자 주입만. Lombok `@RequiredArgsConstructor`·`@Slf4j` 사용 (결정 3) |
| 설정 | 기준값·시간·경로는 `CrowdsightProperties`에만 |
| 시간 | `Clock` 주입. `Instant.now()`·`currentTimeMillis()` 금지, 경과 시간만 `nanoTime()` |
| 예외 | unchecked + 한국어 메시지. 재생 루프는 잡아서 로그 후 계속 |
| 로그 | SLF4J, 한국어 메시지, `zone=`, `t=` 키 |
| 테스트 | JUnit Jupiter 6 + AssertJ, `XxxTest`, 영어 camelCase + `@DisplayName("한국어")`, 통합은 `XxxIntegrationTest`, fixture `src/test/resources/timeline/` |
| Jackson 3 | `tools.jackson.databind.*`, 어노테이션 `com.fasterxml.jackson.annotation.*` |

## 4. 설정 (`application.yml`, properties 삭제)
```yaml
spring:
  application:
    name: crowdsight-server
  jackson:
    property-naming-strategy: SNAKE_CASE
server:
  port: 8080

crowdsight:
  timeline-dir: ../data/processed/timeline   # bootRun 작업 폴더가 server/. 환경변수 CROWDSIGHT_TIMELINEDIR로 바꿈
  timeline-files: [E04_039.json]
  time-zone: Asia/Seoul                      # (S3)
  replay:
    interval-ms: 1000
    loop: true
  grade:
    density: { caution: 3.0, alert: 4.0, critical: 5.0 }
    up-seconds: 2
    down-seconds: 10
    min-walkable-area-m2: 2.0                # 결정 4
  instability:
    pressure: 0.02                           # 가정, E5 결과로 조정
    seconds: 3
  inflow:
    ratio: 0.6
    window-seconds: 5
    min-samples: 3                           # 결정 기록 8, 5초 중 non-null 개수 하한 (가정)
    off-seconds: 10
    min-count: 3                             # 결정 6
  ws:
    ping-interval-ms: 30000
    send-time-limit-ms: 2000
    buffer-size-limit-bytes: 524288
  alert-log: logs/alerts.jsonl               # server/logs/, git 제외
  cors-origin-patterns: ["http://localhost:*", "http://127.0.0.1:*"]
```
- `CrowdsightProperties`: `@ConfigurationProperties("crowdsight")` 중첩 record, compact constructor 검사 (`caution < alert < critical`, 초 ≥ 1, `interval-ms` > 0, `1 ≤ inflow.min-samples ≤ inflow.window-seconds`). validation 스타터 안 씀. `timeline-dir`은 `String`(PathEditor 회피).
- 시작 시 타임라인 폴더 절대 경로 INFO. 파일 없으면 경로 넣어 시작 실패.
- 테스트는 `@SpringBootTest(properties = ...)`. `src/test/resources/application.yml`은 만들지 않음.

## 5. 동시성·시간
| 주제 | 설계 |
|---|---|
| 재생 시계 | `scheduleAtFixedRate(Duration.ofMillis(interval))`. 주기 작업은 자기와 겹치지 않아 판정 상태는 스레드 1개 |
| 테스트 시간 | `tickAll()`·`ZoneRuntime.tick()` 직접 호출, `Clock.fixed`. 실제 스케줄러는 20 ms 테스트 1개 |
| 예외 | Spring `ThreadPoolTaskScheduler`는 반복 작업 예외를 로그 후 계속한다(jar 확인). 구역마다 try/catch는 같은 tick의 다른 구역을 지키기 위해서다 |
| 세션 | `ConcurrentHashMap<String, Set<WebSocketSession>>` + 데코레이터. JSON은 tick당 한 번 |
| 느린 화면 | Tomcat 전송 제한 2초를 넘으면 그 세션만 닫고, 재접속 시 hello로 복구 (결정 1). 최악은 그 tick +2초 |
| ping | 두 번째 스레드, 30초 |
| 30분 반복 | 반복마다 판정·알림 초기화 + playback. 커지는 곳은 AlertStore(100 상한)뿐. 1800 tick 테스트 |
| p95 ≤ 5초 | `frame_ts`와 화면 수신 시각 차이 (api-spec 7절). tick 처리 시간 last·max를 `/api/health`에, 500 ms 넘으면 WARN |

## 6. null 처리
| 필드 | 서버 처리 |
|---|---|
| `density` | null이면 파일 거부. 히스테리시스는 null 관측 건너뛰기(방어용) `[토론]` |
| `pressure` | null이면 불안정 연속 0. 흐름 출력은 셀 머리 수가 적으면 null이라 연속이 끊길 수 있다. 빈도는 E5 때 확인 `[토론]` |
| `density_pred_60s` | null이면 `grade_pred_60s` null |
| `vx`, `vy`, `speed_var`, `counterflow` | 판정 안 씀, null 그대로 전달 (`counterflow`는 흐름 모듈이 쓰지 않아 실제 파일에서 늘 null) |
| `inflow_ratio` | 시작·초기화 뒤 5초 관측이 쌓이기 전(t0~t3)에는 평균 null. 그 뒤 최근 5초 중 non-null이 3개(`min-samples`) 이상이면 그 평균, 아니면 평균 null·조건 거짓 (결정 기록 8). 평균 null인 초도 끄는 연속에 센다. 원래 값은 그대로 전달 |
| `count` | null이면 유입 경보 안 켬. 키 없음은 v0.1 파일만 허용하고 null로 읽는다 (결정 기록 7). null 그대로 전달 |
| `max_density` | 대상 셀 없으면 null |
- null은 출력한다 (`default-property-inclusion` 설정 안 함). 화면 `validateFrame`은 키 없으면 실패 → S3에 `"vx":null` 테스트.

## 7. `docs/api-spec.md` 고칠 곳 (D1)
1. 기준 문서를 timeline-spec v0.2, decisions-2026-11-11, `proposal.md` v3.1로.
2. 3.2 `zone_state`: `zone.count` 추가, `cells[]`에 `counterflow`, `zone.inflow_ratio`는 원래 값이고 경보는 5초 평균. v0.2 파일은 두 키 필수(결정 기록 7).
3. 3.3 `alert`: GRADE_UP 재전송 규칙, `t`·`frame_ts`는 같은 tick의 `zone_state`와 같음.
4. 3.4 `playback`: 반복으로 0이면 `{state:"playing", t:0}`, 화면은 프레임을 비움.
5. 4.2: 판정 대상 `walkable_area_m2 ≥ 2.0`(결정 4), 올림 규칙 명확화, density null 문장 교체.
6. 4.3: pressure null → 연속 0, counterflow 판정 미사용 `[토론]`.
7. 4.4: `count` < 3이면 안 켬(결정 6), 5초 중 non-null 3개 이상이면 평균(결정 기록 8), 끄는 조건 10초 연속 거짓(평균 null 초 포함).
8. 7절에 E8 기준(결정 9).
9. 8절 설정을 4장 yml로.
10. 10절 미결 안건 닫기 (1번 결정 4, 3번 결정 6, 6번 timeline-spec 9절 1번, 유입 평균 null 처리 결정 기록 8), 화면 `[토론]` 추가.
11. `hello.schema_version`은 API 메시지 버전 (타임라인 파일 버전과 별개).

## 8. 화면(web)·mock과 어긋나는 곳 `[토론]` (나예린)
| # | 지금 web / mock | api-spec | 권장 |
|---|---|---|---|
| 1 | mock `{type:"timeline"}`, `{type:"frame"}` | `hello`, `zone_state`, `alert`, `playback` | web `liveFeed.ts` |
| 2 | 모르는 type throw | 무시 | web: null 반환 |
| 3 | 프레임 = 타임라인 프레임 그대로 | `zone_state.zone.{...}` + `cells[].grade·grade_pred_60s` | web 어댑터. 서버는 셀 전부·null 키 유지 |
| 4 | `ws://localhost:8787` | `ws://localhost:8080/ws/zones/{zone_id}` | web `.env.local` `VITE_WS_URL` |
| 5 | 반복 시 mock이 `timeline` 재전송 | 미정 | 명세(D1 4번) + web. 화면이 영상 시각으로 프레임을 고르므로(#34) 옛 `t`가 섞이면 영상과 히트맵이 어긋난다 |
| 6 | ~~`types/timeline.ts`·`validate.ts`가 v0.1~~ | v0.2 | **해결 (#35)**. 실시간 프레임은 `requireV02=false`로 검사, `count` 유지, 빠진 `counterflow`는 null로 채움 |
| 7 | 화면이 `DENSITY_LEVELS`로 즉시 판정, "경고" | 서버 `grade`, "경계" | web: 서버 grade 사용 |
| 8 | `alerts.ts`가 raise·clear·forecast 직접 생성 | 서버 `alert` + REST | web. forecast 유지 여부 `[토론]` |
| 9 | 재접속 1 s → ×2, 최대 15 s | 1, 2, 5, 이후 5 s | web 최대 5 s 권장 |
| 10 | `frame_ts` 지연 미기록 | 화면이 기록 (E8) | web |
| 11 | `thresholds`, `playback`, `unacked_alerts` 없음 | 있음 | web. `playback` 일시정지·이동을 영상에도 반영 (api-spec 6절, 영상 오버레이 #34) |
| 12 | mock 옛 형식 | | mock 갱신 또는 11-13부터 실제 서버. 담당 `[토론]` |
| 13 | 화면 5173, 서버 8080 | | 서버 WS·REST CORS에 5173 |
- S3 병합 때 `hello`·`zone_state` 실제 출력 예시를 PR 설명에 붙여 나예린 님께 전달.

## 9. 위험·가정·안건
### 위험
| 위험 | 대응 |
|---|---|
| Boot 4·Jackson 3 예제 부족 | jar로 확인한 API만, import 규칙 |
| 구역 하나의 예외가 같은 tick의 다른 구역을 막음 | 구역별 try/catch + `survivesZoneException` |
| 상대 경로가 실행 위치마다 다름 | 절대 경로 로그, 없으면 시작 실패, 환경변수 |
| 화면이 11-13까지 새 형식 못 받음 | S3를 11-12에, 출력 예시 전달 |
| 실제 E04_039 타임라인 늦음 | `fake_timeline.py` 파일 지정 |
| 가짜 유입 비율 최대 0.6 | fixture로 시험 |
| 불안정이 INSTABILITY(t2)와 GRADE_UP/CRITICAL(t3) 둘 다 만듦 | 명세대로 둘 다, 줄일지 `[토론]` |
| E8에 히스테리시스 지연 포함 여부 | 밀도 +1초, 불안정 +3초, 넣어도 5초 이내. 측정 기준 이유노와 |
| 작업 폴더에 flow 수정분 | S0은 `server/`·`.gitignore`만 stage |
| `Executor` 빈 → `applicationTaskExecutor` 생략 | `ThreadPoolTaskScheduler` 빈이 `Executor`라 Boot가 만들지 않는다. 지금은 `@Async`·MVC 비동기가 없어 영향 없음. 쓰게 되면 `spring.task.execution.mode: force` 또는 전용 실행기 |

### 가정
- 서버 시작 시 모든 구역 t=0부터 재생. 재생 상태는 구역당 하나.
- 셀 히스테리시스 시작 등급 NORMAL, null 관측 건너뜀.
- 유입 끄는 연속에 평균 null·`count` < 3·`count` null 초 포함.
- 미확인 알림은 메모리에만 (재시작 시 사라짐, 명세 4.5).
- 반복 재생마다 판정 초기화 → 같은 알림 반복 (시연용).

### `[결정 필요]` (조영준)
모두 정함 → 맨 위 "결정 기록".

### `[토론]`
| # | 안건 | 누구와 |
|---|---|---|
| 1 | density null 셀 허용 여부 | 이유노 |
| 2 | 불안정 판정에 counterflow | 이유노 |
| 3 | 불안정 알림과 심각 등급 알림 둘 다 | 이유노, 나예린 |
| 4 | E8에 히스테리시스 지연, 30분 실행 시점 | 이유노 |
| 5 | 8장 web 변경과 11-13 연결 범위 | 나예린 |
| 6 | mock 서버 갱신 담당 | 나예린 |
| 7 | 반복 신호 `playback` t=0 | 나예린 |
| 8 | forecast 알림 유지 | 나예린 |
| 9 | 재접속 최대 간격 5 s / 15 s | 나예린 |
| 10 | 유입 5초 평균의 null 처리 | **닫힘 (결정 기록 8)**: 창이 다 찬 뒤 non-null 3개 이상이면 평균 |
| 11 | `pressure` null이 불안정 3초 연속을 끊는 빈도 | 조영준, E5 때 |
