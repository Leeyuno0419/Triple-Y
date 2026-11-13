# 서버 S3 WebSocket `hello`·`zone_state`·`playback` 구현 계획 (`feat/server-ws-zone-state`)

| 항목 | 내용 |
|---|---|
| 작성일 | 2026-11-12 |
| 기준 | `docs/plans/server_impl_plan.md`(결정 기록 1·2, 1장, 2장 S3, 4장 `time-zone`·`ws.*`·`cors-origin-patterns`, 5장 동시성, 6장 null, 8장 화면), `docs/plans/server_s2_grade_plan.md`(7장), `origin/feat/api-spec-v02:docs/api-spec.md`(1, 2, 3.1, 3.2, 3.4, 3.5, 6절), `docs/research/server_research.md`(2.1, 2.4, 4절), `docs/research/server_recheck_2026-11-11.md`(3절), `origin/main:web/src/lib/{liveFeed,validate,useLiveFeed}.ts`, `web/src/types/timeline.ts`, `web/scripts/mock-ws-server.mjs` |
| 대상 | `server/` (`main` `73bf33f`에서 분기. S1·S2는 #45로 `main`에 병합됨), `docs/plans/` |
| 범위 | `crowdsight.time-zone`·`ws.*`·`cors-origin-patterns` 설정, `ClockConfig`, `WebSocketConfig`, `/ws/zones/{zone_id}` 핸들러(없는 구역 4404, 받은 메시지 무시), `ZoneSessions`(hello 뒤 추가, 한 번 직렬화한 JSON 방송, 실패 세션 닫고 빼기, ping), 메시지 record, `MessageFactory`, `FrameTimestamps`, `ZoneRegistry.find`, 재생 tick마다 [playback?] → `zone_state`. **불안정·유입(S4), 알림(S5), ack·로그(S6), 재생 제어 REST(S7) 없음** |
| 상태 | 계획. 사용자 승인(2026-11-13) |

## 0. 확인한 사실 (코드·jar로 확인)
- 작업 트리:
  - 작성 당시 브랜치 `feat/server-grade`(`00acb31`). 이후 #45로 S1·S2가 `main`에 병합됐고, 구현은 `main` `73bf33f`에서 분기한다.
  - untracked 파일은 `CLAUDE.local.md`, 이 계획 문서다. `CLAUDE.local.md`는 stage하지 않는다.
  - 로컬 `main`은 `origin/main`(`73bf33f`)과 같다. web 파일은 `main` 기준으로 봤다.
- S2 코드 상태:
  - `ReplayScheduler.tickAll()`은 구역마다 다음 순서로 돈다: `zone.tick()` → `pollStateChange()`(INFO 로그) → DEBUG 로그. 그 뒤에 `// S3: [playback?] → zone_state 방송` 주석 자리가 있다.
  - `ZonePlayer.tick()` 반복 시: `currentT=0`으로 둔 뒤 `pendingChange = (PLAYING, 0, loop, duration)`.
  - `ZonePlayer.tick()` 끝(loop false) 시: `pendingChange = (ENDED, 마지막 t, …)`를 남기고 빈 값을 준다.
  - `ZonePlayer.snapshot().t`는 마지막으로 준 프레임이다. 시작 전에는 0이다.
  - `ZoneTimeline.metaJson()`은 원본 meta 트리다(모르는 키 포함).
  - `CellEvaluation.state()`는 타임라인 `CellState` 그대로다.
  - `ZoneEvaluation`은 `(t, zoneGrade, maxDensity, cells)`다. `inflow_ratio`·`count`는 `ZoneStep.tick().frame()`에 있다.
  - `CrowdsightProperties`는 `TestProperties.of`·`replay`에서만 만든다.
  - `ReplaySchedulerConfig` poolSize는 1이다. Javadoc에 "S3에서 2"라고 적혀 있다.
- Tomcat 11.0.27 (`tomcat-embed-websocket-11.0.27.jar`, javap):
  - `Constants.BLOCKING_SEND_TIMEOUT_PROPERTY = "org.apache.tomcat.websocket.BLOCKING_SEND_TIMEOUT"`, `DEFAULT_BLOCKING_SEND_TIMEOUT = 20000L`.
  - `WsRemoteEndpointImplBase.getBlockingSendTimeout()`은 `wsSession.getUserProperties().get(키)`를 보낼 때마다 읽는다. 값이 `instanceof Long`일 때만 쓰고, 아니면(예: `Integer`) 20000이다. **값은 반드시 `Long`이어야 한다.**
  - 텍스트(`sendMessageBlock(CharBuffer, …)`)와 ping·바이너리(`sendMessageBlock(byte, ByteBuffer, …)`) 모두 이 값을 쓴다.
  - 제한 시간이 넘거나 쓰기가 실패하면 Tomcat이 먼저 `WsSession.doClose(GOING_AWAY / CLOSED_ABNORMALLY)`로 세션을 닫는다. 그다음 `SocketTimeoutException` 또는 `IOException`을 던진다.
  - jar 안에 `jakarta/websocket/Session.class`가 있다. 의존 경로는 `spring-boot-starter-tomcat-runtime`의 `apiElements`다(Gradle module 확인). 그래서 main 코드에서 컴파일된다.
- Spring Framework 7.0.10 (`spring-websocket-7.0.10.jar`, javap):
  - `StandardWebSocketHandlerAdapter.onOpen`은 `initializeNativeSession`을 먼저 부르고 그다음 `afterConnectionEstablished`를 부른다. 그래서 핸들러 안에서 네이티브 세션을 쓸 수 있다.
  - `AbstractWebSocketSession implements NativeWebSocketSession`. `getNativeSession(Class<T>)`는 `isInstance`가 거짓이면 null이다.
  - 생성자: `ConcurrentWebSocketSessionDecorator(WebSocketSession, int sendTimeLimit, int bufferSizeLimit[, OverflowStrategy])`. `getTimeSinceSendStarted()`가 있고, 기본 전략은 TERMINATE다.
  - `WebSocketSessionDecorator.unwrap(WebSocketSession)`은 static이다.
  - 데코레이터는 잠금을 못 얻은 스레드만 한도를 검사한다. 넘으면 `SessionLimitExceededException`(unchecked)을 던지고 세션은 닫지 않는다(조사 2.1).
  - `CloseStatus(int, String)`, `CloseStatus.SESSION_NOT_RELIABLE`(4500).
  - `WebSocketHandlerRegistration.setAllowedOriginPatterns(String...)`.
  - `WebSocketConfigurationSupport`는 SockJS 스케줄러를 `DefaultSockJsSchedulerContainer`로 감싼다. `ThreadPoolTaskScheduler` 빈이 하나 더 생기지 않으므로 `replayTaskScheduler` 주입이 모호해지지 않는다.
  - `WebSocketClient.execute(handler, String uriTemplate, Object...)`, `execute(handler, WebSocketHttpHeaders, URI)` → `CompletableFuture<WebSocketSession>`.
  - `HttpHeaders.setOrigin(String)`, `WebSocketHttpHeaders extends HttpHeaders`.
  - `UriTemplate.matches/match`.
- Spring Boot 4.1.2 테스트: `org.springframework.boot.test.web.server.LocalServerPort`(spring-boot-test-4.1.2.jar).
- Jackson 3.1.7 `JsonNode`:
  - `propertyNames()`(Collection), `asString()`, `asInt()`, `asDouble()`, `asBoolean()`, `isNull()`, `has()`, `values()`.
  - `writeValueAsString`은 unchecked `JacksonException`을 던진다.
- 조사(2.3절, 실측):
  - record는 선언 순서대로 직렬화된다.
  - enum은 이름으로 나간다.
  - `densityPred60s`는 `@JsonProperty` 없이는 `density_pred60s`가 된다.
  - `Double`은 `Double.toString` 형식이다(0 → `0.0`).
- api-spec v0.2:
  - `hello.schema_version`은 API 메시지 버전이고 예시 값은 `"0.2"`다.
  - 없는 구역은 `4404 unknown zone`.
  - 반복 시 `playback{playing, t:0}` → `zone_state t:0` 순서.
  - ping 30초, 차단 전송 제한 2초, 버퍼 512KB.
  - 허용 출처는 `http://localhost:*`, `http://127.0.0.1:*`.
- web(`origin/main`):
  - `liveFeed.ts`는 `timeline`·`frames`·`frame`만 안다. 모르는 type은 throw한다.
  - `useLiveFeed.ts`는 닫기 코드를 보지 않고, 재접속 간격이 최대 15초다.
  - `validateFrame(fr, meta, requireV02=false)`는 셀의 남는 키(`grade`)를 막지 않는다. `vx`·`vy`·`speed_var`·`pressure`·`density_pred_60s` 키가 없으면 실패한다.
  - mock은 포트 8787, `zone-mock-ws`, v0.1 형식이다.
  - 가짜 E04_039의 `zone_id`는 `zone-e04-039`다(`fake_timeline.py`가 `video_id.lower().replace("_","-")`로 만든다).
- fixture `valid_v02.json`을 서버가 끊김 없이 재생할 때(재생은 클라이언트와 상관없이 늘 같다)의 판정. 계산은 S2 계획 6.6절과 같다.

| t | 구역 등급 | `max_density` | `inflow_ratio` | `count` | 셀 등급 [c-0000, c-0001, c-0102] | `grade_pred_60s` |
|---|---|---|---|---|---|---|
| 0 | NORMAL | 1.25 | null | 6.5 | [N, N, N] | [null, null, null] |
| 1 | NORMAL | 1.5 | 0.3 | 11.0 | [N, N, N] | [N, N, N] |
| 2 | NORMAL | 2.0 | 0.45 | 15.0 | [N, N, N] | [N, N, N] |
| 3 | NORMAL | 3.2 | 0.7 | 22.8 | [N, N, N] | [C, N, A] |
| 4 | CAUTION | 4.2 | 0.65 | null | [C, N, A] | [A, N, CR] |

- 반복 뒤 t0에서 다시 초기화되므로 t4는 언제나 위 값이다. 통합 테스트가 이 값을 쓴다.

## 1. 이번 계획에서 정한 것 (계획 대비)
| # | 항목 | 결정 | 이유 |
|---|---|---|---|
| 1 | 방송 경계 | `replay/ZoneBroadcaster` 인터페이스(`playback`, `zoneState`)를 replay에 둔다. ws의 `WsZoneBroadcaster`가 구현한다(메시지 생성 → JSON 1번 → `ZoneSessions.broadcast`). `ZoneSessions`는 세션 관리와 전송만 맡는다 | ws는 `ZoneRegistry`(hello)를 쓰므로 replay가 ws를 알면 패키지 순환이 생긴다. 포트를 replay에 두면 의존이 ws → replay 한 방향이다. 계획 2장의 "`ZoneSessions implements ZoneBroadcaster`"를 정정한다 |
| 2 | 메시지 record | `ws/message/` 패키지. `type`을 첫 성분으로 두고 `type` 없는 보조 생성자를 둔다 | JSON 첫 키가 `type`이다(record 선언 순서). 만드는 쪽이 type 문자열을 틀릴 수 없다 |
| 3 | `hello.schema_version` | `MessageFactory.API_SCHEMA_VERSION = "0.2"` 상수 | 기준값·시간·경로가 아니라 프로토콜 버전이다. 메시지 형식을 바꾸는 PR이 올린다 |
| 4 | `hello.thresholds` | S3는 `{density:{caution,alert,critical}}`만 보낸다. `pressure`·`inflow_ratio`는 S4가 `crowdsight.instability.pressure`·`inflow.ratio`와 함께 더한다 | 값을 코드에 쓰면 설정 규칙 위반이다. 설정 키를 지금 넣으면 "읽는 PR에서 추가" 규칙(결정 기록 6) 위반이다. null은 범례를 오해하게 만든다 `[토론]` |
| 5 | `hello.unacked_alerts` | 늘 `[]`. 성분 타입은 `List<Object>`이고 S5가 `List<AlertMessage>`로 바꾼다 | 키를 미리 둬서 화면 파서가 S5에서 바뀌지 않게 한다 |
| 6 | `zone.inflow_alert` | 늘 `false`(키 유지). S4에서 실제 값 | api-spec 3.2 "키는 빼지 않는다" |
| 7 | 느린 화면 (결정 기록 1) | `join`에서 hello보다 먼저 네이티브 세션에 `BLOCKING_SEND_TIMEOUT = Long.valueOf(send-time-limit-ms)`. 데코레이터는 `(send-time-limit-ms, buffer-size-limit-bytes, TERMINATE)`. 보내기에서 `IOException`·`RuntimeException`이 나면 그 세션을 `close(SESSION_NOT_RELIABLE)`(예외 무시)하고 뺀다 | Tomcat은 `Long`만 읽는다(0장). Tomcat이 먼저 닫더라도 우리 집합에서 빼는 일은 우리가 한다 |
| 8 | `join` 순서 | 속성 → 감싸기 → hello 전송(실패 시 닫고 끝) → 집합 추가 → `raw.isOpen()`이 거짓이면 다시 뺀다 | hello보다 `zone_state`가 먼저 가지 않는다. 그 사이 tick 1개를 놓칠 수 있다(가정). 그 사이 끊긴 세션이 남지 않는다 |
| 9 | ping | `ws/WsPingScheduler`(SmartLifecycle)가 같은 `replayTaskScheduler`에 `scheduleAtFixedRate(sessions::pingAll, ping-interval-ms)`. poolSize 1 → 2. 세션마다 새 `PingMessage` | 재생 스레드가 느린 세션에 막혀 있을 때도 ping이 돌아 데코레이터 한도 검사가 일어난다. `ByteBuffer`를 세션끼리 나눠 쓰지 않는다 |
| 10 | 없는 구역 | 핸드셰이크는 받고 `afterConnectionEstablished`에서 `close(new CloseStatus(4404, "unknown zone"))` | 핸드셰이크에서 거절하면 브라우저는 1006만 본다(조사 2.1) |
| 11 | 경로 | `addHandler(h, "/ws/zones/*")`. ID는 `UriTemplate("/ws/zones/{zoneId}").match(uri.getPath())`이고 빈 값은 없는 구역이다 | Spring은 경로 변수를 핸들러에 넘기지 않는다(조사 2.1) |
| 12 | 허용 출처 (결정 기록 2) | `setAllowedOriginPatterns(props.corsOriginPatterns())`. `Origin` 헤더가 없는 요청(브라우저가 아닌 클라이언트)은 Spring 규칙대로 허용한다 | WebSocket에는 브라우저 CORS가 적용되지 않는다. 서버의 Origin 검사가 교차 사이트 WS 탈취를 막는다 |
| 13 | 시계 | `crowdsight.time-zone`(String, compact constructor에서 `ZoneId.of` 검사). `clockZone()`. `ClockConfig`의 `Clock.system(clockZone())` 빈 | CLAUDE.md "Clock 주입". 테스트는 `Clock.fixed` |
| 14 | `frame_ts` | `FrameTimestamps.now(clock)`, 패턴 `uuuu-MM-dd'T'HH:mm:ss.SSSXXX`(밀리초 아래 버림). 구역·tick마다 1번 만든다 | api-spec 1절. S5 `alert`가 같은 tick의 값을 공유한다 |
| 15 | 직렬화 | 메시지당 `JsonMapper.writeValueAsString` 1번, `TextMessage` 1개를 모든 세션에 보낸다 | 계획 5장. 두 화면이 같은 tick에 같은 바이트를 받는다(테스트) |
| 16 | `ws` 설정 | `CrowdsightProperties.Ws(long pingIntervalMs, int sendTimeLimitMs, int bufferSizeLimitBytes)` 중첩 record(`Replay`와 같은 방식). 세 값 모두 0보다 커야 한다 | 데코레이터 생성자가 `int`를 받는다 |
| 17 | 받은 메시지 | 텍스트는 무시하고 연결은 유지한다. 바이너리는 `TextWebSocketHandler` 기본값(1003 닫기) | api-spec 1절: 요청은 REST |
| 18 | 로그 | 접속·끊김 INFO(`zone=`, `session=`, `접속자=`), 보내기 실패·닫음 WARN, 없는 구역 INFO, 전송 오류 DEBUG | 느린 화면 원인을 로그로 본다 |
| 19 | 테스트 | 단위(mock 세션, `Clock.fixed`, Boot와 같은 `MAPPER`) + 통합(RANDOM_PORT, `StandardWebSocketClient`, `interval-ms=100`) | 조사 2.4. 실제 Tomcat의 차단 2초는 자동 시험하지 않는다(12장 위험) |

## 2. 구조와 파일

### 2.1 추가·수정 파일
```text
server/
├─ README.md                                                     수정 (WebSocket 절)
├─ src/main/resources/application.yml                            수정 (time-zone, ws.*, cors-origin-patterns)
├─ src/main/java/com/tripley/crowdsight/
│  ├─ config/  CrowdsightProperties                              수정 (timeZone, ws, corsOriginPatterns)
│  │           ReplaySchedulerConfig                             수정 (poolSize 2)
│  │           ClockConfig, WebSocketConfig                      추가
│  ├─ replay/  ZoneBroadcaster                                   추가 (인터페이스)
│  │           ZoneRegistry (find), ReplayScheduler (방송)       수정
│  └─ ws/      FrameTimestamps, MessageFactory, ZoneSessions, ZoneWebSocketHandler,
│              WsZoneBroadcaster, WsPingScheduler                추가
│      ws/message/ HelloMessage, PlaybackView, ThresholdsView, ZoneStateMessage, ZoneView, CellView,
│                  PlaybackMessage                               추가
└─ src/test/java/com/tripley/crowdsight/
   ├─ CrowdsightServerApplicationIntegrationTest                 수정 (+2)
   ├─ TimelineStartupIntegrationTest                             수정 (+1)
   ├─ config/   CrowdsightPropertiesTest (+6), TestProperties (TIME_ZONE, WS, CORS, ws(...))
   ├─ replay/   ReplaySchedulerTest (수정 +3), ZoneRegistryTest (추가)
   └─ ws/       FrameTimestampsTest, MessageFactoryTest, MessageJsonTest, ZoneSessionsTest,
                ZoneWebSocketHandlerTest, WsPingSchedulerTest, ZoneWebSocketIntegrationTest   추가
docs/plans/server_s3_ws_plan.md                                  (이 문서)
docs/plans/server_impl_plan.md                                   정정 (9장)
```

### 2.2 1초 흐름 (S3)
```text
ReplayScheduler.tickAll()                       replayTaskScheduler 주기 작업 ①
  └─ for each ZoneRuntime (구역마다 try/catch)
       ZoneRuntime.tick()              → ZoneStep 또는 빈 값(ENDED)
       player().pollStateChange()      → 있으면 INFO + broadcaster.playback(zone, snapshot)
       ZoneStep 있으면                  → DEBUG + broadcaster.zoneState(zone, step)
WsZoneBroadcaster
  playback  : MessageFactory.playback → JsonMapper 1번 → ZoneSessions.broadcast
  zoneState : frame_ts = FrameTimestamps.now(clock) → MessageFactory.zoneState → JsonMapper 1번 → broadcast
ZoneSessions.broadcast(zoneId, json)  세션마다 데코레이터.sendMessage, 실패면 닫고 뺌
WsPingScheduler                       replayTaskScheduler 주기 작업 ② (30초) → ZoneSessions.pingAll()

접속 (Tomcat 스레드)
ZoneWebSocketHandler.afterConnectionEstablished
  zoneIdOf(uri) → ZoneRegistry.find → 없으면 close(4404)
  hello = JsonMapper(MessageFactory.hello(zone)) → ZoneSessions.join(zoneId, raw, hello)
    Tomcat 속성(Long 2000) → 데코레이터 → hello 전송 → 집합 추가 → isOpen 재확인
afterConnectionClosed / handleTransportError → ZoneSessions.leave(raw)
```

### 2.3 스레드 규칙
| 스레드 | 하는 일 | 공유 상태 |
|---|---|---|
| `replay-*` 작업 ① | tick, 판정, 방송 | 판정 상태(잠금 없음, 겹치지 않는 주기 작업 하나), `ZonePlayer`(synchronized) |
| `replay-*` 작업 ② | ping | `ZoneSessions` 맵(Concurrent) |
| Tomcat 접속·IO | hello 생성·전송, join·leave | `ZonePlayer.snapshot()`(synchronized), metaJson(읽기만), `ZoneSessions` 맵 |
- 세션 하나에 두 스레드(①·②)가 동시에 보낼 수 있다. 그래서 `ConcurrentWebSocketSessionDecorator`가 직렬화한다. Tomcat 세션은 동시 전송을 허용하지 않는다.
- poolSize 2: 실행마다 스레드가 바뀔 수 있다. 같은 주기 작업은 겹치지 않고, `ScheduledThreadPoolExecutor` 큐가 앞 실행과 다음 실행 사이의 happens-before를 보장한다. 그래서 판정 상태는 잠금이 없어도 된다.

## 3. 설정

### 3.1 `application.yml` (최종)
```yaml
spring:
  application:
    name: crowdsight-server
  jackson:
    property-naming-strategy: SNAKE_CASE

server:
  port: 8080

# crowdsight.* 설정은 그 값을 읽는 클래스와 같은 PR에서 추가한다 (S4: instability·inflow, S6: alert-log)
crowdsight:
  timeline-dir: ../data/processed/timeline   # 작업 폴더(bootRun·test는 server/) 기준. 시작 로그에 절대 경로가 찍힌다
  timeline-files: [E04_039.json]             # 파일당 구역 1개. 가짜는 --crowdsight.timeline-files=fake_E04_039.json
  time-zone: Asia/Seoul                      # frame_ts 오프셋(+09:00). Clock 빈이 쓴다
  replay:
    interval-ms: 1000                        # 1초 = 타임라인 1칸 (interval_s 1)
    loop: true                               # 끝에서 처음으로 (E8 30분 반복)
  grade:
    density: { caution: 3.0, alert: 4.0, critical: 5.0 }   # 명/㎡, 이상이면 그 등급 (proposal 3.2)
    up-seconds: 2                            # 최근 2개 관측이 모두 현재보다 높으면 올림 (가정)
    down-seconds: 10                         # 최근 10개 관측이 모두 현재보다 낮으면 한 단계 내림 (가정)
    min-walkable-area-m2: 2.0                # 구역 등급·max_density 판정 대상 셀 (결정 4)
  ws:
    ping-interval-ms: 30000                  # 연결 확인 ping (api-spec 3.5)
    send-time-limit-ms: 2000                 # 메시지 하나 보내기가 이보다 오래 막히면 그 세션만 닫음 (결정 기록 1)
    buffer-size-limit-bytes: 524288          # 못 보내고 쌓인 메시지 한도 512KB. ping과 겹쳐 보낼 때만 검사된다
  cors-origin-patterns: ["http://localhost:*", "http://127.0.0.1:*"]   # WS(S3)·REST(S6) 허용 출처 (결정 기록 2)
```

### 3.2 `config/CrowdsightProperties.java` (수정분)
```java
package com.tripley.crowdsight.config;

import java.time.DateTimeException;
import java.time.ZoneId;
import java.util.List;

import org.springframework.boot.context.properties.ConfigurationProperties;

import com.tripley.crowdsight.grade.GradeSettings;

/**
 * crowdsight.* 설정 (application.yml). 기준값·시간·경로는 이 record 한 곳에만 둔다.
 * 값 검사는 compact constructor에서 한다 (validation 스타터 안 씀). 틀리면 서버가 시작하지 않는다.
 * grade는 grade 패키지의 record로 바로 묶고, 그 값 검사는 해당 record가 한다.
 * instability·inflow·alert-log는 그 값을 쓰는 PR(S4~S6)에서 추가한다.
 *
 * @param timelineDir        타임라인 폴더. 상대 경로면 작업 폴더(bootRun·test는 server/) 기준
 * @param timelineFiles      timelineDir 안의 파일 이름. 1개 이상, 파일당 구역 1개
 * @param timeZone           서버 시계의 시간대 (IANA 이름, 예: Asia/Seoul). frame_ts 오프셋이 된다
 * @param replay             재생 설정
 * @param grade              등급 판정 설정 (crowdsight.grade.*)
 * @param ws                 WebSocket 설정 (crowdsight.ws.*)
 * @param corsOriginPatterns 허용 출처 패턴. WebSocket(S3)과 REST(S6)가 같이 쓴다 (결정 기록 2)
 */
@ConfigurationProperties("crowdsight")
public record CrowdsightProperties(String timelineDir, List<String> timelineFiles, String timeZone, Replay replay,
                                   GradeSettings grade, Ws ws, List<String> corsOriginPatterns) {

    public CrowdsightProperties {
        // ... S1 검사 그대로 (timelineDir, timelineFiles) ...
        if (timeZone == null || timeZone.isBlank()) {
            throw new IllegalArgumentException("crowdsight.time-zone 이 없습니다.");
        }
        try {
            ZoneId.of(timeZone);
        } catch (DateTimeException e) {
            throw new IllegalArgumentException("crowdsight.time-zone 을 알 수 없습니다: " + timeZone, e);
        }
        // ... replay, grade 검사 그대로 ...
        if (ws == null) {
            throw new IllegalArgumentException("crowdsight.ws 가 없습니다.");
        }
        if (corsOriginPatterns == null || corsOriginPatterns.isEmpty()) {
            throw new IllegalArgumentException("crowdsight.cors-origin-patterns 에 패턴이 1개 이상 필요합니다.");
        }
        if (corsOriginPatterns.stream().anyMatch(p -> p == null || p.isBlank())) {
            throw new IllegalArgumentException("crowdsight.cors-origin-patterns 에 빈 패턴이 있습니다.");
        }
        timelineFiles = List.copyOf(timelineFiles);
        corsOriginPatterns = List.copyOf(corsOriginPatterns);
    }

    /** 서버 시계의 시간대. 생성할 때 검사했으므로 예외가 나지 않는다. */
    public ZoneId clockZone() {
        return ZoneId.of(timeZone);
    }

    // Replay record는 그대로

    /**
     * WebSocket 설정 (api-spec 3.5).
     *
     * @param pingIntervalMs       ping 간격(ms)
     * @param sendTimeLimitMs      메시지 하나 보내기가 막히는 최대 시간(ms). Tomcat 차단 전송 제한과 데코레이터 한도에 쓴다
     * @param bufferSizeLimitBytes 못 보내고 쌓인 메시지 한도(바이트). 두 스레드가 겹쳐 보낼 때만 검사된다
     */
    public record Ws(long pingIntervalMs, int sendTimeLimitMs, int bufferSizeLimitBytes) {

        public Ws {
            if (pingIntervalMs <= 0) {
                throw new IllegalArgumentException("crowdsight.ws.ping-interval-ms 는 0보다 커야 합니다: " + pingIntervalMs);
            }
            if (sendTimeLimitMs <= 0) {
                throw new IllegalArgumentException(
                        "crowdsight.ws.send-time-limit-ms 는 0보다 커야 합니다: " + sendTimeLimitMs);
            }
            if (bufferSizeLimitBytes <= 0) {
                throw new IllegalArgumentException(
                        "crowdsight.ws.buffer-size-limit-bytes 는 0보다 커야 합니다: " + bufferSizeLimitBytes);
            }
        }
    }
}
```
- 이름 `clockZone()`: `zoneId`는 구역 ID와 헷갈린다.

### 3.3 `config/ClockConfig.java`, `config/ReplaySchedulerConfig.java`
```java
package com.tripley.crowdsight.config;

import java.time.Clock;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/** 서버 시계. 시각이 필요한 곳은 이 Clock을 주입받는다 (Instant.now() 금지, CLAUDE.md). */
@Configuration(proxyBeanMethods = false)
public class ClockConfig {

    /** crowdsight.time-zone 시간대의 시스템 시계. 테스트는 Clock.fixed를 직접 만든다. */
    @Bean
    public Clock clock(CrowdsightProperties props) {
        return Clock.system(props.clockZone());
    }
}
```
```java
    /**
     * 재생·ping 스레드 2개. 재생 tickAll과 ping은 각각 scheduleAtFixedRate 작업 하나다.
     * 같은 주기 작업은 자기와 겹치지 않으므로 판정 상태는 여전히 한 번에 한 스레드만 만진다.
     * 실행마다 스레드가 바뀔 수 있으나 실행기 큐가 앞뒤 실행 사이의 happens-before를 보장한다.
     * ping이 따로 돌아야 느린 세션에 막힌 재생과 겹칠 때 데코레이터 한도 검사가 일어난다.
     */
    @Bean
    public ThreadPoolTaskScheduler replayTaskScheduler() {
        ThreadPoolTaskScheduler scheduler = new ThreadPoolTaskScheduler();
        scheduler.setPoolSize(2);
        scheduler.setThreadNamePrefix("replay-");
        scheduler.setRemoveOnCancelPolicy(true);
        return scheduler;
    }
```

## 4. 메시지

### 4.1 `ws/FrameTimestamps.java`
```java
package com.tripley.crowdsight.ws;

import java.time.Clock;
import java.time.ZonedDateTime;
import java.time.format.DateTimeFormatter;

/** frame_ts 형식: ISO 8601, 밀리초 3자리, 오프셋 (예: 2026-11-18T14:02:31.512+09:00, api-spec 1절). */
public final class FrameTimestamps {

    private static final DateTimeFormatter FORMAT = DateTimeFormatter.ofPattern("uuuu-MM-dd'T'HH:mm:ss.SSSXXX");

    private FrameTimestamps() {
    }

    /** clock의 지금 시각을 clock의 시간대로 적는다. 밀리초 아래는 버린다. 오프셋이 0이면 Z로 적는다. */
    public static String now(Clock clock) {
        return FORMAT.format(ZonedDateTime.now(clock));
    }
}
```

### 4.2 `ws/message/*` (record, 키는 전역 SNAKE_CASE)
```java
package com.tripley.crowdsight.ws.message;

import java.util.List;

import tools.jackson.databind.JsonNode;

/**
 * 접속 직후 1번 보내는 메시지 (api-spec 3.1).
 *
 * @param type          "hello"
 * @param schemaVersion API 메시지 버전 (타임라인 파일 버전과 별개)
 * @param zoneId        구역 ID
 * @param meta          타임라인 meta 원본 트리 그대로 (모르는 키 포함)
 * @param playback      지금 재생 상태
 * @param thresholds    표시용 기준값. S3는 density만, S4가 pressure·inflow_ratio를 더한다
 * @param unackedAlerts 미확인 알림. S5 전까지 늘 빈 목록 (S5에서 List<AlertMessage>로 바꾼다)
 */
public record HelloMessage(String type, String schemaVersion, String zoneId, JsonNode meta, PlaybackView playback,
                           ThresholdsView thresholds, List<Object> unackedAlerts) {

    public static final String TYPE = "hello";

    public HelloMessage {
        unackedAlerts = List.copyOf(unackedAlerts);
    }

    public HelloMessage(String schemaVersion, String zoneId, JsonNode meta, PlaybackView playback,
                        ThresholdsView thresholds, List<Object> unackedAlerts) {
        this(TYPE, schemaVersion, zoneId, meta, playback, thresholds, unackedAlerts);
    }
}
```
```java
/** hello.playback (api-spec 3.1). state는 playing·paused·ended. */
public record PlaybackView(String state, int t, boolean loop, int durationS) {
}

/** hello.thresholds. S4가 pressure·inflowRatio 성분을 더한다. */
public record ThresholdsView(DensityThresholds density) {
}

/** 재생 상태가 바뀔 때 보내는 메시지 (api-spec 3.4). 반복으로 0이면 state playing, t 0. */
public record PlaybackMessage(String type, String zoneId, String state, int t, boolean loop) {

    public static final String TYPE = "playback";

    public PlaybackMessage(String zoneId, String state, int t, boolean loop) {
        this(TYPE, zoneId, state, t, loop);
    }
}

/** 1초마다 보내는 구역 상태 (api-spec 3.2). */
public record ZoneStateMessage(String type, String zoneId, int t, String frameTs, ZoneView zone,
                               List<CellView> cells) {

    public static final String TYPE = "zone_state";

    public ZoneStateMessage {
        cells = List.copyOf(cells);
    }

    public ZoneStateMessage(String zoneId, int t, String frameTs, ZoneView zone, List<CellView> cells) {
        this(TYPE, zoneId, t, frameTs, zone, cells);
    }
}

/** zone_state.zone. inflowRatio·count는 타임라인 값 그대로, inflowAlert는 S4 전까지 false. */
public record ZoneView(Grade grade, Double maxDensity, Double inflowRatio, boolean inflowAlert, Double count) {
}

/** zone_state.cells[]. 측정·예측 값은 타임라인 그대로(null 포함), 서버는 grade·grade_pred_60s만 더한다. */
public record CellView(String cellId, Grade grade, Double density, Double vx, Double vy, Double speedVar,
                       Double pressure, Double counterflow,
                       @JsonProperty("density_pred_60s") Double densityPred60s,
                       @JsonProperty("grade_pred_60s") Grade gradePred60s) {
}
```
- import는 다음과 같다:
  - `com.fasterxml.jackson.annotation.JsonProperty`
  - `com.tripley.crowdsight.grade.Grade`
  - `com.tripley.crowdsight.grade.DensityThresholds`
- null은 그대로 출력한다. `default-property-inclusion`은 설정하지 않는다(계획 6장).

### 4.3 `ws/MessageFactory.java`
```java
package com.tripley.crowdsight.ws;

/**
 * 재생·판정 결과를 API 메시지 record로 바꾼다 (api-spec 3.1~3.4). JSON 변환은 하지 않는다.
 * 상태가 없어 재생 스레드와 Tomcat 접속 스레드에서 같이 불러도 된다.
 */
@Component
@RequiredArgsConstructor
public class MessageFactory {

    /** hello.schema_version. API 메시지 버전 (api-spec v0.2). 메시지 형식을 바꾸는 PR이 올린다. */
    public static final String API_SCHEMA_VERSION = "0.2";

    private final Clock clock;
    private final CrowdsightProperties props;

    /** 접속한 화면에 보낼 hello. 재생 상태는 지금 snapshot이다. */
    public HelloMessage hello(ZoneRuntime zone) {
        ZonePlayer player = zone.player();
        return new HelloMessage(API_SCHEMA_VERSION, zone.zoneId(), player.timeline().metaJson(),
                playbackView(player.snapshot()), new ThresholdsView(props.grade().density()), List.of());
    }

    /** 재생 상태 변화 (반복으로 0, 끝). */
    public PlaybackMessage playback(String zoneId, PlaybackSnapshot snapshot) {
        return new PlaybackMessage(zoneId, stateName(snapshot.state()), snapshot.t(), snapshot.loop());
    }

    /** 한 초 판정 결과. frameTs는 frameTs()로 tick마다 한 번 만든다. */
    public ZoneStateMessage zoneState(String zoneId, ZoneStep step, String frameTs) {
        Frame frame = step.tick().frame();
        ZoneEvaluation eval = step.evaluation();
        ZoneView zone = new ZoneView(eval.zoneGrade(), eval.maxDensity(), frame.inflowRatio(),
                false, frame.count());                                   // inflow_alert는 S4에서 실제 값
        List<CellView> cells = eval.cells().stream().map(MessageFactory::cellView).toList();
        return new ZoneStateMessage(zoneId, eval.t(), frameTs, zone, cells);
    }

    /** 지금 시각의 frame_ts. 한 tick의 zone_state와 alert(S5)는 같은 값을 쓴다. */
    public String frameTs() {
        return FrameTimestamps.now(clock);
    }

    static String stateName(PlaybackState state) {
        return state.name().toLowerCase(Locale.ROOT);
    }

    private static PlaybackView playbackView(PlaybackSnapshot s) {
        return new PlaybackView(stateName(s.state()), s.t(), s.loop(), s.durationS());
    }

    private static CellView cellView(CellEvaluation c) {
        CellState s = c.state();
        return new CellView(c.cellId(), c.grade(), s.density(), s.vx(), s.vy(), s.speedVar(), s.pressure(),
                s.counterflow(), s.densityPred60s(), c.gradePred60s());
    }
}
```

## 5. 세션·핸들러·방송

### 5.1 `ws/ZoneSessions.java`
```java
package com.tripley.crowdsight.ws;

/**
 * 구역별 접속 화면. 세션은 ConcurrentWebSocketSessionDecorator로 감싸 두 스레드(재생·ping)가 보내도 안전하게 한다.
 * 느린 화면(결정 기록 1): 세션마다 Tomcat 차단 전송 제한을 걸고, 보내기가 실패하면 그 세션만 닫고 뺀다.
 * 스레드 규칙: join·leave는 Tomcat 스레드, broadcast는 재생 스레드, pingAll은 ping 스레드가 부른다.
 * 맵은 Concurrent 컬렉션이라 잠금이 없다.
 */
@Slf4j
@Component
public final class ZoneSessions {

    /** Tomcat이 보낼 때마다 읽는 세션 사용자 속성. 값이 Long이 아니면 무시하고 기본 20초를 쓴다 (jar 확인). */
    static final String BLOCKING_SEND_TIMEOUT = "org.apache.tomcat.websocket.BLOCKING_SEND_TIMEOUT";

    private final CrowdsightProperties.Ws ws;
    private final ConcurrentMap<String, Set<WebSocketSession>> byZone = new ConcurrentHashMap<>();
    private final ConcurrentMap<String, Member> bySessionId = new ConcurrentHashMap<>();

    public ZoneSessions(CrowdsightProperties props) {
        this.ws = props.ws();
    }

    /** 감싼 세션과 구역. 키는 원래 세션 ID. */
    private record Member(String zoneId, WebSocketSession session) {
    }

    /**
     * 차단 전송 제한을 걸고, 감싸고, hello를 보낸 뒤 방송 대상에 넣는다.
     * hello 전송이 실패하면 닫고 넣지 않는다. 그 사이 끊겼으면 다시 뺀다.
     */
    public void join(String zoneId, WebSocketSession raw, String helloJson) {
        setBlockingSendTimeout(raw);
        WebSocketSession session = new ConcurrentWebSocketSessionDecorator(raw, ws.sendTimeLimitMs(),
                ws.bufferSizeLimitBytes());
        try {
            session.sendMessage(new TextMessage(helloJson));
        } catch (IOException | RuntimeException e) {
            log.warn("hello 전송 실패, 세션을 닫음 zone={} session={} 원인={}", zoneId, raw.getId(), e.toString());
            closeQuietly(session);
            return;
        }
        bySessionId.put(raw.getId(), new Member(zoneId, session));
        byZone.computeIfAbsent(zoneId, k -> ConcurrentHashMap.newKeySet()).add(session);
        if (!raw.isOpen()) {
            leave(raw);
            return;
        }
        log.info("화면 접속 zone={} session={} 접속자={}", zoneId, raw.getId(), sessionCount(zoneId));
    }

    /** 방송 대상에서 뺀다. 없으면 아무것도 하지 않는다 (닫힘·전송 오류에서 여러 번 불려도 된다). */
    public void leave(WebSocketSession raw) {
        Member member = bySessionId.remove(raw.getId());
        if (member == null) {
            return;
        }
        Set<WebSocketSession> targets = byZone.get(member.zoneId());
        if (targets != null) {
            targets.remove(member.session());
        }
        log.info("화면 접속 끊김 zone={} session={} 접속자={}", member.zoneId(), raw.getId(),
                sessionCount(member.zoneId()));
    }

    /** 이미 만든 JSON 하나를 그 구역 화면 모두에 보낸다. 실패한 세션만 닫고 빼고 나머지는 계속한다. */
    public void broadcast(String zoneId, String json) {
        Set<WebSocketSession> targets = byZone.get(zoneId);
        if (targets == null || targets.isEmpty()) {
            return;
        }
        TextMessage message = new TextMessage(json);
        for (WebSocketSession session : targets) {
            send(zoneId, session, message);
        }
    }

    /** 모든 화면에 ping을 보낸다 (브라우저가 pong으로 자동 응답). */
    public void pingAll() {
        byZone.forEach((zoneId, targets) -> {
            for (WebSocketSession session : targets) {
                send(zoneId, session, new PingMessage());     // ByteBuffer를 세션끼리 나눠 쓰지 않는다
            }
        });
    }

    /** 모든 구역 접속 수. */
    public int sessionCount() {
        return byZone.values().stream().mapToInt(Set::size).sum();
    }

    /** 구역 접속 수. */
    public int sessionCount(String zoneId) {
        Set<WebSocketSession> targets = byZone.get(zoneId);
        return targets == null ? 0 : targets.size();
    }

    /** 테스트용: 구역의 감싼 세션 목록. */
    List<WebSocketSession> sessions(String zoneId) {
        return List.copyOf(byZone.getOrDefault(zoneId, Set.of()));
    }

    private void send(String zoneId, WebSocketSession session, WebSocketMessage<?> message) {
        try {
            session.sendMessage(message);
        } catch (IOException | RuntimeException e) {     // 차단 제한 초과·끊김(IOException), 한도 초과·닫힌 세션(Runtime)
            drop(zoneId, session, e);
        }
    }

    private void drop(String zoneId, WebSocketSession session, Exception cause) {
        Set<WebSocketSession> targets = byZone.get(zoneId);
        if (targets != null) {
            targets.remove(session);
        }
        bySessionId.remove(session.getId());
        log.warn("보내기 실패한 화면을 닫고 뺌 zone={} session={} 원인={}", zoneId, session.getId(), cause.toString());
        closeQuietly(session);
    }

    private void setBlockingSendTimeout(WebSocketSession raw) {
        if (raw instanceof NativeWebSocketSession nativeSession) {
            Session tomcat = nativeSession.getNativeSession(Session.class);
            if (tomcat != null) {
                tomcat.getUserProperties().put(BLOCKING_SEND_TIMEOUT, Long.valueOf(ws.sendTimeLimitMs()));
                return;
            }
        }
        log.warn("Tomcat 세션이 아니라 차단 전송 제한을 걸지 못함 session={} 종류={}", raw.getId(),
                raw.getClass().getName());
    }

    private static void closeQuietly(WebSocketSession session) {
        try {
            session.close(CloseStatus.SESSION_NOT_RELIABLE);
        } catch (IOException | RuntimeException e) {
            log.debug("세션 닫기 실패 무시 session={} 원인={}", session.getId(), e.toString());
        }
    }
}
```
- import: `jakarta.websocket.Session`, `org.springframework.web.socket.*`(`CloseStatus`, `PingMessage`, `TextMessage`, `WebSocketMessage`, `WebSocketSession`), `org.springframework.web.socket.adapter.NativeWebSocketSession`, `org.springframework.web.socket.handler.ConcurrentWebSocketSessionDecorator`.
- Tomcat 상수 클래스는 main에서 import하지 않는다. 문자열이 같은지는 테스트가 `org.apache.tomcat.websocket.Constants`로 확인한다.

### 5.2 `ws/ZoneWebSocketHandler.java`
```java
/**
 * /ws/zones/{zone_id} 접속 처리 (api-spec 3절). 접속하면 hello를 보낸 뒤 방송 대상에 넣는다.
 * 없는 구역이면 닫기 코드 4404로 닫는다. 화면 → 서버 텍스트 메시지는 무시한다 (요청은 REST).
 * 스레드 규칙: Tomcat 스레드에서 불린다. 상태는 ZoneSessions에만 있다.
 */
@Slf4j
@Component
@RequiredArgsConstructor
public class ZoneWebSocketHandler extends TextWebSocketHandler {

    /** 없는 구역 (api-spec 3.1). 4000~4999는 응용이 정해 쓰는 닫기 코드다. */
    public static final CloseStatus UNKNOWN_ZONE = new CloseStatus(4404, "unknown zone");

    private static final UriTemplate PATH = new UriTemplate("/ws/zones/{zoneId}");

    private final ZoneRegistry zones;
    private final ZoneSessions sessions;
    private final MessageFactory messages;
    private final JsonMapper jsonMapper;

    @Override
    public void afterConnectionEstablished(WebSocketSession session) throws Exception {
        Optional<ZoneRuntime> zone = zoneIdOf(session.getUri()).flatMap(zones::find);
        if (zone.isEmpty()) {
            log.info("없는 구역 접속을 닫음 uri={} session={}", session.getUri(), session.getId());
            session.close(UNKNOWN_ZONE);
            return;
        }
        String hello = jsonMapper.writeValueAsString(messages.hello(zone.get()));
        sessions.join(zone.get().zoneId(), session, hello);
    }

    @Override
    protected void handleTextMessage(WebSocketSession session, TextMessage message) {
        // 화면 → 서버 메시지는 쓰지 않는다 (api-spec 1절: 요청은 REST). 연결은 유지한다.
    }

    @Override
    public void handleTransportError(WebSocketSession session, Throwable exception) {
        log.debug("WS 전송 오류 session={} 원인={}", session.getId(), exception.toString());
        sessions.leave(session);
    }

    @Override
    public void afterConnectionClosed(WebSocketSession session, CloseStatus status) {
        sessions.leave(session);
    }

    /** 경로에서 구역 ID를 꺼낸다. 형식이 다르거나 비어 있으면 빈 값. */
    static Optional<String> zoneIdOf(URI uri) {
        if (uri == null || !PATH.matches(uri.getPath())) {
            return Optional.empty();
        }
        return Optional.ofNullable(PATH.match(uri.getPath()).get("zoneId")).filter(id -> !id.isEmpty());
    }
}
```
- 핸들러가 던진 예외는 Spring이 감싸 둔 `ExceptionWebSocketHandlerDecorator`가 1011로 닫는다(Spring 기본).

### 5.3 `config/WebSocketConfig.java`
```java
/** WebSocket 경로와 허용 출처 (api-spec 2절, 결정 기록 2). */
@Configuration(proxyBeanMethods = false)
@EnableWebSocket
@RequiredArgsConstructor
public class WebSocketConfig implements WebSocketConfigurer {

    private final ZoneWebSocketHandler zoneHandler;
    private final CrowdsightProperties props;

    @Override
    public void registerWebSocketHandlers(WebSocketHandlerRegistry registry) {
        registry.addHandler(zoneHandler, "/ws/zones/*")
                .setAllowedOriginPatterns(props.corsOriginPatterns().toArray(String[]::new));
    }
}
```

### 5.4 `replay/ZoneBroadcaster.java`, `ws/WsZoneBroadcaster.java`
```java
package com.tripley.crowdsight.replay;

/**
 * tick 결과를 화면으로 내보내는 곳. ws 패키지가 구현한다.
 * replay가 ws에 의존하지 않도록 인터페이스를 여기 둔다 (의존 방향 ws → replay).
 * 스레드 규칙: ReplayScheduler의 재생 작업에서만 부른다. 한 tick 안에서는 playback → zoneState 순서다.
 */
public interface ZoneBroadcaster {

    /** 재생 상태가 바뀌었다 (반복으로 0, 끝). */
    void playback(String zoneId, PlaybackSnapshot snapshot);

    /** 한 초 판정 결과. */
    void zoneState(String zoneId, ZoneStep step);
}
```
```java
package com.tripley.crowdsight.ws;

/**
 * 재생 결과를 메시지당 JSON 한 번으로 바꿔 그 구역 화면 모두에 보낸다.
 * 스레드 규칙: 재생 작업에서만 불린다. 세션별 전송 안전은 ZoneSessions가 맡는다.
 */
@Component
@RequiredArgsConstructor
public class WsZoneBroadcaster implements ZoneBroadcaster {

    private final MessageFactory messages;
    private final ZoneSessions sessions;
    private final JsonMapper jsonMapper;

    @Override
    public void playback(String zoneId, PlaybackSnapshot snapshot) {
        send(zoneId, messages.playback(zoneId, snapshot));
    }

    @Override
    public void zoneState(String zoneId, ZoneStep step) {
        send(zoneId, messages.zoneState(zoneId, step, messages.frameTs()));
    }

    private void send(String zoneId, Object message) {
        sessions.broadcast(zoneId, jsonMapper.writeValueAsString(message));
    }
}
```

### 5.5 `ws/WsPingScheduler.java`
```java
/**
 * ping-interval-ms마다 모든 화면에 ping을 보낸다 (api-spec 3.5).
 * 재생과 같은 replayTaskScheduler(스레드 2개)의 두 번째 주기 작업이다.
 * SmartLifecycle 기본 phase라 웹 서버가 뜬 뒤 시작하고 닫을 때 먼저 멈춘다.
 */
@Slf4j
@Component
@RequiredArgsConstructor
public class WsPingScheduler implements SmartLifecycle {

    private final ZoneSessions sessions;
    private final ThreadPoolTaskScheduler replayTaskScheduler;
    private final CrowdsightProperties props;
    private volatile ScheduledFuture<?> future;

    @Override
    public void start() {
        if (future != null) {
            return;
        }
        Duration interval = Duration.ofMillis(props.ws().pingIntervalMs());
        future = replayTaskScheduler.scheduleAtFixedRate(sessions::pingAll, interval);
        log.info("ping 시작: 간격 {} ms", interval.toMillis());
    }

    @Override
    public void stop() {
        ScheduledFuture<?> running = future;
        if (running != null) {
            running.cancel(false);
            future = null;
        }
    }

    @Override
    public boolean isRunning() {
        return future != null;
    }
}
```

### 5.6 `replay/ReplayScheduler.java` (수정분)
- 필드에 `private final ZoneBroadcaster broadcaster;`를 마지막에 추가한다. `@RequiredArgsConstructor` 순서는 `(zones, replayTaskScheduler, props, broadcaster)`다.
- 클래스 Javadoc 마지막 줄은 이렇게 바꾼다: "tick마다 재생 상태 변화(playback)를 먼저, 판정 결과(zone_state)를 다음에 ZoneBroadcaster로 보낸다."
- Javadoc의 "스레드 하나에서만"은 "주기 작업 하나(겹치지 않음)에서만"으로 바꾼다.
```java
    /** 모든 구역을 한 칸씩 진행·판정하고 내보낸다. 재생 작업에서만 부른다 (테스트는 직접 부른다). */
    void tickAll() {
        for (ZoneRuntime zone : zones.all()) {
            try {
                tickZone(zone);
            } catch (RuntimeException e) {
                log.error("구역 재생 중 오류, 다음 구역으로 계속 zone={}", zone.zoneId(), e);
            }
        }
    }

    /** 한 구역: tick → [playback] → zone_state. 반복 tick이면 playback이 zone_state(t=0)보다 먼저 나간다. */
    private void tickZone(ZoneRuntime zone) {
        Optional<ZoneStep> step = zone.tick();
        Optional<PlaybackSnapshot> change = zone.player().pollStateChange();
        if (change.isPresent()) {
            PlaybackSnapshot s = change.get();
            log.info("재생 상태 zone={} state={} t={} loop={}", zone.zoneId(), s.state(), s.t(), s.loop());
            broadcaster.playback(zone.zoneId(), s);
        }
        if (step.isPresent()) {
            ZoneStep s = step.get();
            log.debug("재생 zone={} t={} discontinuity={} wrapped={} grade={} max_density={}", zone.zoneId(),
                    s.tick().frame().t(), s.tick().discontinuity(), s.tick().wrapped(),
                    s.evaluation().zoneGrade(), s.evaluation().maxDensity());
            broadcaster.zoneState(zone.zoneId(), s);
        }
    }
```

### 5.7 `replay/ZoneRegistry.java` (수정분)
```java
    private final List<ZoneRuntime> zones;
    private final Map<String, ZoneRuntime> byId;

    public ZoneRegistry(TimelineLoader loader, CrowdsightProperties props) {
        this.zones = loader.loadAll().stream()
                .map(timeline -> register(timeline, props))
                .toList();
        this.byId = zones.stream().collect(Collectors.toUnmodifiableMap(ZoneRuntime::zoneId, Function.identity()));
    }

    /** 구역 ID로 찾는다. 없거나 null이면 빈 값. 목록이 바뀌지 않으므로 여러 스레드에서 불러도 된다. */
    public Optional<ZoneRuntime> find(String zoneId) {
        return zoneId == null ? Optional.empty() : Optional.ofNullable(byId.get(zoneId));
    }
```
- `toUnmodifiableMap`의 `get(null)`은 NPE를 던지므로 null을 먼저 거른다.
- `zone_id` 중복은 `TimelineLoader`가 이미 거부한다.

## 6. 테스트
공통 표기: N=NORMAL, C=CAUTION, A=ALERT, CR=CRITICAL. 고정 시계 `FIXED = Clock.fixed(Instant.parse("2026-11-18T05:02:31.512Z"), ZoneId.of("Asia/Seoul"))`. JSON은 `TimelineFixtures.MAPPER`(SNAKE_CASE, yml과 같음).

### 6.1 테스트 도우미 (`config/TestProperties`)
```java
    public static final String TIME_ZONE = "Asia/Seoul";
    public static final CrowdsightProperties.Ws WS = new CrowdsightProperties.Ws(30000, 2000, 524288);
    public static final List<String> CORS = List.of("http://localhost:*", "http://127.0.0.1:*");

    public static CrowdsightProperties of(String timelineDir, List<String> files, long intervalMs, boolean loop) {
        return full(timelineDir, files, intervalMs, loop, WS);
    }

    /** fixture 기본값에 WebSocket 설정만 바꾼다. */
    public static CrowdsightProperties ws(CrowdsightProperties.Ws ws) {
        return full("src/test/resources/timeline", List.of("valid_v02.json"), 1000, true, ws);
    }

    private static CrowdsightProperties full(String dir, List<String> files, long intervalMs, boolean loop,
                                             CrowdsightProperties.Ws ws) {
        return new CrowdsightProperties(dir, files, TIME_ZONE, new CrowdsightProperties.Replay(intervalMs, loop),
                GRADE, ws, CORS);
    }
    // replay(...)는 그대로 (of를 부른다)
```

### 6.2 `ws/FrameTimestampsTest`
| 메서드 | `@DisplayName` | 입력 (`Clock.fixed(…, Asia/Seoul)`) | 기대 |
|---|---|---|---|
| `formatsMillisAndOffset` | "밀리초 3자리와 +09:00을 붙인다" | `2026-11-18T05:02:31.512Z` | `"2026-11-18T14:02:31.512+09:00"` |
| `padsWholeSecond` | "밀리초가 0이면 .000으로 적는다" | `2026-11-18T05:02:31Z` | `"2026-11-18T14:02:31.000+09:00"` |
| `truncatesBelowMillis` | "밀리초 아래는 버린다" | `2026-11-18T05:02:31.512999999Z` | `"2026-11-18T14:02:31.512+09:00"` |
| `rollsDateInZone` | "시간대 기준으로 날짜가 넘어간다" | `2026-11-18T15:30:00.007Z` | `"2026-11-19T00:30:00.007+09:00"` |
| `utcWritesZ` | "오프셋 0이면 Z로 적는다" | 같은 시각, `ZoneOffset.UTC` | `"2026-11-18T05:02:31.512Z"` |

### 6.3 `config/CrowdsightPropertiesTest` (수정, `Binder`)
`defaults()`에 다음 키를 더한다:
- `crowdsight.time-zone`=Asia/Seoul
- `crowdsight.ws.ping-interval-ms`=30000, `send-time-limit-ms`=2000, `buffer-size-limit-bytes`=524288
- `crowdsight.cors-origin-patterns[0]`=`http://localhost:*`, `[1]`=`http://127.0.0.1:*`

| 메서드 | `@DisplayName` | 입력 | 기대 |
|---|---|---|---|
| (S1·S2 10개) | 그대로 | 기본 맵 | 그대로 통과 |
| `bindsWsCorsAndTimeZone` | "ws·허용 출처·시간대 키를 묶는다" | 기본 맵 | `ws()` == `TestProperties.WS`, `corsOriginPatterns()` == `CORS`, `clockZone()` == `ZoneId.of("Asia/Seoul")` |
| `rejectsNonPositiveWs` (`@ValueSource(strings = {"ping-interval-ms", "send-time-limit-ms", "buffer-size-limit-bytes"})`) | "ws 값이 0이면 거부한다" | `crowdsight.ws.{key}`=0 | `BindException`, 원인 메시지에 `crowdsight.ws.{key}` |
| `rejectsMissingWs` | "ws 설정이 없으면 거부한다" | `crowdsight.ws.` 키 3개 제거 | 원인 메시지 `crowdsight.ws` |
| `rejectsUnknownTimeZone` | "모르는 시간대면 거부한다" | `time-zone`=Mars/Base | 원인 메시지 `crowdsight.time-zone` |
| `rejectsMissingCorsPatterns` | "허용 출처가 없으면 거부한다" | cors 키 2개 제거 | 원인 메시지 `crowdsight.cors-origin-patterns` |
| `rejectsBlankCorsPattern` | "빈 허용 출처 패턴을 거부한다" | `[1]`=" " | 원인 메시지 `빈 패턴` |

### 6.4 `ws/MessageFactoryTest` (`new MessageFactory(FIXED, TestProperties.replay(1000, true))`)
fixture 런타임:
- `timeline = new TimelineLoader(MAPPER, TestProperties.of(fixturePath().getParent().toString(), List.of("valid_v02.json"), 1000, true)).loadAll().get(0)`
- `runtime = new ZoneRuntime(new ZonePlayer(timeline, true), new ZoneGrader(timeline.meta().cells(), GRADE))`

| 메서드 | `@DisplayName` | 입력 | 기대 |
|---|---|---|---|
| `helloFromFixture` | "hello는 meta 원본·재생 상태·밀도 기준·빈 미확인 알림을 담는다" | tick 전 `hello(runtime)` | type `"hello"`, schemaVersion `"0.2"`, zoneId `"zone-test"`, `meta` `isSameAs(timeline.metaJson())`, playback == `PlaybackView("playing", 0, true, 5)`, thresholds == `ThresholdsView(DensityThresholds(3.0, 4.0, 5.0))`, unackedAlerts 비어 있음 |
| `helloReflectsCurrentPlayback` | "hello 재생 위치는 마지막으로 준 프레임이다" | `tick()` 3번 뒤 | playback.t 2 |
| `zoneStateAtT4` | "t4 zone_state는 fixture 판정과 같다" | `tick()` 5번, 마지막 step, frameTs `messages.frameTs()` | t 4, frameTs `"2026-11-18T14:02:31.512+09:00"`, zone == `ZoneView(CAUTION, 4.2, 0.65, false, null)`, cells == [`CellView("c-0000", CAUTION, 4.2, 0.3, -0.1, 0.012, 0.0504, 0.25, 4.6, ALERT)`, `("c-0001", NORMAL, 1.5, 0.2, 0.0, 0.006, 0.009, null, 1.6, NORMAL)`, `("c-0102", ALERT, 5.5, 0.2, 0.1, 0.006, 0.033, null, 5.9, CRITICAL)`] |
| `zoneStateAtT0KeepsNulls` | "null 값은 null 그대로 옮긴다" | 첫 step(t0) | zone == `ZoneView(NORMAL, 1.25, null, false, 6.5)`, cells[1] == `CellView("c-0001", NORMAL, 0.0, null, null, null, 0.0, null, null, null)` |
| `playbackStateLowercase` (`@CsvSource({"PLAYING,playing", "PAUSED,paused", "ENDED,ended"})`) | "재생 상태는 소문자로 보낸다" | `playback("zone-test", new PlaybackSnapshot(state, 4, false, 5))` | == `PlaybackMessage("playback", "zone-test", 기대, 4, false)` |
| `frameTsUsesClock` | "frame_ts는 주입한 시계를 쓴다" | `frameTs()` | `"2026-11-18T14:02:31.512+09:00"` |

### 6.5 `ws/MessageJsonTest` (`MAPPER.writeValueAsString` → `readTree`)
| 메서드 | `@DisplayName` | 입력 | 기대 |
|---|---|---|---|
| `helloKeys` | "hello 키는 api-spec 3.1과 같다" | `helloFromFixture` 메시지 | 루트 `propertyNames()` = {type, schema_version, zone_id, meta, playback, thresholds, unacked_alerts}. playback {state, t, loop, duration_s}, thresholds {density}, density {caution, alert, critical}. `unacked_alerts`는 크기 0인 배열 |
| `helloMatchesSample` | "hello 출력이 7.1절 예시와 같다" | tick 3번 뒤 hello | `readTree(json)` == `readTree(7.1절 예시)` (트리 비교, 키 순서 무시) |
| `helloMetaPassthrough` | "meta의 모르는 키도 그대로 보낸다" | `timelineOf(5)`에서 metaJson만 `{"foo":1,"zone_id":"zone-test"}`로 바꾼 `ZoneTimeline` | `meta.foo` == 1 |
| `zoneStateKeys` | "zone_state·zone·cells 키는 api-spec 3.2와 같다" | `zoneStateAtT4` 메시지 | 루트 {type, zone_id, t, frame_ts, zone, cells}. zone {grade, max_density, inflow_ratio, inflow_alert, count}. 각 셀 {cell_id, grade, density, vx, vy, speed_var, pressure, counterflow, density_pred_60s, grade_pred_60s}. `density_pred60s` 키 없음 |
| `zoneStateKeepsNullKeys` | "null 값도 키를 빼지 않는다" | `zoneStateAtT0KeepsNulls` | 문자열에 `"inflow_ratio":null`, `"vx":null`, `"grade_pred_60s":null`. `cells[1].has("counterflow")`이고 `isNull()` |
| `zoneStateMatchesSamples` | "zone_state 출력이 7.2·7.3절 예시와 같다" | t0, t4 메시지 | 각각 트리가 같다. JSON이 `{"type":"zone_state","zone_id":"zone-test","t":`로 시작한다 (record 선언 순서) |
| `playbackKeys` | "playback 키는 api-spec 3.4와 같다" | `PlaybackMessage("zone-test", "playing", 0, true)` | 트리 == 7.4절 예시. 키 {type, zone_id, state, t, loop} |

### 6.6 `ws/ZoneSessionsTest` (Mockito)
도우미:
- `session(id)`: `mock(WebSocketSession.class)`. `getId()`는 id, `isOpen()`은 true를 돌려준다.
- `sent(session)`: `mockingDetails(session).getInvocations()`에서 `sendMessage` 인자를 뽑는다. `TextMessage`이면 payload를, 아니면 `"PING"`을 넣은 목록이다.
- `sessions = new ZoneSessions(TestProperties.ws(TestProperties.WS))`.

| 메서드 | `@DisplayName` | 입력 | 기대 |
|---|---|---|---|
| `setsTomcatBlockingSendTimeout` | "Tomcat 차단 전송 제한을 Long 2000으로 건다" | `mock(NativeWebSocketSession.class)`. `getNativeSession(jakarta.websocket.Session.class)`는 mock 세션을 주고, 그 세션의 `getUserProperties()`는 `HashMap`을 준다. 그다음 `join` | 맵에 `org.apache.tomcat.websocket.Constants.BLOCKING_SEND_TIMEOUT_PROPERTY` → `2000L`, 값은 `Long` |
| `sendsHelloBeforeBroadcast` | "hello를 먼저 보내고 방송을 받는다" | `join(z, a, "hello")`, `broadcast(z, "s1")` | `sent(a)` == ["hello", "s1"] |
| `broadcastsOnlyToSameZone` | "다른 구역 방송은 받지 않는다" | a는 zone-test, b는 zone-b. `broadcast("zone-test", "s1")` | `sent(a)` 끝이 "s1", `sent(b)` == ["hello"] |
| `dropsFailingSessionOnIoException` | "보내기에서 IOException이 나면 그 세션만 닫고 뺀다" | a 정상. b는 `doNothing().doThrow(new IOException("끊김"))`. `broadcast` 2번 ("s1", "s2") | `verify(b).close(SESSION_NOT_RELIABLE)` 1번. `sent(a)` == [hello, s1, s2]. b의 `sendMessage`는 2번(hello, s1). `sessionCount()` 1 |
| `dropsFailingSessionOnRuntimeException` | "보내기에서 RuntimeException이 나도 그 세션만 뺀다" | b 두 번째 호출이 `IllegalStateException` | 위와 같다 |
| `dropsWhenPingFindsStuckSend` | "재생이 막힌 세션은 ping이 한도를 검사해 닫는다" | `Ws(30000, 50, 524288)`. a의 두 번째 `sendMessage`는 latch로 멈춘다. 다른 스레드에서 `broadcast`, `getTimeSinceSendStarted() > 50`까지 대기한 뒤 `pingAll()`. 그다음 latch를 푼다 | 막힌 방송 `Future`가 예외 없이 끝난다. `verify(a, times(1)).close(SESSION_NOT_RELIABLE)`, `sessionCount()` 0 |
| `helloFailureNotJoined` | "hello를 못 보내면 닫고 넣지 않는다" | a의 `sendMessage`가 늘 `IOException` | close(SESSION_NOT_RELIABLE), `sessionCount()` 0 |
| `removesSessionClosedDuringHello` | "hello 중에 끊긴 세션은 남기지 않는다" | a `isOpen()` false | `sessionCount()` 0 |
| `leaveRemoves` | "leave하면 방송 대상에서 빠진다" | join → `leave(a)` → `broadcast` | `sent(a)` == ["hello"], count 0. `leave(a)` 한 번 더 불러도 예외 없음 |
| `pingAllSendsPing` | "pingAll은 모든 구역 세션에 ping을 보낸다" | a(zone-test), b(zone-b) | `sent(a)`·`sent(b)` 끝이 "PING" |

`dropsWhenPingFindsStuckSend` 순서 (손 추적):
1. `join`: hello가 delegate로 바로 간다(잠금 획득).
2. 스레드 R `broadcast("zone-test","zs")`: 데코레이터가 잠금을 얻고 `sendStartTime`을 기록한다. delegate는 latch에서 멈춘다.
3. 테스트 스레드: `getTimeSinceSendStarted() > 50`까지 Awaitility로 기다린다.
4. `pingAll()`: ping을 버퍼에 넣고 `tryLock`에 실패한다. 그래서 `checkSessionLimits`를 부르고, 경과 시간이 50보다 커서 `SessionLimitExceededException`이 난다. 우리 `send`가 잡아 `drop`하면 `close(SESSION_NOT_RELIABLE)`가 delegate로 간다.
5. latch를 푼다. R의 flush 루프는 `shouldNotSend()`(limitExceeded)를 보고 끝난다. 예외는 없다.

### 6.7 `ws/ZoneWebSocketHandlerTest`
| 메서드 | `@DisplayName` | 입력 | 기대 |
|---|---|---|---|
| `parsesZoneId` (`@CsvSource({"/ws/zones/zone-test,zone-test", "/ws/zones/zone-e04-039,zone-e04-039"})`) | "경로에서 구역 ID를 꺼낸다" | `URI.create("ws://localhost:8080" + path)` | 값 |
| `emptyForOtherPaths` (`@ValueSource(strings = {"/ws/zones/", "/ws/other/zone-test", "/ws/zones"})`) | "구역 ID가 없거나 다른 경로면 빈 값" | 같다 | 빈 값. `zoneIdOf(null)`도 빈 값 |

### 6.8 `replay/ReplaySchedulerTest` (수정), `replay/ZoneRegistryTest` (추가)
- 기존 2개: `new ReplayScheduler(registry, scheduler, props, mock(ZoneBroadcaster.class))`. 기대는 그대로다.
- `RecordingBroadcaster`(테스트 안 클래스): `"playback " + state + " " + t`, `"zone_state " + t`를 목록에 쌓는다.

| 메서드 | `@DisplayName` | 입력 | 기대 |
|---|---|---|---|
| `wrapSendsPlaybackBeforeZoneState` | "반복으로 처음에 돌아오면 playback을 zone_state보다 먼저 보낸다" | `runtime(new ZonePlayer(timelineOf(3), true))`, `tickAll()` 4번 | ["zone_state 0", "zone_state 1", "zone_state 2", "playback PLAYING 0", "zone_state 0"] |
| `endSendsPlaybackOnce` | "끝나면 playback(ended)을 한 번만 보낸다" | `timelineOf(2)`, loop false, `tickAll()` 4번 | ["zone_state 0", "zone_state 1", "playback ENDED 1"] |
| `broadcastFailureDoesNotStopOtherZones` | "한 구역 방송이 실패해도 같은 tick의 다른 구역은 보낸다" | 구역 2개(`timelineOf(5)`). mock 방송기 `doThrow(new IllegalStateException("시험")).doNothing().when(b).zoneState(any(), any())`. `tickAll()` 2번 | 예외 없음. `verify(b, times(4)).zoneState(eq("zone-test"), any())` |
| `ZoneRegistryTest.findsById` | "구역 ID로 찾는다" | fixture `TimelineLoader` + `TestProperties.of(...)` | `find("zone-test")`는 `all().get(0)`과 같은 객체. `find("nope")`·`find(null)`·`find("")`는 빈 값 |

### 6.9 `ws/WsPingSchedulerTest`
| 메서드 | `@DisplayName` | 입력 | 기대 |
|---|---|---|---|
| `pingsOnIntervalUntilStop` | "간격마다 pingAll을 부르고 stop하면 멈춘다" | `mock(ZoneSessions.class)`, 실제 `ThreadPoolTaskScheduler`(pool 1), `TestProperties.ws(new Ws(20, 2000, 524288))`. `start()` | 2초 안에 `pingAll()` 3번 이상. `stop()` 뒤 `isRunning()` false |

### 6.10 통합 테스트
`ws/ZoneWebSocketIntegrationTest`:
```java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT, properties = {
        "crowdsight.timeline-dir=src/test/resources/timeline",
        "crowdsight.timeline-files=valid_v02.json",
        "crowdsight.replay.interval-ms=100"
})
class ZoneWebSocketIntegrationTest {

    private static final Duration WAIT = Duration.ofSeconds(3);
    private static final Pattern FRAME_TS =
            Pattern.compile("\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}\\.\\d{3}\\+09:00");

    @LocalServerPort
    private int port;

    @Autowired
    private ZoneSessions sessions;

    private final StandardWebSocketClient client = new StandardWebSocketClient();
    private final List<WebSocketSession> opened = new ArrayList<>();

    @AfterEach
    void closeClients() throws IOException {
        for (WebSocketSession s : opened) {
            if (s.isOpen()) {
                s.close();
            }
        }
        await().atMost(WAIT).until(() -> sessions.sessionCount() == 0);   // 다음 테스트가 0에서 시작
    }

    private Inbox connect(String zoneId) throws Exception {
        Inbox inbox = new Inbox();
        opened.add(client.execute(inbox, "ws://localhost:{port}/ws/zones/{zone}", port, zoneId)
                .get(5, TimeUnit.SECONDS));
        return inbox;
    }

    private CompletableFuture<WebSocketSession> connectWithOrigin(Inbox inbox, String origin) {
        WebSocketHttpHeaders headers = new WebSocketHttpHeaders();
        headers.setOrigin(origin);
        return client.execute(inbox, headers, URI.create("ws://localhost:" + port + "/ws/zones/zone-test"));
    }

    /** 클라이언트가 받은 메시지와 닫힘 상태. Tomcat 클라이언트 스레드가 채운다. */
    static final class Inbox extends TextWebSocketHandler {
        final BlockingQueue<JsonNode> messages = new LinkedBlockingQueue<>();
        final CompletableFuture<CloseStatus> closed = new CompletableFuture<>();

        @Override
        protected void handleTextMessage(WebSocketSession session, TextMessage message) {
            messages.add(MAPPER.readTree(message.getPayload()));
        }

        @Override
        public void afterConnectionClosed(WebSocketSession session, CloseStatus status) {
            closed.complete(status);
        }

        JsonNode next() throws InterruptedException {
            JsonNode node = messages.poll(WAIT.toMillis(), TimeUnit.MILLISECONDS);
            assertThat(node).as("메시지가 와야 한다").isNotNull();
            return node;
        }

        /** 다음 zone_state (최대 50개 넘김). */
        JsonNode nextZoneState() throws InterruptedException { /* type이 zone_state일 때까지 next() */ }

        /** t가 같은 zone_state까지 넘긴다 (최대 50개). */
        JsonNode zoneStateAt(int t) throws InterruptedException { /* 같다 */ }
    }
}
```

| 메서드 | `@DisplayName` | 동작 | 기대 |
|---|---|---|---|
| `helloFirst` | "접속하면 hello를 먼저 받는다" | `connect("zone-test").next()` | type `hello`, schema_version `"0.2"`, zone_id `zone-test`, `meta.video_id` `TEST_001`, `meta.cells` 크기 3, playback.state `playing`, loop true, duration_s 5, `thresholds.density.alert` 4.0, `unacked_alerts` 크기 0 |
| `zoneStatesInOrderWithPlaybackOnWrap` | "zone_state t가 1씩 늘고, 반복 때 playback(playing, 0)이 먼저 온다" | hello 뒤 15개 수집 | 모두 `zone_state` 또는 `playback`. 두 번째 zone_state부터 t == (앞 t + 1) % 5. 그 t가 0이면 바로 앞 메시지가 `{type: playback, state: playing, t: 0, loop: true}`. playback이 1개 이상 있다 |
| `zoneStateMatchesFixtureAtT4` | "t4 zone_state 값·키·frame_ts 형식이 맞다" | `zoneStateAt(4)` | 루트 키 6개. `frame_ts`가 `FRAME_TS`와 맞는다. zone {grade CAUTION, max_density 4.2, inflow_ratio 0.65, inflow_alert false, count는 키 있고 null}. 셀 grade [CAUTION, NORMAL, ALERT], grade_pred_60s [ALERT, NORMAL, CRITICAL]. 셀마다 키 10개. `cells[1].counterflow` null |
| `unknownZoneClosedWith4404` | "없는 구역은 4404 unknown zone으로 닫는다" | `connect("nope")` | `closed.get(3, SECONDS)` code 4404, reason `"unknown zone"`. 받은 메시지 없음 |
| `twoClientsReceiveSameMessage` | "두 화면이 같은 tick에 같은 메시지를 받는다" | a 접속·hello, b 접속·hello. b의 첫 zone_state를 a에서 찾는다 (최대 50개) | a에 b와 같은 JsonNode(t·frame_ts·값 모두 같음)가 있다 |
| `ignoresClientMessages` | "화면이 보낸 메시지는 무시하고 연결을 유지한다" | hello 뒤 클라이언트가 `{"type":"ack"}`와 `not json`을 보낸다 | 이어서 zone_state 3개를 받고, 클라이언트 세션 `isOpen()` true |
| `allowsLocalhostOrigin` (`@ValueSource(strings = {"http://localhost:5173", "http://127.0.0.1:5173"})`) | "허용 출처 패턴의 화면은 접속한다" | `connectWithOrigin(inbox, origin).get(5, SECONDS)` | 첫 메시지 type `hello` |
| `rejectsForeignOrigin` | "허용하지 않는 출처는 핸드셰이크에서 거절한다" | origin `http://example.com` | `get(5, SECONDS)`가 `ExecutionException`을 던진다 |
| `setsTomcatBlockingSendTimeout` | "실제 Tomcat 세션에 차단 전송 제한 2000ms가 걸린다" | 접속·hello. `sessionCount("zone-test") == 1`까지 대기. `WebSocketSessionDecorator.unwrap(sessions.sessions("zone-test").get(0))` → `NativeWebSocketSession.getNativeSession(jakarta.websocket.Session.class)` | `getUserProperties()`에 `Constants.BLOCKING_SEND_TIMEOUT_PROPERTY` → `2000L` |
| `removesSessionOnClose` | "화면이 닫으면 방송 대상에서 빠진다" | 접속 → count 1까지 대기 → 클라이언트 `close()` | 3초 안에 `sessionCount()` 0 |

기타 통합 테스트:

| 클래스.메서드 | `@DisplayName` | 기대 |
|---|---|---|
| `CrowdsightServerApplicationIntegrationTest.bindsDefaultWsSettings` (추가) | "application.yml의 ws·허용 출처·시간대 기본값을 읽는다" | `props.ws()` == `TestProperties.WS`, `corsOriginPatterns()` == `CORS`, `timeZone()` `"Asia/Seoul"` |
| `CrowdsightServerApplicationIntegrationTest.clockUsesConfiguredZone` (추가) | "Clock 빈은 설정 시간대를 쓴다" | `clock.getZone()` == `ZoneId.of("Asia/Seoul")` |
| `TimelineStartupIntegrationTest.failsOnUnknownTimeZone` (추가) | "모르는 시간대면 시작하지 않는다" | `--crowdsight.time-zone=Mars/Base`(나머지는 기존과 같음) → `rootCause()` 메시지에 `crowdsight.time-zone` |
| `ReplaySchedulerIntegrationTest` (그대로) | | MOCK 웹 환경에서 `@EnableWebSocket`이 있어도 뜨는지 확인한다 |

- RANDOM_PORT 컨텍스트는 Spring 테스트 컨텍스트 캐시가 갖고 있다가 테스트 JVM이 끝날 때 닫힌다. 포트는 임의라 8080과 부딪히지 않는다.
- Tomcat 클라이언트는 받는 텍스트 버퍼가 기본 8192바이트다. fixture hello는 약 1.2KB라 충분하다(실제 브라우저에는 이 제한이 없다).

## 7. 출력 예시 (fixture `valid_v02.json`, PR 설명·나예린 님 전달용)
`MessageJsonTest`가 7.1~7.4와 같은지 트리로 확인한다. `frame_ts`는 시험용 고정 시계 값이고, 실제로는 보낸 시각이다.

### 7.1 `hello` (재생 t=2에 접속)
```json
{
  "type": "hello",
  "schema_version": "0.2",
  "zone_id": "zone-test",
  "meta": {
    "zone_id": "zone-test",
    "camera_id": "cam-test",
    "video_id": "TEST_001",
    "duration_s": 5,
    "interval_s": 1,
    "cell_size_m": 2.0,
    "models": { "counter": "fixture", "flow": "fixture", "predictor": "fixture" },
    "prediction": { "history_s": 2, "horizon_s": 60 },
    "cells": [
      { "cell_id": "c-0000", "row": 0, "col": 0, "walkable_area_m2": 4.0,
        "image_polygon": [[0.0, 0.0], [0.5, 0.0], [0.5, 0.5], [0.0, 0.5]] },
      { "cell_id": "c-0001", "row": 0, "col": 1, "walkable_area_m2": 4.0,
        "image_polygon": [[0.5, 0.0], [1.0, 0.0], [1.0, 0.5], [0.5, 0.5]] },
      { "cell_id": "c-0102", "row": 1, "col": 2, "walkable_area_m2": 1.5,
        "image_polygon": [[0.5, 0.5], [1.0, 0.5], [1.0, 1.0], [0.5, 1.0]] }
    ]
  },
  "playback": { "state": "playing", "t": 2, "loop": true, "duration_s": 5 },
  "thresholds": { "density": { "caution": 3.0, "alert": 4.0, "critical": 5.0 } },
  "unacked_alerts": []
}
```

### 7.2 `zone_state` t=0 (null이 많은 초)
```json
{
  "type": "zone_state",
  "zone_id": "zone-test",
  "t": 0,
  "frame_ts": "2026-11-18T14:02:31.512+09:00",
  "zone": { "grade": "NORMAL", "max_density": 1.25, "inflow_ratio": null, "inflow_alert": false, "count": 6.5 },
  "cells": [
    { "cell_id": "c-0000", "grade": "NORMAL", "density": 1.25, "vx": 0.1, "vy": 0.0, "speed_var": 0.004,
      "pressure": 0.005, "counterflow": null, "density_pred_60s": null, "grade_pred_60s": null },
    { "cell_id": "c-0001", "grade": "NORMAL", "density": 0.0, "vx": null, "vy": null, "speed_var": null,
      "pressure": 0.0, "counterflow": null, "density_pred_60s": null, "grade_pred_60s": null },
    { "cell_id": "c-0102", "grade": "NORMAL", "density": 1.0, "vx": 0.05, "vy": -0.02, "speed_var": 0.002,
      "pressure": 0.002, "counterflow": null, "density_pred_60s": null, "grade_pred_60s": null }
  ]
}
```

### 7.3 `zone_state` t=4 (구역 주의, 작은 셀 c-0102는 경계지만 구역 등급에서 빠짐)
```json
{
  "type": "zone_state",
  "zone_id": "zone-test",
  "t": 4,
  "frame_ts": "2026-11-18T14:02:31.512+09:00",
  "zone": { "grade": "CAUTION", "max_density": 4.2, "inflow_ratio": 0.65, "inflow_alert": false, "count": null },
  "cells": [
    { "cell_id": "c-0000", "grade": "CAUTION", "density": 4.2, "vx": 0.3, "vy": -0.1, "speed_var": 0.012,
      "pressure": 0.0504, "counterflow": 0.25, "density_pred_60s": 4.6, "grade_pred_60s": "ALERT" },
    { "cell_id": "c-0001", "grade": "NORMAL", "density": 1.5, "vx": 0.2, "vy": 0.0, "speed_var": 0.006,
      "pressure": 0.009, "counterflow": null, "density_pred_60s": 1.6, "grade_pred_60s": "NORMAL" },
    { "cell_id": "c-0102", "grade": "ALERT", "density": 5.5, "vx": 0.2, "vy": 0.1, "speed_var": 0.006,
      "pressure": 0.033, "counterflow": null, "density_pred_60s": 5.9, "grade_pred_60s": "CRITICAL" }
  ]
}
```
- t4에서 c-0000이 C인 이유: 관측이 N, N, N, C(3.2), A(4.2)로 들어왔다. 최근 2개 [C, A]의 최솟값 C가 N보다 높아 C로 올린다.
- c-0102가 A인 이유: 최근 2개 [A(4.0), CR(5.5)]의 최솟값이 A다. 이 셀은 1.5㎡라 구역 등급과 `max_density`에서 빠진다.

### 7.4 `playback` (t=4 다음 tick, 반복으로 처음)
```json
{ "type": "playback", "zone_id": "zone-test", "state": "playing", "t": 0, "loop": true }
```
그다음 메시지는 7.2와 같은 t=0 `zone_state`다(`frame_ts`만 다름).

### 7.5 화면 어댑터 예시 (나예린 님 참고, web 변경은 web 담당)
아래는 `web/src/lib/liveFeed.ts`의 `parseLiveMessage`에 넣을 수 있는 형태다. 지금 있는 `validateTimeline`·`validateFrame`을 그대로 쓴다.
```ts
case 'hello':      // meta로 빈 타임라인을 만든다. hello.schema_version은 API 버전이므로 타임라인 버전은 상수를 쓴다
  return { type: 'timeline', timeline: validateTimeline({ schema_version: SCHEMA_VERSION, meta: obj.meta, frames: [] }, { partial: true }) };
case 'zone_state': // 프레임 모양으로 바꾼다. cells[]는 validateFrame을 통과한다 (grade·grade_pred_60s는 남는 키)
  return { type: 'frames', frames: [{ t: obj.t, inflow_ratio: obj.zone.inflow_ratio, count: obj.zone.count, cells: obj.cells } as Frame] };
case 'playback':   // state playing·t 0이면 쌓은 프레임을 비운다 (마지막 hello의 meta로 timeline을 다시 만든다)
default:
  return null;     // 모르는 type은 무시 (api-spec 1절)
```
- 주소: `.env.local`에 `VITE_WS_URL=ws://localhost:8080/ws/zones/zone-e04-039`(가짜 E04_039).
- 화면 등급은 서버의 `zone.grade`·`cells[].grade`를 쓴다. 표기는 "경계"다.

## 8. 이후 PR이 붙일 곳 (S3에서 만들지 않음)
| PR | 붙는 곳 | 내용 |
|---|---|---|
| S4 | `ThresholdsView`, `MessageFactory.hello` | `pressure`(`instability.pressure`), `inflow_ratio`(`inflow.ratio`) 성분 추가 |
| S4 | `MessageFactory.zoneState` | `ZoneView.inflowAlert` = `ZoneEvaluation.inflowAlert` |
| S5 | `HelloMessage.unackedAlerts` | `List<AlertMessage>` = `AlertStore.unacked(zoneId)` |
| S5 | `ZoneBroadcaster`, `WsZoneBroadcaster` | 같은 tick `frame_ts`로 `zone_state` → `alert` 순서 |
| S6 | `CorsConfig` | REST `/api/**`에 같은 `corsOriginPatterns` |
| S7 | `ZonePlayer` 제어 | 상태가 바뀌면 `pendingChange`. 지금 `tickZone` 순서 그대로 `playback`이 나간다. `/api/health`에 `sessionCount()` |

## 9. `server_impl_plan.md` 정정 (이 PR의 docs 커밋)
1. 1.1절 패키지:
   - `config/`: `CorsConfig` 표시는 S6이다.
   - `replay/`: `ZoneBroadcaster` 추가.
   - `ws/`: `ZoneWebSocketHandler, ZoneSessions, MessageFactory, FrameTimestamps, WsZoneBroadcaster, WsPingScheduler`.
   - `ws/message/`: `HelloMessage, PlaybackView, ThresholdsView, ZoneStateMessage, ZoneView, CellView, PlaybackMessage`(`AlertMessage`는 S5).
2. 1.2절 흐름 `MessageFactory → [playback?] → zone_state → alert…`를 바꾼다: "`ZoneBroadcaster.playback/zoneState`(구현 `WsZoneBroadcaster`: `MessageFactory` → `JsonMapper` 1번 → `ZoneSessions.broadcast`)".
3. 2장 S1 코드 블록 `ReplayScheduler` 생성자: `ZoneBroadcaster broadcaster /* S3부터, replay 패키지 인터페이스 */`.
4. 2장 S3:
   - 제목에 `playback`과 ping을 넣는다.
   - `ZoneSessions`는 `ZoneBroadcaster`를 구현하지 않는다. 시그니처는 `join(zoneId, raw, helloJson)`(Tomcat 속성 → 감싸기 → hello → 추가 → isOpen 재확인), `leave`, `broadcast`, `pingAll`, `sessionCount()`, `sessionCount(zoneId)`.
   - `ThresholdsView(DensityThresholds density)`는 S3이고, `pressure`·`inflowRatio`는 S4.
   - `HelloMessage.unackedAlerts`는 S3에서 `List<Object>`(빈 목록)이고 S5에서 `List<AlertMessage>`.
   - `FrameTimestamps.now(Clock)`, 패턴 `uuuu-…SSSXXX`.
   - `CrowdsightProperties(timelineDir, timelineFiles, timeZone, replay, grade, ws, corsOriginPatterns)`, `Ws(long pingIntervalMs, int sendTimeLimitMs, int bufferSizeLimitBytes)`, `clockZone()`.
   - `ReplaySchedulerConfig` poolSize 2와 `WsPingScheduler`.
   - 테스트 표:
     - `ZoneRuntimeTest.wrapEmitsPlayback`를 `ReplaySchedulerTest.wrapSendsPlaybackBeforeZoneState`(duration 3)로 바꾼다.
     - 통합 기대값은 "zone_state t가 (앞 t+1) mod 5, 0 앞에 playback(playing, 0)"이다.
     - 두 클라이언트 기대값은 "같은 JSON(t·frame_ts 같음)"이다.
     - 허용 출처·차단 전송 제한 통합 테스트를 추가한다.
     - 마지막에 "상세는 `docs/plans/server_s3_ws_plan.md` 6장"을 단다.
5. 2장 S4: "`ThresholdsView`에 `pressure`·`inflow_ratio`, `ZoneView.inflowAlert` 실제 값". 2장 S5: "`HelloMessage.unackedAlerts` 타입 교체".
6. 결정 기록 1에 덧붙인다: "(jar 확인) 값은 `Long`이어야 한다. 시간이 넘으면 Tomcat이 먼저 세션을 닫고(GOING_AWAY) `IOException`을 던진다. 우리는 집합에서 빼고 `SESSION_NOT_RELIABLE` 닫기를 한 번 더 시도한다".
7. 4장 yml: `ws.*`·`time-zone`·`cors-origin-patterns` 주석을 3.1절과 같게 한다. `buffer-size-limit-bytes`는 "ping과 겹칠 때만 검사"다.
8. 5장 표:
   - 세션 행: "`ConcurrentHashMap<String, Set<WebSocketSession>>` + 세션 ID 맵. JSON은 메시지당 한 번".
   - ping 행: "같은 `replayTaskScheduler`(poolSize 2)의 두 번째 주기 작업".
   - 느린 화면 행: "최악은 그 tick + 2초 × 느린 세션 수".
9. 8장 #13: "WS 허용 출처 `localhost:*`·`127.0.0.1:*` 적용(S3), REST는 S6". 8장 끝 문장: "출력 예시·어댑터 예시는 `server_s3_ws_plan.md` 7장".

## 10. TDD 단계
공통 (Git Bash, `server/`):
```bash
cd /c/Users/Woori/Desktop/project/Triple-Y/server
JAVA_HOME="/c/Program Files/Eclipse Adoptium/jdk-21.0.13.9-hotspot" ./gradlew test --tests '<패턴>' --no-daemon
```
> **에이전트는 `bootRun`을 실행하지 않는다** (포그라운드·백그라운드 모두). 확인은 `test`·`build`로 한다. RANDOM_PORT 통합 테스트는 임의 포트를 쓰고, 테스트 JVM이 끝날 때 닫힌다.

각 단계의 Red는 "테스트 먼저 작성 → 컴파일 실패 또는 단언 실패 확인"이다.

| 단계 | 할 일 (Red → Green) | `--tests` | 완료 조건 |
|---|---|---|---|
| 0 | 브랜치: `git switch main && git pull && git switch -c feat/server-ws-zone-state` | — | `git status --short`에 `?? CLAUDE.local.md`·`?? docs/plans/server_s3_ws_plan.md`만 있음 |
| 1 | `FrameTimestampsTest` → `FrameTimestamps` | `'com.tripley.crowdsight.ws.FrameTimestampsTest'` | 5메서드 통과 |
| 2 | `CrowdsightPropertiesTest` 수정·추가, `TestProperties`, `bindsDefaultWsSettings`, `clockUsesConfiguredZone`, `failsOnUnknownTimeZone` → `CrowdsightProperties`(timeZone·ws·cors), yml, `ClockConfig` | `'com.tripley.crowdsight.config.*'` 다음 `'com.tripley.crowdsight.CrowdsightServerApplicationIntegrationTest'`, `'com.tripley.crowdsight.TimelineStartupIntegrationTest'` | config 16메서드(21회), 앱 통합 5메서드, 시작 통합 4메서드 통과 |
| 3 | `ZoneRegistryTest` → `ZoneRegistry.find` | `'com.tripley.crowdsight.replay.ZoneRegistryTest'` | 1메서드 통과 |
| 4 | `MessageFactoryTest`, `MessageJsonTest` → `ws/message/*`, `MessageFactory` | `'com.tripley.crowdsight.ws.Message*'` | 13메서드(15회) 통과. 7장 예시와 트리가 같음 |
| 5 | `ZoneSessionsTest` → `ZoneSessions` | `'com.tripley.crowdsight.ws.ZoneSessionsTest'` | 10메서드 통과. `dropsWhenPingFindsStuckSend`를 5번 연속 실행해도 통과(`--rerun` 또는 반복 실행) |
| 6 | `ReplaySchedulerTest` 수정·추가 → `ZoneBroadcaster`, `ReplayScheduler.tickZone`, `WsZoneBroadcaster` | `'com.tripley.crowdsight.replay.*'` | replay 단위 통과(기존 2 + 신규 3 + 레지스트리 1) |
| 7 | `WsPingSchedulerTest` → `WsPingScheduler`, `ReplaySchedulerConfig` poolSize 2 | `'com.tripley.crowdsight.ws.WsPingSchedulerTest'` | 1메서드 통과 |
| 8 | `ZoneWebSocketHandlerTest`, `ZoneWebSocketIntegrationTest` → `ZoneWebSocketHandler`, `WebSocketConfig` | `'com.tripley.crowdsight.ws.ZoneWebSocket*'` | 핸들러 2메서드(5회), 통합 10메서드(11회) 통과 |
| 9 | 전체 실행. MOCK·NONE 환경 기존 테스트가 `@EnableWebSocket`과 함께 통과하는지 확인 | 없음 (`./gradlew test --no-daemon`) | 모든 테스트 통과. 실패하면 12장 위험 2행 대응 |
| 10 | README에 WebSocket 절 추가 (아래), `server_impl_plan.md` 9장 정정 | — | 문구만 |
| 11 | 전체 검증 (아래 표) | — | 모두 기대대로 |

README 추가 절 (실행 절 아래):
````markdown
## WebSocket (S3)
- 주소: `ws://localhost:8080/ws/zones/{zone_id}` (가짜 E04_039는 `zone-e04-039`). 없는 구역이면 닫기 코드 4404로 닫힌다.
- 접속하면 `hello` 1번, 이후 1초마다 `zone_state`, 반복으로 처음에 돌아오면 `playback`이 `zone_state` 앞에 온다 (`docs/api-spec.md` 3절).
- 허용 출처는 `crowdsight.cors-origin-patterns` (기본 `http://localhost:*`, `http://127.0.0.1:*`). 다른 사이트에서 연 콘솔은 403으로 거절된다.
- 확인 (화면 dev 서버 http://localhost:5173 의 개발자 도구 콘솔):
  ```js
  const ws = new WebSocket('ws://localhost:8080/ws/zones/zone-e04-039');
  ws.onmessage = (e) => console.log(JSON.parse(e.data));
  ws.onclose = (e) => console.log('닫힘', e.code, e.reason);
  ```
- 느린 화면: 메시지 하나 보내기가 2초(`crowdsight.ws.send-time-limit-ms`) 넘게 막히면 그 화면 연결만 닫는다. 화면은 재접속하면 `hello`부터 다시 받는다.
- 로그: 접속·끊김은 INFO `화면 접속 zone=… session=… 접속자=…`, 보내기 실패는 WARN `보내기 실패한 화면을 닫고 뺌`.
````

11단계 검증:

| # | 명령 | 기대 |
|---|---|---|
| 1 | `JAVA_HOME=… ./gradlew clean build --no-daemon` | `BUILD SUCCESSFUL` |
| 2 | `grep -h -o 'tests="[0-9]*" skipped="[0-9]*" failures="[0-9]*" errors="[0-9]*"' build/test-results/test/*.xml` | 모든 줄이 `failures="0" errors="0"` |
| 3 | `grep -rn 'springframework' src/main/java/com/tripley/crowdsight/grade` | 출력 없음 |
| 4 | `grep -rn 'crowdsight.ws' src/main/java/com/tripley/crowdsight/replay src/main/java/com/tripley/crowdsight/grade` | 출력 없음 (replay는 ws를 모름) |
| 5 | `grep -rnE 'Instant\.now\|currentTimeMillis\|ZonedDateTime\.now\(\)' src/main` | 출력 없음 (`ZonedDateTime.now(clock)`만) |
| 6 | `grep -rnE '@(Data\|Getter\|Setter\|Builder\|Value\|AllArgsConstructor\|NoArgsConstructor)\b' src` | 출력 없음 |
| 7 | `grep -rn 'com.fasterxml.jackson.databind' src` | 출력 없음 |
| 8 | `grep -rn 'org.apache.tomcat' src/main` | 출력 없음 (Tomcat 상수는 테스트만) |
| 9 | `grep -rnP '\t' src README.md` | 출력 없음 |
| 10 | 바뀐 `.java` 파일에 120자 초과 줄 없음 (문자 수 기준) | 출력 없음 |
| 11 | stage 뒤 `git -C .. ls-files --eol server \| grep -v 'i/lf'` | `gradle-wrapper.jar`, `gradlew.bat`만 |
| 12 | `git -C .. status --short` | `CLAUDE.local.md`가 stage되지 않음 |

커밋 제안:
1. `feat: 시간대·WebSocket 설정과 frame_ts 형식 추가` (`CrowdsightProperties`, yml, `ClockConfig`, `FrameTimestamps`, 테스트)
2. `feat: WebSocket hello·zone_state·playback 방송 (S3)` (메시지, `MessageFactory`, `ZoneSessions`, 핸들러, 설정, 방송·ping, `ReplayScheduler`, `ZoneRegistry.find`, 테스트)
3. `docs: S3 계획 추가, 구현 계획 정정, README WebSocket 설명`

## 11. PR 설명 (초안)
제목: `feat: WebSocket hello·zone_state·playback 방송 (S3)` / 기준 `main` ← `feat/server-ws-zone-state`

> **병합 순서**: S0(#42)·S1·S2(#45)는 `main`에 병합됨. 이 PR은 `main`을 기준으로 연다.

- 목적: 화면이 `/ws/zones/{zone_id}`로 접속하면 `hello`(meta·재생 상태·기준값)를 받고, 이후 1초마다 `zone_state`(구역·셀 등급과 측정값)를 받는다. 반복 재생 때는 `playback`이 먼저 온다. 느린 화면 하나가 재생과 다른 화면을 막지 않게 한다.
- 변경:
  - 설정 `crowdsight.time-zone`, `ws.*`(ping 30초, 차단 전송 2초, 버퍼 512KB), `cors-origin-patterns`. `ClockConfig`
  - `ws/`: `ZoneWebSocketHandler`(없는 구역 4404, 받은 메시지 무시), `ZoneSessions`(hello 뒤 추가, 한 번 만든 JSON 방송, 실패 세션 닫고 빼기, ping), `MessageFactory`, `FrameTimestamps`, `WsZoneBroadcaster`, `WsPingScheduler`, `message/` record 7개
  - `replay/`: `ZoneBroadcaster` 인터페이스, `ReplayScheduler`가 [playback] → zone_state를 보냄, `ZoneRegistry.find`
  - 재생 스케줄러 스레드 1 → 2 (재생, ping)
- S3에서 비워 둔 값: `zone.inflow_alert`는 늘 `false`(S4), `hello.thresholds`는 `density`만(S4), `hello.unacked_alerts`는 늘 `[]`(S5).
- 출력 예시 (fixture, 테스트가 같은지 확인함): `docs/plans/server_s3_ws_plan.md` 7.1~7.4의 `hello`, `zone_state` t0·t4, `playback`을 그대로 붙인다.
- 참고 결정: 결정 기록 1(Tomcat 차단 전송 2초), 결정 기록 2(허용 출처 패턴), api-spec 3.1·3.2·3.4·3.5, 조사 2.1·2.4.

> [!IMPORTANT]
> **CS 이슈**
> | **주제** | **내용** |
> |---|---|
> | **느린 소비자와 head-of-line blocking** | 재생 스레드 하나가 모든 화면에 차례로 보낸다. 한 화면이 받지 않으면 뒤 화면과 다음 tick이 기다린다. 메시지마다 Tomcat 차단 전송 제한 2초로 상한을 두고, 넘으면 그 세션만 닫는다. 최악은 tick + 2초 × 느린 세션 수다 |
> | **세션 동시 전송** | Tomcat 세션은 두 스레드가 동시에 보내면 `IllegalStateException`을 던진다. 재생과 ping 두 스레드가 보내므로 `ConcurrentWebSocketSessionDecorator`가 직렬화한다. 데코레이터 한도는 잠금을 못 얻은 스레드만 검사한다(jar 확인) |
> | **팬아웃 직렬화 1회** | 메시지당 JSON을 한 번만 만들고 같은 `TextMessage`를 모든 세션에 보낸다. 두 화면이 같은 tick에 같은 바이트를 받는다 |
> | **경쟁 조건: hello와 방송** | hello를 보낸 뒤 방송 집합에 넣는다. `zone_state`가 hello보다 먼저 가지 않는다. 대가로 그 사이 tick 1개를 놓칠 수 있다 |
> | **스레드 한정과 happens-before** | 스레드 2개 풀에서도 같은 주기 작업은 겹치지 않는다. 실행기 큐가 실행 사이의 가시성을 보장하므로 판정 상태에 잠금이 없다 |
> | **포트와 어댑터(의존 역전)** | replay가 `ZoneBroadcaster` 포트를 정의하고 ws가 구현한다. 패키지 순환이 없고, 재생 테스트는 기록용 가짜 방송기로 순서를 검사한다 |
> | **WebSocket 닫기 코드** | 4000~4999는 응용 전용이다. 핸드셰이크에서 거절하면 브라우저는 1006만 보므로, 열고 나서 4404로 닫아 이유를 알린다 |
> | **Origin 검사 (CSWSH)** | 브라우저 CORS는 WebSocket에 적용되지 않는다. 서버가 `Origin`을 패턴과 비교해 다른 사이트 페이지의 접속을 403으로 막는다 |
> | **keepalive ping** | 30초 ping으로 프록시·NAT의 유휴 끊김을 막고 죽은 연결을 찾는다. 브라우저는 pong을 자동으로 보낸다 |
> | **시계 주입** | `Clock` 빈 하나로 `frame_ts`를 만든다. 테스트는 `Clock.fixed`로 형식을 고정한다(밀리초 3자리, +09:00, 날짜 넘김) |

| 선택 | 대안 | 고른 이유 |
|---|---|---|
| Tomcat 세션 속성 `BLOCKING_SEND_TIMEOUT`(Long 2000) | 데코레이터 `sendTimeLimit`만 / 세션별 비동기 전송 | 데코레이터 한도는 혼자 보낼 때 검사되지 않는다. 비동기 전송은 시연 규모에 비해 복잡하다 (결정 기록 1) |
| 없는 구역은 열고 4404 닫기 | `HandshakeInterceptor`로 거절 | 화면이 이유(코드)를 받는다 |
| `ZoneBroadcaster`를 replay에 두고 ws가 구현 | `ZoneSessions`가 구현 / replay가 ws 직접 사용 | 패키지 순환을 막고, 전송과 메시지 생성을 나눈다 |
| `hello.thresholds`는 S3에서 `density`만 | 0.02·0.6을 코드에 / null | 값은 설정에만 둔다. 설정 키는 읽는 PR(S4)에서 추가한다 |
| `inflow_alert` false, `unacked_alerts` [] (키 유지) | 키 생략 | 화면 파서가 S4·S5에서 바뀌지 않는다 |
| ping을 같은 스케줄러의 두 번째 작업으로 | 별도 스케줄러 빈 | 빈 하나로 수명 관리. ping이 재생과 겹쳐야 데코레이터 한도가 동작한다 |
| 메시지 record에 `type` 성분 + 보조 생성자 | 클래스 수준 `@JsonTypeInfo` | 단순하고 키 순서가 `type`부터다 |
| `/ws/zones/*` + `UriTemplate` | 경로 변수를 `HandshakeInterceptor`로 속성에 넣기 | 클래스가 하나 줄고, 핸들러 안에서 바로 판단한다 |

리뷰 요청:
- `ZoneSessions.join` 순서(속성 → 감싸기 → hello → 추가 → isOpen 재확인)
- 실패 시 닫기 처리(Tomcat이 먼저 닫는 경우 포함)
- S3에서 비워 둔 세 값(`inflow_alert`, `thresholds`, `unacked_alerts`)
- `ZoneBroadcaster` 위치

남은 일:
- S4(유입 경보·불안정, thresholds 완성), S5(alert, `unacked_alerts`)
- 화면 어댑터(나예린, 7.5절)
- mock 서버 갱신 담당 `[토론]`
- 실제 느린 화면 수동 시험 `[토론]`

## 12. 위험·가정·`[토론]`
| 위험 | 대응 |
|---|---|
| 제한 시간이 넘으면 Tomcat이 먼저 `GOING_AWAY`로 닫는다. 화면이 받는 코드는 4500이 아니라 1001·1006일 수 있다 | 화면은 코드와 상관없이 재접속한다(4404만 예외). 우리 `close` 실패는 무시하고 집합에서는 반드시 뺀다 |
| `@EnableWebSocket`이 MOCK(`@SpringBootTest` 기본)·NONE(`TimelineStartupIntegrationTest`) 환경에서 뜨지 않음 | 9단계에서 전체 실행으로 확인한다. 실패하면 `WebSocketConfig`에 `@ConditionalOnWebApplication(type = SERVLET)`을 붙인다 (확인 필요) |
| 실제 Tomcat 차단 2초 동작은 자동 시험하지 않는다 (받지 않는 클라이언트를 만들려면 OS 소켓 버퍼를 채워야 해 느리고 불안정하다) | 속성이 실제 Tomcat 세션에 `Long 2000`으로 걸렸는지(통합), Tomcat이 그 값을 읽는지(jar), 실패 시 처리(mock)를 따로 확인한다 |
| `buffer-size-limit-bytes`(512KB)는 ping이 겹칠 때만 검사된다. api-spec 3.5 "쌓인 메시지가 512KB를 넘어도 닫는다"와 다르게 읽힌다 | 실제 보호는 2초 제한이다. api-spec 문구는 D1에서 고친다 `[토론]` |
| 느린 세션이 여러 개면 재생이 2초 × n 늦어지고, fixed-rate가 따라잡으며 연달아 tick한다 | 시연은 같은 PC 화면 1~2개다(가정). 처리 시간 last·max는 S7 `/api/health` |
| `dropsWhenPingFindsStuckSend`가 시간에 의존한다 | `getTimeSinceSendStarted()`를 Awaitility로 기다려 시간 조건을 직접 확인한다. 5단계에서 반복 실행 |
| 통합 테스트(100 ms, 5초 fixture)에서 접속 시점이 반복과 겹치면 첫 메시지가 `playback`일 수 있다 | 첫 zone_state 앞은 검사하지 않는다 |
| Jackson이 record 키 순서를 바꿈 | 테스트는 트리 비교(순서 무시)다. `startsWith` 한 줄만 순서를 본다. 실패하면 그 단언만 뺀다 |
| `PingMessage`를 세션끼리 공유하면 `ByteBuffer` 위치가 바뀜 | 세션마다 새로 만든다 |

가정:
- (가정) 접속과 tick이 겹치면 hello 뒤 첫 `zone_state`가 `hello.playback.t + 1`이 아닐 수 있다. 1개를 건너뛸 수 있다.
- (가정) `Origin` 헤더가 없는 클라이언트(도구·테스트)는 허용한다(Spring 기본). 운영은 같은 출처 배포.
- (가정) 화면은 바이너리를 보내지 않는다. 보내면 1003으로 닫힌다(`TextWebSocketHandler` 기본).
- (가정) `frame_ts`는 구역·tick마다 1번 만들고 같은 tick 메시지가 공유한다. `playback`에는 없다(api-spec 3.4).
- (가정) `time-zone`을 UTC로 바꾸면 `frame_ts` 오프셋은 `Z`다. api-spec 예시는 `+09:00`이다.

`[토론]`:

| # | 안건 | 누구와 |
|---|---|---|
| 1 | `liveFeed.ts`가 `hello`·`zone_state`·`playback`(·S5 `alert`)을 받고 모르는 type은 무시. 7.5절 어댑터 예시 | 나예린 |
| 2 | 반복 신호 `playback{playing, t:0}`을 받으면 쌓은 프레임 비우기 (mock은 `timeline` 재전송 방식) | 나예린 |
| 3 | 닫기 코드 4404면 재접속을 멈추고 오류 표시. 재접속 최대 간격 15초 → 5초 | 나예린 |
| 4 | 등급은 서버 `grade`·`grade_pred_60s` 사용, 표기 "경고" → "경계" | 나예린 |
| 5 | S3의 `inflow_alert` false·`thresholds` density만·`unacked_alerts` []를 화면이 "아직 없음"으로 다룰지 | 나예린 |
| 6 | `VITE_WS_URL=ws://localhost:8080/ws/zones/zone-e04-039`, 서버 허용 출처로 충분한지(Vite 프록시 불필요) | 나예린 |
| 7 | mock 서버(8787)를 새 형식으로 갱신할지, 11-13부터 실제 서버만 쓸지 | 나예린 |
| 8 | `frame_ts`와 수신 시각 차이 기록(E8) 방식: 콘솔 vs CSV | 나예린, 이유노 |
| 9 | api-spec 3.5의 512KB 문구를 "ping과 겹칠 때만 검사, 실제 보호는 2초 제한"으로 고치기 (D1) | 조영준 |
| 10 | 실제 느린 화면 수동 시험(시연 PC에서 탭 일시정지 등)을 G2 전에 할지 | 조영준 |

---

### Critical Files for Implementation
- C:\Users\Woori\Desktop\project\Triple-Y\server\src\main\java\com\tripley\crowdsight\replay\ReplayScheduler.java
- C:\Users\Woori\Desktop\project\Triple-Y\server\src\main\java\com\tripley\crowdsight\config\CrowdsightProperties.java
- C:\Users\Woori\Desktop\project\Triple-Y\server\src\main\java\com\tripley\crowdsight\replay\ZoneRegistry.java
- C:\Users\Woori\Desktop\project\Triple-Y\server\src\test\java\com\tripley\crowdsight\config\TestProperties.java
- C:\Users\Woori\Desktop\project\Triple-Y\server\src\main\resources\application.yml
