# 서버 S3 리뷰 반영 계획 (`feat/server-ws-zone-state`, PR #47)

| 항목 | 내용 |
|---|---|
| 작성일 | 2026-11-13 |
| 기준 | `docs/plans/server_s3_ws_plan.md`(1장 결정 7·8·9, 2.3 스레드 규칙, 5.1·5.5, 6.6), PR #47 코드 리뷰 3건, CLAUDE.md `server/` 규칙(DTO·상태 클래스 `final`, 로그) |
| 대상 | `server/src/main/java/com/tripley/crowdsight/ws/ZoneSessions.java`, `ws/WsPingScheduler.java`, `server/src/test/java/com/tripley/crowdsight/ws/ZoneSessionsTest.java` |
| 범위 | (1) `join` 경쟁으로 닫힌 세션이 `byZone`에 남는 문제, (2) `drop`이 두 스레드에서 겹치면 WARN·닫기가 두 번 나는 문제, (3) `WsPingScheduler` `final`·스레드 규칙 Javadoc. **동작·메시지·설정 변경 없음** |
| 상태 | 계획. 사용자 승인(2026-11-13) |

## 0. 확인한 사실 (코드·jar로 확인)
- `ZoneSessions.join` (52-70행) 순서: 속성 → 감싸기 → hello → `bySessionId.put(raw.getId(), Member)`(63) → `byZone…add(session)`(64) → `if (!raw.isOpen()) leave(raw)`(65-67).
- `leave` (73-84행): `bySessionId.remove(id)`가 null이면 바로 끝난다. 아니면 `byZone.get(zoneId).remove(member.session())`.
- 호출 스레드: `join`은 `afterConnectionEstablished`, `leave`는 `afterConnectionClosed`·`handleTransportError`(`ZoneWebSocketHandler` 58-65행). 둘 다 Tomcat 스레드지만 서로 다른 스레드일 수 있다. `afterConnectionClosed`가 불릴 때 `raw.isOpen()`은 이미 거짓이다.
- `byZone`의 구역 Set은 한 번 만들면 지우지 않는다. 그래서 `join`이 받은 Set 참조는 끝까지 맵 안의 그 Set이다.
- `drop` (131-139행): `targets.remove(session)`의 결과를 보지 않고 WARN 로그와 `closeQuietly`를 한다.
- `ConcurrentWebSocketSessionDecorator.close` (spring-websocket 7.0.10, javap): `closeLock.tryLock()` 뒤 `closeInProgress`이면 바로 return. 그래서 **raw `close`는 지금도 한 번만 불린다**. 겹쳐서 보이는 것은 WARN 로그 2줄과 불필요한 닫기 시도다.
- 이중 `drop` 경로: 재생 스레드가 막힌 전송에 걸린 동안 ping 스레드가 한도 초과(`SessionLimitExceededException`)로 `drop` → 이후 막힌 전송이 `IOException`(Tomcat 차단 제한)으로 끝나면 재생 스레드도 `drop`.
- `WsPingScheduler` (23행)는 `public class`다. 상태 필드 `volatile ScheduledFuture<?> future`가 있다.
  - mock·상속하는 곳이 없다. `WsPingSchedulerTest`는 `new WsPingScheduler(…)`로 직접 만든다.
  - AOP(`@Aspect`·`@Transactional`·`@Async`)가 `src/main`에 없어 CGLIB 프록시가 생기지 않는다.
  - `ZoneSessions`가 이미 `final`이고 테스트에서 `mock(ZoneSessions.class)`가 된다. Mockito 5.23.0 기본 inline mock maker다.
- 테스트 classpath에 logback-classic이 있다 (`spring-boot-starter-webmvc` → `spring-boot-starter-logging`).

## 1. 결정
| # | 항목 | 결정 | 이유 |
|---|---|---|---|
| 1 | `join` 경쟁 | `!raw.isOpen()` 분기에서 `leave(raw)`를 부르지 않고 **두 맵에서 직접 뺀다**: `targets.remove(session)`, `bySessionId.remove(id, member)`. 그 뒤 INFO "화면 접속 끊김" 로그 | 아래 표처럼 모든 순서에서 남는 세션이 없다. `leave`의 내부 순서에 기대지 않는다. 바꾸는 곳이 분기 하나다 |
| 2 | `drop` 중복 | `if (targets == null \|\| !targets.remove(session)) return;`를 로그·닫기 앞에 둔다. `bySessionId.remove(session.getId())`는 그 뒤로 옮긴다 | `Set.remove`의 참 결과는 한 스레드만 얻는다. 이미 `leave`가 뺀 세션은 끊기는 중이라 우리가 닫을 필요가 없다 |
| 3 | `WsPingScheduler` | `public final class`. Javadoc에 스레드 규칙 1줄 | CLAUDE.md "상태가 있는 클래스는 final, 스레드 규칙을 Javadoc에" |
| 4 | 대안 (채택 안 함) | 두 put 순서 바꾸기(`byZone` 먼저) | 이것도 맞지만 `leave`가 `bySessionId`를 먼저 지운다는 순서에 숨은 의존이 생긴다. 1번이 더 읽기 쉽다 |

결정 1의 순서 검토 (J1=`bySessionId.put`, J2=`byZone add`, J3=`isOpen` 검사, L=`leave` 전체. 닫힘은 L보다 먼저):

| L의 위치 | 지금 코드 | 바꾼 코드 |
|---|---|---|
| J1 앞 | L은 아무것도 못 찾음. J3 거짓 → `leave`가 둘 다 뺌. 정상 | J3 거짓 → 직접 둘 다 뺌. 정상 |
| J1과 J2 사이 | L이 `bySessionId`만 뺌. J2가 추가. J3 거짓 → `leave` 조기 return → **`byZone`에 남음** | J3 거짓 → `byZone`에서 직접 뺌. 정상 |
| L의 `bySessionId.remove`는 J1 뒤, `byZone.remove`는 J2 뒤 | L이 둘 다 뺌. 정상 | 정상 (제거는 몇 번 해도 같다) |
| J2 뒤 (J3 앞·뒤) | L이 둘 다 뺌. 정상 | 정상 |
| 닫힘이 J3 뒤 | J3 참. 나중 L이 둘 다 뺌. 정상 | 같음 |

## 2. 코드 변경

### 2.1 `ws/ZoneSessions.java` — `join` (결정 1)
Before (63-69행):
```java
        bySessionId.put(raw.getId(), new Member(zoneId, session));
        byZone.computeIfAbsent(zoneId, k -> ConcurrentHashMap.newKeySet()).add(session);
        if (!raw.isOpen()) {
            leave(raw);
            return;
        }
        log.info("화면 접속 zone={} session={} 접속자={}", zoneId, raw.getId(), sessionCount(zoneId));
```
After:
```java
        Member member = new Member(zoneId, session);
        bySessionId.put(raw.getId(), member);
        Set<WebSocketSession> targets = byZone.computeIfAbsent(zoneId, k -> ConcurrentHashMap.newKeySet());
        targets.add(session);
        if (!raw.isOpen()) {     // 그 사이 끊김. leave가 bySessionId만 먼저 지웠을 수 있어 두 맵에서 직접 뺀다
            targets.remove(session);
            bySessionId.remove(raw.getId(), member);
            log.info("화면 접속 끊김 zone={} session={} 접속자={}", zoneId, raw.getId(), sessionCount(zoneId));
            return;
        }
        log.info("화면 접속 zone={} session={} 접속자={}", zoneId, raw.getId(), sessionCount(zoneId));
```
- 메서드 Javadoc 둘째 줄 "그 사이 끊겼으면 다시 뺀다"는 그대로 둔다.

### 2.2 `ws/ZoneSessions.java` — `drop` (결정 2)
Before (131-139행):
```java
    private void drop(String zoneId, WebSocketSession session, Exception cause) {
        Set<WebSocketSession> targets = byZone.get(zoneId);
        if (targets != null) {
            targets.remove(session);
        }
        bySessionId.remove(session.getId());
        log.warn("보내기 실패한 화면을 닫고 뺌 zone={} session={} 원인={}", zoneId, session.getId(), cause.toString());
        closeQuietly(session);
    }
```
After:
```java
    /** 실패한 세션을 빼고 닫는다. 두 스레드(재생·ping)가 같이 불러도 뺀 스레드 하나만 로그를 남기고 닫는다. */
    private void drop(String zoneId, WebSocketSession session, Exception cause) {
        Set<WebSocketSession> targets = byZone.get(zoneId);
        if (targets == null || !targets.remove(session)) {
            return;     // 다른 스레드의 drop이나 leave가 이미 뺐다
        }
        bySessionId.remove(session.getId());
        log.warn("보내기 실패한 화면을 닫고 뺌 zone={} session={} 원인={}", zoneId, session.getId(), cause.toString());
        closeQuietly(session);
    }
```

### 2.3 `ws/WsPingScheduler.java` (결정 3)
```java
/**
 * ping-interval-ms마다 모든 화면에 ping을 보낸다 (api-spec 3.5).
 * 재생과 같은 replayTaskScheduler(스레드 2개)의 두 번째 주기 작업이다.
 * SmartLifecycle 기본 phase라 웹 서버가 뜬 뒤 시작하고 닫을 때 먼저 멈춘다.
 * 스레드 규칙: start·stop·isRunning은 Spring 생명주기 스레드, pingAll은 스케줄러 스레드가 부른다. future는 volatile이다.
 */
@Slf4j
@Component
@RequiredArgsConstructor
public final class WsPingScheduler implements SmartLifecycle {
```
- 본문은 바꾸지 않는다.

## 3. 테스트 (`ws/ZoneSessionsTest`에 추가)

### 3.1 `leaveRacingJoinLeavesNoSession` — 결정 1
- **결정적 재현이 안 되는 이유**: J1과 J2 사이에 mock을 거치는 호출이 없다. `getId()`는 J1 앞, `isOpen()`은 J2 뒤, hello 전송은 J1 앞이다. hello 답에서 `leave`를 부르면 "J1 앞" 경우라 지금 코드도 통과한다(Red가 안 된다). 테스트용 훅을 넣는 것은 리뷰 범위를 넘는다.
- 그래서 **반복 경쟁 테스트**로 한다. 닫힌 세션(`isOpen` 거짓)을 한 스레드가 `join`하는 동안 다른 스레드가 `leave`를 계속 부른다.

```java
    @Test
    @DisplayName("join 도중 다른 스레드가 leave해도 닫힌 세션이 남지 않는다")
    void leaveRacingJoinLeavesNoSession() throws Exception {
        ExecutorService closer = Executors.newSingleThreadExecutor();
        try {
            for (int i = 0; i < 2000; i++) {
                ZoneSessions fresh = new ZoneSessions(TestProperties.ws(TestProperties.WS));
                WebSocketSession raw = session("r" + i);
                when(raw.isOpen()).thenReturn(false);       // afterConnectionClosed 때는 이미 닫혀 있다
                AtomicBoolean joined = new AtomicBoolean();
                Future<?> leaving = closer.submit(() -> {
                    while (!joined.get()) {
                        fresh.leave(raw);
                    }
                });

                fresh.join("zone-test", raw, "hello");
                joined.set(true);
                leaving.get(2, TimeUnit.SECONDS);

                assertThat(fresh.sessionCount()).as("반복 %d", i).isZero();
            }
        } finally {
            closer.shutdownNow();
        }
    }
```
- import 추가: `java.util.concurrent.atomic.AtomicBoolean`.
- Red: 지금 코드에서 2000번 안에 한 번 이상 `sessionCount() == 1`이 나와야 한다. **Red가 안 나오면** 반복을 10000으로 올려 한 번 더 본다. 그래도 안 나오면 TDD 에이전트는 그 사실을 보고하고, 이 테스트는 회귀 방지로 두고 Green으로 넘어간다(코드 변경 근거는 1장 순서 표).
- Green: 바꾼 코드는 J3에서 무조건 두 맵을 비우므로 모든 반복에서 0이다.
- 시간: mock 호출 수 μs × 반복 2000. 1초 안쪽을 예상한다.

### 3.2 `pingAndReplayDropLogsOnce` — 결정 2
기존 `dropsWhenPingFindsStuckSend`(132-163행)와 같은 틀이다. 막힌 전송이 풀릴 때 `IOException`을 던지게 해 두 스레드가 모두 `drop`에 들어가게 한다. WARN 수는 logback `ListAppender`로 센다.

```java
    @Test
    @DisplayName("ping과 재생이 같은 세션을 함께 버려도 WARN과 닫기는 한 번이다")
    void pingAndReplayDropLogsOnce() throws Exception {
        ZoneSessions limited = new ZoneSessions(TestProperties.ws(new CrowdsightProperties.Ws(30000, 50, 524288)));
        WebSocketSession a = session("a");
        CountDownLatch release = new CountDownLatch(1);
        AtomicInteger calls = new AtomicInteger();
        doAnswer(invocation -> {
            if (calls.incrementAndGet() == 2) {         // 첫 방송에서 멈췄다가 Tomcat 차단 제한처럼 실패한다
                release.await(5, TimeUnit.SECONDS);
                throw new IOException("차단 전송 제한 초과");
            }
            return null;
        }).when(a).sendMessage(any());
        limited.join("zone-test", a, "hello");
        ConcurrentWebSocketSessionDecorator decorated =
                (ConcurrentWebSocketSessionDecorator) limited.sessions("zone-test").get(0);
        Logger logger = (Logger) LoggerFactory.getLogger(ZoneSessions.class);
        ListAppender<ILoggingEvent> logs = new ListAppender<>();
        logs.start();
        logger.addAppender(logs);
        ExecutorService replayThread = Executors.newSingleThreadExecutor();
        try {
            Future<?> stuck = replayThread.submit(() -> limited.broadcast("zone-test", "zs"));
            await().atMost(Duration.ofSeconds(2)).until(() -> decorated.getTimeSinceSendStarted() > 50);

            limited.pingAll();                          // ping 스레드 drop
            release.countDown();                        // 재생 스레드 drop
            stuck.get(2, TimeUnit.SECONDS);

            assertThat(logs.list).filteredOn(e -> e.getLevel() == Level.WARN).hasSize(1);
            verify(a, times(1)).close(CloseStatus.SESSION_NOT_RELIABLE);
            assertThat(limited.sessionCount()).isZero();
        } finally {
            release.countDown();
            replayThread.shutdownNow();
            logger.detachAppender(logs);
        }
    }
```
- import 추가: `ch.qos.logback.classic.Level`, `ch.qos.logback.classic.Logger`, `ch.qos.logback.classic.spi.ILoggingEvent`, `ch.qos.logback.core.read.ListAppender`, `org.slf4j.LoggerFactory`.
- Red: 지금 코드는 WARN이 2개다. `close` 1회 검증은 지금도 통과한다(0장, 데코레이터 `closeInProgress`). 그래서 실패 원인은 WARN 수다.
- `broadcast`는 예외를 `send`에서 잡으므로 `stuck.get`은 예외 없이 끝난다.

### 3.3 `WsPingScheduler`
- 새 테스트 없음. 컴파일과 기존 `WsPingSchedulerTest`, 통합 테스트(Spring이 `final` 빈을 만드는지)로 확인한다.

## 4. TDD 단계
공통 (Git Bash):
```bash
cd /c/Users/Woori/Desktop/project/Triple-Y/server && JAVA_HOME="/c/Program Files/Eclipse Adoptium/jdk-21.0.13.9-hotspot" ./gradlew test --tests '<패턴>' --no-daemon
```
> 에이전트는 `bootRun`을 실행하지 않는다.

| 단계 | 할 일 (Red → Green) | `--tests` | 완료 조건 |
|---|---|---|---|
| 1 | 3.1 테스트 추가 → Red 확인(3.1의 Red 규칙) → 2.1 수정 | `'com.tripley.crowdsight.ws.ZoneSessionsTest'` | 11메서드 통과 |
| 2 | 3.2 테스트 추가 → Red(WARN 2개) → 2.2 수정 | `'com.tripley.crowdsight.ws.ZoneSessionsTest'` | 12메서드 통과. `--rerun`으로 5번 연속 통과 |
| 3 | 2.3 수정 | `'com.tripley.crowdsight.ws.WsPingSchedulerTest'`, 다음 `'com.tripley.crowdsight.ws.ZoneWebSocketIntegrationTest'` | 통과 |
| 4 | 전체 실행 | 없음 (`./gradlew test --no-daemon`) | 모든 테스트 통과 |

## 5. 커밋
```
fix: S3 리뷰 반영 (join 경쟁·drop 중복·WsPingScheduler final)

- join: 닫힌 세션을 leave 대신 두 맵에서 직접 빼 경쟁 시 남지 않게 함
- drop: Set에서 뺀 스레드만 WARN 로그와 닫기를 함
- WsPingScheduler: final, 스레드 규칙 Javadoc

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```
- stage 대상: 위 3개 파일과 이 계획 문서. `CLAUDE.local.md`는 stage하지 않는다.

## 6. 위험·가정
| 위험 | 대응 |
|---|---|
| 3.1이 지금 코드에서 Red를 못 낼 수 있다 (창이 수십 ns) | 반복을 늘려 본다. 그래도 안 되면 보고하고 회귀 방지 테스트로 둔다. 근거는 1장 순서 표 |
| `handleTransportError`의 `leave`가 J1과 J2 사이에 오고 J3에서 `isOpen`이 아직 참이면, 세션이 `byZone`에 남는다 | 남은 세션은 다음 `broadcast`·`pingAll`에서 보내기가 실패해 `drop`이 뺀다(최대 1 tick). 이번 범위에서 고치지 않는다 |
| `drop`에서 `leave`가 먼저 뺀 세션은 닫지 않는다 | `leave`는 닫힘·전송 오류 때만 불린다. 그 세션은 Tomcat이 닫는 중이다 |
| `ListAppender`가 logback 구현에 의존한다 | Boot 기본 로깅이 logback이다. 로깅 구현을 바꾸면 이 테스트도 고친다 |
| `final` 빈에 나중에 AOP가 붙으면 CGLIB 프록시가 실패한다 | 지금은 AOP가 없다. 붙일 때 `final`을 다시 검토한다 |

## 2차 리뷰 반영 (2026-11-13)

| 항목 | 내용 |
|---|---|
| 기준 | PR #47 2차 리뷰 2건 (minor 1, nit 1), HEAD `6a2be4c` |
| 대상 | `server/src/main/java/com/tripley/crowdsight/ws/ZoneSessions.java`, `server/src/test/java/com/tripley/crowdsight/ws/ZoneSessionsTest.java` |
| 범위 | (A) 경쟁 테스트의 `leave` 스레드가 `join` 예외 때 끝나지 않는 문제, (B) `join` J3 분기에서 "화면 접속 끊김" INFO가 두 번 나는 문제. **동작·메시지·설정 변경 없음** |

### 7.0 확인한 사실 (코드로 확인)
- `ZoneSessionsTest.leaveRacingJoinLeavesNoSession` (236-259행): `leave` 루프는 `while (!joined.get())`만 본다. `joined.set(true)`(251)는 `fresh.join(...)`(250) 다음 줄이다. `join`이 던지면 `joined`가 영영 거짓이다. 루프는 인터럽트를 보지 않아 `closer.shutdownNow()`(257)로 멈추지 않는다. `newSingleThreadExecutor`의 스레드는 데몬이 아니다. 매 반복 `raw.getId()` 호출이 mock 호출 목록에 쌓인다.
- `join`이 던질 수 있는 곳: `TestProperties`·mock 설정 실수, 뒤에 `join`을 고치다 생긴 버그. 지금 Green에서는 안 생긴다. 실패할 때만 드러나는 문제다.
- `join`(52-74행)에서 raw의 `isOpen()`을 부르는 곳은 67행(J3) 하나다. `setBlockingSendTimeout`은 `getId()`·`getClass()`만, 데코레이터 `sendMessage`는 raw `sendMessage`만 부른다. `leave`·`sessionCount`도 `isOpen()`을 부르지 않는다. 그래서 `isOpen()` 답 안에서 `leave`를 부르면 **J2 뒤·J3 판정 앞**에 `leave` 전체가 들어간다(결정적).
- 지금 코드에서 그 순서면: `leave`가 두 맵에서 빼고 "끊김" INFO → J3 분기가 `targets.remove`·`bySessionId.remove(id, member)`(둘 다 false) 뒤 또 "끊김" INFO. **2줄**.
- `leave`는 `bySessionId.remove(id)`로 Member를 얻었을 때만 로그를 남긴다(78-87행).

### 7.1 결정
| # | 항목 | 결정 | 이유 |
|---|---|---|---|
| A | 경쟁 테스트 스레드 | `fresh.join(...)`을 `try { } finally { joined.set(true); }`로 감싼다. 루프 조건의 인터럽트 검사는 넣지 않는다 | 멈추지 않는 원인은 `joined`가 안 켜지는 경로 하나다. `finally`가 그 경로를 막는다. `join`이 정상 반환하든 던지든 `leave` 루프가 끝난다. 한 곳만 바꾼다 |
| B | J3 끊김 로그 | `targets.remove(session)`은 그대로 무조건 부른다. 로그 조건을 **`bySessionId.remove(raw.getId(), member)`가 참일 때**로 한다 | 아래 표. 리뷰 제안(`targets.remove` 결과)은 L이 J1과 J2 사이일 때 2줄이 남는다. `bySessionId`의 Member를 뺀 쪽이 로그를 남기면 `leave`와 같은 기준이라 모든 순서에서 1줄이다 |

B의 순서 검토 (J1=`bySessionId.put`, J2=`targets.add`, J3=`isOpen` 판정, L=`leave` 전체. 두 맵 정리는 1장 표와 같다: J3 분기는 두 맵 제거를 계속 무조건 부른다):

| L의 위치 | `leave` 로그 | J3 로그 (`targets.remove` 조건, 리뷰안) | J3 로그 (`bySessionId.remove` 조건, 채택) | 두 맵 |
|---|---|---|---|---|
| J1 앞 | 없음 (Member 없음) | 1 | 1 | 비움 |
| J1과 J2 사이 | 1 | 1 → **2줄** | 0 → 1줄 | 비움 |
| L의 두 remove가 J1 뒤·J2 뒤로 갈림 | 1 | 0 | 0 | 비움 |
| J2 뒤, J3 앞 | 1 | 0 | 0 | 비움 |
| 닫힘이 J3 뒤 | 나중 1 ("접속" 1 + "끊김" 1) | — | — | 나중 L이 비움 |

### 7.2 코드 변경 — `ws/ZoneSessions.java` `join` (결정 B)
Before (67-72행):
```java
        if (!raw.isOpen()) {     // 그 사이 끊김. leave가 bySessionId만 먼저 지웠을 수 있어 두 맵에서 직접 뺀다
            targets.remove(session);
            bySessionId.remove(raw.getId(), member);
            log.info("화면 접속 끊김 zone={} session={} 접속자={}", zoneId, raw.getId(), sessionCount(zoneId));
            return;
        }
```
After:
```java
        if (!raw.isOpen()) {     // 그 사이 끊김. leave가 bySessionId만 먼저 지웠을 수 있어 두 맵에서 직접 뺀다
            targets.remove(session);
            if (bySessionId.remove(raw.getId(), member)) {     // Member를 뺀 쪽만 로그 (leave가 뺐으면 leave가 남겼다)
                log.info("화면 접속 끊김 zone={} session={} 접속자={}", zoneId, raw.getId(), sessionCount(zoneId));
            }
            return;
        }
```

### 7.3 테스트 변경 — `ZoneSessionsTest`
(A) `leaveRacingJoinLeavesNoSession` 250-252행만 바꾼다:
```java
                try {
                    fresh.join("zone-test", raw, "hello");
                } finally {
                    joined.set(true);                       // join이 던져도 leave 스레드를 끝낸다
                }
                leaving.get(2, TimeUnit.SECONDS);
```
- 새 테스트 없음. 확인: 이 테스트와 클래스 전체가 그대로 통과하고 `--rerun` 5번 연속 통과.

(B) 새 테스트 `leaveBetweenAddAndOpenCheckLogsOnce` (`leaveRacingJoinLeavesNoSession` 바로 뒤):
```java
    @Test
    @DisplayName("join의 열림 검사 직전에 leave가 끼어도 끊김 로그는 한 번이다")
    void leaveBetweenAddAndOpenCheckLogsOnce() {
        WebSocketSession a = session("a");
        doAnswer(invocation -> {
            sessions.leave(a);                          // J2 뒤·J3 판정 앞에 leave 전체가 들어간다
            return false;
        }).when(a).isOpen();
        Logger logger = (Logger) LoggerFactory.getLogger(ZoneSessions.class);
        ListAppender<ILoggingEvent> logs = new ListAppender<>();
        logs.start();
        logger.addAppender(logs);
        try {
            sessions.join("zone-test", a, "hello");

            assertThat(logs.list)
                    .filteredOn(e -> e.getLevel() == Level.INFO
                            && e.getFormattedMessage().startsWith("화면 접속 끊김"))
                    .hasSize(1);
            assertThat(sessions.sessionCount()).isZero();
        } finally {
            logger.detachAppender(logs);
        }
    }
```
- import 추가 없음 (모두 이미 있다).
- `session()`의 `when(isOpen()).thenReturn(true)`를 `doAnswer`가 덮는다. mock 세션이라 `setBlockingSendTimeout`이 WARN을 남기므로 INFO·메시지로 거른다.
- Red: 지금 코드는 2줄. Green: 1줄. `sessionCount() == 0`은 지금도 통과한다(두 맵 정리는 1차에서 고쳤다).

### 7.4 TDD 단계
공통 명령은 4장과 같다. `bootRun`은 실행하지 않는다.

| 단계 | 할 일 | `--tests` | 완료 조건 |
|---|---|---|---|
| 1 | 7.3(B) 테스트 추가 → Red(끊김 INFO 2줄) → 7.2 수정 → Green | `'com.tripley.crowdsight.ws.ZoneSessionsTest'` | 13메서드 통과 |
| 2 | 7.3(A) 수정 | `'com.tripley.crowdsight.ws.ZoneSessionsTest'` | 13메서드 통과. `--rerun`으로 5번 연속 통과 |
| 3 | 전체 실행 | 없음 (`./gradlew test --no-daemon`) | 모든 테스트 통과 |

### 7.5 커밋
```
fix: S3 2차 리뷰 반영 (join 끊김 로그 중복·경쟁 테스트 스레드 종료)

- join: 끊김 분기에서 bySessionId의 Member를 뺀 경우에만 로그를 남김
- ZoneSessionsTest: join이 던져도 leave 루프가 끝나게 finally로 joined 설정

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```
- stage 대상: 위 2개 파일과 이 계획 문서. `CLAUDE.local.md`는 stage하지 않는다.

### 7.6 위험·가정
| 위험 | 대응 |
|---|---|
| 답(answer) 안에서 같은 mock의 `getId()`를 부른다 | Mockito는 답 안의 다른 메서드 호출을 허용한다. 스텁된 `getId()`가 "a"를 준다 |
| 나중에 `join`이 J3 앞에서 `isOpen()`을 더 부르면 7.3(B)가 다른 순서를 재현한다 | 그때 답에 "첫 호출에서만 leave" 조건을 넣는다. 지금은 J3 하나뿐이다(7.0) |
| (A)의 루프는 여전히 인터럽트를 보지 않는다 | `joined`가 켜지지 않는 경로가 `finally`로 없어졌다. 인터럽트 검사는 쓰지 않는 방어라 넣지 않는다 |
| 로그 조건이 `bySessionId` 결과에 의존한다 | `leave`도 같은 결과로 로그를 정한다. 두 곳의 기준이 같아 한쪽만 남긴다 |
