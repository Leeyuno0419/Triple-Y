# 서버 S7 구역 조회와 서버 상태 구현 계획 (`feat/server-zones-health`)

| 항목 | 내용 |
|---|---|
| 작성일 | 2026-11-16 |
| 기준 | 사용자 결정(11-16): **영상 = 실시간 CCTV 흉내. 화면이 재생을 제어하지 않는다.** `docs/plans/server_impl_plan.md`(1.1 `api/ZoneController, HealthController`, 2장 S7, 5장 "p95 ≤ 5초" 행의 tick 처리 시간 last·max·WARN), `docs/api-spec.md` v0.2(2절 엔드포인트, 3.4 `playback`, 4.2 초기화, 4.5 오류 본문 `[토론]`, 5절 재생 제어, 6절, 8절, 10절), `docs/plans/server_s3_ws_plan.md`(위험 표 "처리 시간 last·max는 S7", `/api/health`에 `sessionCount()`), CLAUDE.md(서버 규칙: `Clock`, 경과 시간만 `System.nanoTime()`, 설정은 `crowdsight.*` 한 곳, API에 처음부터 `zone_id`·`camera_id`) |
| 대상 | `server/` (`feat/server-alert-ack`(S6, PR #51, `d5281e3`) 위 브랜치, **PR 기준 `main`**), `docs/plans/`, `docs/api-spec.md`, `server/README.md` |
| 범위 | `GET /api/zones`(카메라·구역 목록), `GET /api/zones/{zone_id}/meta`, `GET /api/health`(구역 재생 상태·접속 수·tick 처리 시간), `replay/TickStats`, 설정 `crowdsight.replay.slow-tick-ms`(느린 tick WARN). 쓰지 않게 된 `PlaybackState.PAUSED` 삭제(확정), 재생 제어를 전제한 주석·문서 정리. **재생 제어 REST 없음, WS 메시지 키 변경 없음, ProblemDetail 설정 없음, 인증 없음** |
| 상태 | 계획 v2. 사용자 점검 완료(11-16), 결정 1~3 추천안 확정 → TDD |
| 대체 | `docs/plans/server_s7_playback_api_plan.md`(v1, 재생 제어 포함)를 대체한다. v1은 커밋 전이라 삭제한다(16장 변경 이력) |

## 0. 확인한 사실 (코드·문서·grep으로 확인)
- 작업 트리:
  - 브랜치 `feat/server-playback-api`, HEAD `d5281e3`(= `feat/server-alert-ack` 끝). `main` `3ce4601` 위에 S5 커밋 2개(`efe29ff`, `755c880`)와 S6 커밋 3개(`be6ec26`, `2c8f6ad`, `d5281e3`).
  - 원격에 `feat/server-playback-api`·`feat/server-zones-health` 브랜치가 없다(`git ls-remote --heads origin` 0건). 그래서 이름을 바꿔도 원격 정리가 필요 없다.
  - untracked: `CLAUDE.local.md`(stage 금지), `docs/roadmap.md`(사용자 개인 확인용 → 올리지 않는다, 13장), 이 계획 문서.
  - PR #50(S5)·#51(S6)은 OPEN, 기준 `main`.
- `replay/ZonePlayer`:
  - `private final boolean loop;                 // S7 setLoop가 생기면 final을 뗀다`. 클래스 Javadoc "snapshot()·pollStateChange()와 S7의 제어 메서드는 다른 스레드(WS·REST)에서도 부르므로 모든 공개 메서드를 synchronized로".
  - `state`는 `PLAYING`으로 시작하고 `tick()`에서 `ENDED`로만 바뀐다. **`PAUSED`를 대입하는 코드가 없다.**
  - `tick()` Javadoc "PAUSED·ENDED이면 빈 값". `snapshot()`은 `PlaybackSnapshot(state, currentT, loop, durationS)`.
- `grep -rn "PAUSED\|paused" src`: `PlaybackState.java`(enum 값, Javadoc "PAUSED는 S7에서 처음 쓴다"), `ZonePlayer.java:45`·`ZoneRuntime.java:36`(Javadoc "PAUSED·ENDED"), `ws/message/PlaybackMessage.java:8`·`PlaybackView.java:6`(Javadoc "playing·paused·ended"), `MessageFactoryTest.java:133`(`@CsvSource({"PLAYING,playing", "PAUSED,paused", "ENDED,ended"})`). 그 밖 없음.
- `grep -rn "S7" src/main`: `PlaybackState.java:3`, `Tick.java:9`("첫 프레임·반복·이동(S7) 직후"), `ZonePlayer.java:12·18`, `ZoneRuntime.java:13`("S3 hello, S7 제어").
- `grep -rn "이동" src/main`: 위 `Tick`·`ZoneRuntime:11` 외에 `alert/AlertDetector.java:52`("첫 프레임·반복·이동"), `grade/GradeHysteresis.java:61`, `grade/InflowMonitor.java:50`, `grade/InstabilityTracker.java:36`("반복·이동"), `grade/ZoneGrader.java:89`("첫 프레임·반복·이동"). 모두 Javadoc. `server/README.md:44` "반복·이동 뒤 처음 4초는 평균이 없다".
- `replay/ReplayScheduler`: `@RequiredArgsConstructor` 필드 4개(`zones`, `replayTaskScheduler`, `props`, `broadcaster`), `tickAll()` 패키지 전용. `ReplaySchedulerTest`가 생성자를 **5번** 직접 부른다(`grep -c "new ReplayScheduler("` = 5). `ReplaySchedulerIntegrationTest`는 Spring이 만든다.
- `ws/MessageFactory.stateName(PlaybackState)`: **패키지 전용 static**, `playback`·`playbackView`가 쓴다.
- `ws/ZoneSessions.sessionCount()`: 전체 접속 수 `int`, `ConcurrentHashMap`이라 어느 스레드에서 읽어도 된다.
- `replay/ZoneRegistry`: 만든 뒤 바뀌지 않는 목록, `find(zoneId)`(null·없으면 빈 값), `all()`(설정 순서).
- `timeline/ZoneTimeline.metaJson()`: record 성분이라 늘 같은 인스턴스(원본 `meta` 트리, 모르는 키 포함). `hello.meta`로 이미 보낸다. `timeline/Meta(zoneId, cameraId, videoId, durationS, intervalS, cellSizeM, models, prediction, cells)`.
- fixture `src/test/resources/timeline/valid_v02.json`: `zone_id` `zone-test`, `camera_id` `cam-test`, `video_id` `TEST_001`, `duration_s` 5.
- `api/AlertController`(S6): `@RequestMapping("/api")` + `/alerts/{alertId}/ack`, `/zones/{zoneId}/alerts`. 없는 구역·ID는 `ResponseEntity.notFound().build()`(본문 없음).
- `config/CorsConfig`(S6): `/api/**`, `allowedMethods("GET", "POST")`.
- `config/CrowdsightProperties.Replay(long intervalMs, boolean loop)`: compact 생성자가 `intervalMs <= 0` 거부. 직접 만드는 곳은 `TestProperties.full` 한 곳(`grep "Replay("`).
- 빠진 원시 타입 키는 0으로 묶인다: `CrowdsightPropertiesTest.rejectsMissingUnackedAlertLimit`가 `unacked-alert-limit` 삭제 → `BindException`(root cause에 키 이름)으로 이미 통과한다. `slow-tick-ms`도 같은 방식으로 거부된다.
- 기존 통합 테스트 컨텍스트 속성:
  - `CrowdsightServerApplicationIntegrationTest`: `timeline-dir`, `timeline-files` 2개.
  - `AlertControllerIntegrationTest`: 위 2개 + `alert-log=build/test-logs/alerts.jsonl`, `@AutoConfigureMockMvc`.
  - `ReplaySchedulerIntegrationTest`: + `interval-ms=50`. `ZoneWebSocketIntegrationTest`: RANDOM_PORT + `interval-ms=100`, `@AfterEach`에서 `sessions.sessionCount() == 0`까지 기다린다.
- `ThreadPoolTaskScheduler.scheduleAtFixedRate(task, Duration)`은 첫 실행을 바로 한다(v1 계획에서 jar 확인). 그래서 컨텍스트가 뜨면 곧 tick 1번이 돌아 `last_tick_ms`가 생긴다.
- `web/src`: 서버 재생 제어 REST를 부르는 코드가 없다(`grep "/api/\|playback"` → 없음). `CellHeatmap.tsx`·`lib/video.ts`의 `seekTo`는 화면 안 영상 맞춤이다(서버와 무관).
- `api-spec.md`: 2절 표에 `POST /api/zones/{zone_id}/playback`, 3.4 예시 `"state": "paused"`와 "이동(seek)하면…" 줄, 4.2 "이동(seek)이나 반복 재생으로"·"반복·이동 때", 4.4 "초기화(반복·이동, 4.2절)", 4.5 마지막 줄 "오류 본문 형식은 재생 제어(5절)와 함께 정한다 `[토론]`", 5절 재생 제어 표, 6절 "일시정지·이동은 `playback` 메시지를 따라", 10절 4번 "재생 상태를 접속자마다 따로 둘지".

## 1. 이번 계획에서 정한 것

### 1.1 전제: 영상은 실시간 CCTV다
- 서버는 녹화 영상의 `timeline.json`을 **끊김 없는 CCTV 피드처럼** 1초마다 재생한다. 반복(`crowdsight.replay.loop`)은 피드가 계속 들어오는 것을 흉내 내는 설정이다.
- 실제 관제에서 CCTV 분석은 멈추거나 되돌릴 수 없다. 모든 화면이 공유하는 일시정지·이동은 판정과 알림을 전부 멈추므로 서비스에 없는 기능이다. 그래서 **재생 제어 REST를 만들지 않는다**(api-spec 5절 삭제).
- CCTV별 현재 밀도·흐름·예측은 이미 카메라(구역)별 WS `zone_state`로 화면에 간다(S3·S4: 셀 `density`, `vx`·`vy`, `speed_var`, `pressure`, `counterflow`, `density_pred_60s`·`grade_pred_60s`, 구역 `grade`·`max_density`·`inflow_ratio`·`inflow_alert`·`count`). S7은 화면이 고를 **카메라 목록**과 운영 상태를 준다.

### 1.2 결정 표
| # | 항목 | 결정 | 이유 |
|---|---|---|---|
| 1 | 재생 제어 REST | 만들지 않는다. `ZonePlayer`에 제어 메서드를 더하지 않고 `loop`는 `final` 그대로 | 1.1 전제 |
| 2 | 패키지 | `api/`: `ZoneController`, `HealthController`, `ZoneSummary`, `HealthResponse`, `ZoneHealth` 추가. `replay/`: `TickStats` 추가, `ReplayScheduler` 수정. `ws/MessageFactory.stateName` 공개 | 계획 1.1. 처리 시간은 재생 스레드가 재므로 `replay/` |
| 3 | `GET /api/zones` | `[{zone_id, camera_id, video_id}]`, 설정 순서. **`duration_s`는 넣지 않는다** (확정 11-16) | 카메라 등록 목록이다. 길이는 녹화 재생의 값이라 CCTV 목록에 맞지 않는다(필요하면 `/meta`·`hello.playback.duration_s`). `video_id`는 화면이 영상(피드)을 찾는 키(api-spec 6절). `camera_id`는 CLAUDE.md "API에 처음부터 `zone_id`·`camera_id`" |
| 4 | `GET /api/zones/{zone_id}/meta` | 원본 `meta` 트리(`ZoneTimeline.metaJson()`) 그대로. 없는 구역 404(본문 없음) | api-spec 2절 "타임라인 `meta` 그대로". `hello.meta`와 같다. 화면이 WS 접속 전에 셀 배치를 그릴 수 있다 |
| 5 | `GET /api/health` | `{status:"UP", zones:[{zone_id, state, t, loop}], sessions, last_tick_ms, max_tick_ms}`. tick 전이면 두 시간 `null` | 계획 + 구역 `loop`(E8 30분 반복 시험 중 반복이 켜졌는지). `t`는 피드가 지금 몇 초인지(운영 확인). 응답하면 서버가 살아 있으므로 `status`는 늘 `"UP"` |
| 6 | tick 처리 시간 | `ReplayScheduler.tickAll` 전체(모든 구역 판정 + 방송)를 `System.nanoTime()` 차이로 잰다. `TickStats`(`@Component`)에 last·max(서버 시작부터), ms 소수 3자리. `crowdsight.replay.slow-tick-ms`(기본 500)를 넘으면 WARN | CLAUDE.md: 경과 시간만 `nanoTime`, 기준값은 설정에. 방송까지 넣어야 느린 화면 영향(2초 × n)이 보인다(S3 위험 표) |
| 7 | `TickStats` 스레드 | 쓰기는 재생 스레드 하나, 읽기는 요청 스레드. `volatile long` 두 개, 잠금 없음 | 쓰는 스레드가 하나라 "읽고-비교-쓰기"가 경쟁하지 않는다. last와 max가 같은 tick 값일 필요는 없다 |
| 8 | `PlaybackState.PAUSED` | **삭제** (확정 11-16). `playback`·`hello.playback`의 `state`는 `playing`·`ended` 두 값 | 만드는 코드가 없고(0장), 재생 제어를 두지 않으므로 앞으로도 없다. 남기면 화면이 처리할 필요 없는 상태를 처리하게 된다. WS 키는 그대로이고 값 집합만 준다(화면이 아직 `paused`를 쓰지 않는다, 0장 web) |
| 9 | 재생 제어 흔적 정리 | `src/main`의 `S7` 언급 4곳, seek를 뜻하는 "이동" Javadoc 7곳, README 1줄을 "첫 프레임·반복"으로 고친다 | 없는 기능을 설명하는 주석은 틀린 문서다. 동작은 바뀌지 않는다 |
| 10 | 오류 본문 (api-spec 4.5 `[토론]`) | **닫는다** (확정 11-16): 없는 구역·알림 `404`는 본문 없음. `400`은 Spring 기본 응답(ProblemDetail 설정 안 함) | S7은 새 `400`을 만들지 않는다(입력 본문이 없다). 남은 `400`은 S6 `unacked=abc` 하나라 화면은 상태 코드만 보면 된다. 화면에 이유를 보여 줄 REST 입력이 생기면 그때 ProblemDetail(RFC 9457)로 정한다 |
| 11 | 컨트롤러 나눔 | `ZoneController`(`/api/zones`, `/meta`), `HealthController`(`/api/health`) | 계획 1.1. 구역 자원과 서버 운영 상태는 바뀌는 이유가 다르다 |
| 12 | 인증 | 없음 | 조회만 남아 위험이 줄었다. MVP 시연은 같은 PC·내부망(가정). 위험 표에 남김 |
| 13 | 브랜치 | 원격에 없는 로컬 브랜치 `feat/server-playback-api` → `feat/server-zones-health`(`git branch -m`) | 브랜치 이름이 목적과 같아야 한다(CLAUDE.md). 0장: 원격 정리 불필요 |

## 2. 구조와 파일

### 2.1 추가·수정 파일
```text
server/
├─ README.md                                                     수정 (조회·서버 상태 절, 44줄 "반복·이동 뒤" → "반복 뒤")
├─ src/main/resources/application.yml                            수정 (replay.slow-tick-ms)
├─ src/main/java/com/tripley/crowdsight/
│  ├─ config/  CrowdsightProperties (Replay.slowTickMs)           수정
│  ├─ replay/  TickStats                                         추가
│  │           ReplayScheduler (TickStats, 느린 tick WARN)       수정
│  │           PlaybackState (PAUSED 삭제)                       수정 (결정 #8)
│  │           ZonePlayer·ZoneRuntime·Tick (Javadoc·주석만)       수정
│  ├─ grade/   GradeHysteresis·InflowMonitor·InstabilityTracker·ZoneGrader (Javadoc만)   수정
│  ├─ alert/   AlertDetector (Javadoc만)                         수정
│  ├─ ws/      MessageFactory (stateName 공개)                   수정
│  │           message/PlaybackMessage·PlaybackView (Javadoc만)  수정
│  └─ api/     ZoneController, HealthController, ZoneSummary, HealthResponse, ZoneHealth   추가
└─ src/test/java/com/tripley/crowdsight/
   ├─ CrowdsightServerApplicationIntegrationTest                 수정 (+1)
   ├─ config/   CrowdsightPropertiesTest (+3, defaults), TestProperties (SLOW_TICK_MS)   수정
   ├─ replay/   ReplaySchedulerTest (+1, 생성자 5곳), TickStatsTest (추가)   수정·추가
   ├─ ws/       MessageFactoryTest (CsvSource에서 PAUSED 행 삭제), ZoneWebSocketIntegrationTest (+1)   수정
   └─ api/      ZoneControllerTest, HealthControllerTest, ZoneControllerIntegrationTest   추가
docs/plans/server_s7_zones_health_plan.md                       (이 문서)
docs/plans/server_impl_plan.md                                   정정 (11.1절)
docs/api-spec.md                                                 정정 (11.2절)
```
- 바뀌지 않는 것: WS 메시지 키(`hello`·`zone_state`·`alert`·`playback`), `hello.schema_version` `"0.2"`, `ZonePlayer`·`ZoneRuntime` 코드(Javadoc만), 판정·알림 규칙, `AlertController`, `ZoneSessions`, `WsZoneBroadcaster`, `CorsConfig`.

### 2.2 요청·재생 흐름
```text
재생 스레드 (ReplayScheduler.tickAll, 1초마다)             start = System.nanoTime()
  구역마다 tickZone: ZoneRuntime.tick() → [playback] → zone_state (+ alert)      ← S1~S6 그대로
  TickStats.record(System.nanoTime() - start), slow-tick-ms 넘으면 WARN

Tomcat 요청 스레드
  GET /api/zones            → ZoneRegistry.all() → [ZoneSummary]
  GET /api/zones/{id}/meta  → ZoneRegistry.find(id) → ZoneTimeline.metaJson() | 404
  GET /api/health           → 구역마다 ZonePlayer.snapshot() (synchronized),
                              ZoneSessions.sessionCount(), TickStats.lastMs()/maxMs() (volatile)
```

### 2.3 의존 방향
```text
api ──→ replay (ZoneRegistry, ZoneRuntime, PlaybackSnapshot, TickStats)
 ├──→ timeline (Meta, ZoneTimeline)
 ├──→ ws (MessageFactory.stateName, ZoneSessions)
 └──→ alert (S6 그대로)
replay ──→ grade, alert, timeline, config (그대로. api·ws를 모른다)
```
- 순환 없음. `replay`는 `TickStats`만 더한다.

### 2.4 스레드 규칙
| 클래스 | 누가 부르나 | 규칙 |
|---|---|---|
| `ZonePlayer.tick`, `pollStateChange` | 재생 스레드 | `synchronized` (그대로) |
| `ZonePlayer.snapshot` | 재생·WS(hello)·REST(health) 스레드 | `synchronized` (그대로) |
| `TickStats.record` | 재생 스레드 하나 | `volatile` 쓰기 |
| `TickStats.lastMs`·`maxMs` | 요청 스레드 | `volatile` 읽기 |
| `ZoneController`, `HealthController` | 요청 스레드 | 상태 없음 |
| `ZoneSummary`, `HealthResponse`, `ZoneHealth` | 어디서나 | 불변 record |

## 3. 설정

### 3.1 `application.yml` (수정분)
```yaml
crowdsight:
  # ... (그대로)
  replay:
    interval-ms: 1000                        # 1초 = 타임라인 1칸 (interval_s 1)
    loop: true                               # 끝에서 처음으로 (E8 30분 반복)
    slow-tick-ms: 500                        # tick 1번(판정+방송) 처리가 이보다 길면 WARN. last·max는 /api/health
```

### 3.2 `config/CrowdsightProperties.java` (수정분)
```java
    /**
     * 재생 설정.
     *
     * @param intervalMs 타임라인 1칸을 재생하는 간격(ms). 운영 1000, 테스트만 짧게
     * @param loop       끝에서 처음으로 돌아갈지
     * @param slowTickMs tick 1번(모든 구역 판정 + 방송) 처리 시간이 이보다 길면 WARN (ms, 0보다 큼)
     */
    public record Replay(long intervalMs, boolean loop, long slowTickMs) {

        public Replay {
            if (intervalMs <= 0) {
                throw new IllegalArgumentException("crowdsight.replay.interval-ms 는 0보다 커야 합니다: " + intervalMs);
            }
            if (slowTickMs <= 0) {     // 키가 없으면 0으로 묶여 여기서 거부된다
                throw new IllegalArgumentException(
                        "crowdsight.replay.slow-tick-ms 는 0보다 커야 합니다: " + slowTickMs);
            }
        }
    }
```

### 3.3 `config/TestProperties.java` (수정분)
```java
    /** application.yml crowdsight.replay.slow-tick-ms 기본값과 같다 (bindsDefaultSlowTickMs가 확인). */
    public static final long SLOW_TICK_MS = 500;

    private static CrowdsightProperties full(String dir, List<String> files, long intervalMs, boolean loop,
                                             CrowdsightProperties.Ws ws, String alertLog) {
        return new CrowdsightProperties(dir, files, TIME_ZONE,
                new CrowdsightProperties.Replay(intervalMs, loop, SLOW_TICK_MS),
                GRADE, INSTABILITY, INFLOW, UNACKED_ALERT_LIMIT, ws, alertLog, CORS);
    }
```

## 4. 재생기 (`replay/`)

### 4.1 `replay/TickStats.java` (추가)
```java
package com.tripley.crowdsight.replay;

import org.springframework.stereotype.Component;

/**
 * 재생 tick 1번(모든 구역 판정 + 방송) 처리 시간의 마지막 값과 최댓값 (/api/health, api-spec 7절 E8 참고).
 * 시간은 System.nanoTime() 차이로 잰 경과 시간이다 (벽시계 아님, CLAUDE.md).
 * 스레드 규칙: record는 재생 스레드 하나만 부른다. lastMs·maxMs는 요청 스레드가 읽는다.
 * 쓰는 스레드가 하나라 volatile로 충분하다 (last와 max가 같은 tick 값일 필요는 없다).
 */
@Component
public final class TickStats {

    private volatile long lastNanos = -1;     // -1: 아직 tick 없음
    private volatile long maxNanos = -1;

    /** tick 1번의 처리 시간(나노초)을 기록한다. */
    public void record(long elapsedNanos) {
        if (elapsedNanos < 0) {
            throw new IllegalArgumentException("처리 시간은 0 이상이어야 합니다: " + elapsedNanos);
        }
        lastNanos = elapsedNanos;
        if (elapsedNanos > maxNanos) {
            maxNanos = elapsedNanos;
        }
    }

    /** 마지막 tick 처리 시간(ms, 소수 3자리). tick 전이면 null. */
    public Double lastMs() {
        return toMs(lastNanos);
    }

    /** 서버 시작부터 가장 긴 tick 처리 시간(ms, 소수 3자리). tick 전이면 null. */
    public Double maxMs() {
        return toMs(maxNanos);
    }

    private static Double toMs(long nanos) {
        return nanos < 0 ? null : Math.round(nanos / 1_000.0) / 1_000.0;
    }
}
```

### 4.2 `replay/ReplayScheduler.java` (수정분)
```java
/**
 * ... (그대로)
 * tick마다 처리 시간(System.nanoTime 차이)을 TickStats에 남기고, crowdsight.replay.slow-tick-ms를 넘으면 WARN을 남긴다.
 */
public class ReplayScheduler implements SmartLifecycle {

    private final ZoneRegistry zones;
    private final ThreadPoolTaskScheduler replayTaskScheduler;
    private final CrowdsightProperties props;
    private final ZoneBroadcaster broadcaster;
    private final TickStats tickStats;
    private volatile ScheduledFuture<?> future;

    /** 모든 구역을 한 칸씩 진행·판정하고 내보낸 뒤 처리 시간을 기록한다. 재생 작업에서만 부른다 (테스트는 직접 부른다). */
    void tickAll() {
        long start = System.nanoTime();
        for (ZoneRuntime zone : zones.all()) {
            try {
                tickZone(zone);
            } catch (RuntimeException e) {
                log.error("구역 재생 중 오류, 다음 구역으로 계속 zone={}", zone.zoneId(), e);
            }
        }
        long elapsed = System.nanoTime() - start;
        tickStats.record(elapsed);
        long slowMs = props.replay().slowTickMs();
        if (elapsed > TimeUnit.MILLISECONDS.toNanos(slowMs)) {
            log.warn("tick 처리가 느림 처리={} ms 기준={} ms 구역={}개 (/api/health 참고)", tickStats.lastMs(),
                    slowMs, zones.all().size());
        }
    }
    // start·stop·isRunning·tickZone은 그대로
}
```
- import에 `java.util.concurrent.TimeUnit`을 더한다.
- `ReplaySchedulerTest`의 생성자 호출 5곳에 `new TickStats()`를 더한다.

### 4.3 `replay/PlaybackState.java` (수정, 결정 #8)
```java
/** 구역 재생 상태. playback 메시지에서는 소문자로 보낸다. 실시간 CCTV처럼 재생하므로 화면이 바꾸지 않는다. */
public enum PlaybackState {
    PLAYING, ENDED
}
```
- `ENDED`는 `loop: false`일 때 피드 끝이다(시험·개발용 설정).
- 결정 #8을 반려하면 이 절은 Javadoc만 "PAUSED는 쓰지 않는다(재생 제어 없음)"로 바꾸고 enum 값과 `MessageFactoryTest`는 그대로 둔다.

### 4.4 Javadoc·주석 정정 (동작 변경 없음)
| 파일 | 지금 | 바꿀 문구 |
|---|---|---|
| `replay/ZonePlayer` 클래스 | "스레드 규칙: tick()은 재생 스레드만 부른다. snapshot()·pollStateChange()와 S7의 제어 메서드는 다른 스레드(WS·REST)에서도 부르므로 모든 공개 메서드를 synchronized로 둔다." | "스레드 규칙: tick()·pollStateChange()는 재생 스레드가 부르고, snapshot()은 다른 스레드(WS hello, REST health)에서도 부르므로 모든 공개 메서드를 synchronized로 둔다." |
| `replay/ZonePlayer` `loop` 필드 | `// S7 setLoop가 생기면 final을 뗀다` | 주석 삭제 |
| `replay/ZonePlayer.tick` | "PAUSED·ENDED이면 빈 값." | "ENDED이면 빈 값." |
| `replay/ZoneRuntime` 클래스 | "불연속 tick(첫 프레임·반복·이동)", "다른 스레드(S3 hello, S7 제어)" | "불연속 tick(첫 프레임·반복)", "다른 스레드(WS hello, REST health)" |
| `replay/ZoneRuntime.tick` | "재생할 프레임이 없으면(PAUSED·ENDED) 빈 값." | "재생할 프레임이 없으면(ENDED) 빈 값." |
| `replay/Tick` `@param discontinuity` | "첫 프레임·반복·이동(S7) 직후. 판정 상태를 초기화한다 (S2)" | "첫 프레임·반복 직후. 판정 상태를 초기화한다 (S2)" |
| `alert/AlertDetector.reset` | "(첫 프레임·반복·이동)" | "(첫 프레임·반복)" |
| `grade/GradeHysteresis.reset`, `InflowMonitor.reset`, `InstabilityTracker.reset` | "(반복·이동)" | "(첫 프레임·반복)" |
| `grade/ZoneGrader.reset` | "(첫 프레임·반복·이동)" | "(첫 프레임·반복)" |
| `ws/message/PlaybackMessage` `@param state`, `PlaybackView` `@param state` | "playing·paused·ended" | "playing·ended" (결정 #8 반려 시 그대로) |

## 5. REST (`api/`, `ws/`)

### 5.1 `ws/MessageFactory.java` (수정분)
```java
    /** 재생 상태의 메시지 표기 (playing·ended). REST health도 쓴다. */
    public static String stateName(PlaybackState state) {
        return state.name().toLowerCase(Locale.ROOT);
    }
```

### 5.2 `api/ZoneSummary.java`, `api/ZoneHealth.java`, `api/HealthResponse.java` (추가)
```java
package com.tripley.crowdsight.api;

import com.tripley.crowdsight.timeline.Meta;
import com.tripley.crowdsight.timeline.ZoneTimeline;

/**
 * GET /api/zones 원소. 카메라 한 대 = 구역 하나 (실시간 CCTV 흉내).
 *
 * @param zoneId   구역 ID
 * @param cameraId 카메라 ID (CLAUDE.md: API에 처음부터 zone_id·camera_id)
 * @param videoId  영상(피드) ID. 화면이 영상 파일을 찾는다 (api-spec 6절)
 */
public record ZoneSummary(String zoneId, String cameraId, String videoId) {

    /** 타임라인 meta에서 만든다. */
    public static ZoneSummary of(ZoneTimeline timeline) {
        Meta m = timeline.meta();
        return new ZoneSummary(m.zoneId(), m.cameraId(), m.videoId());
    }
}
```
```java
/**
 * /api/health의 구역 하나.
 *
 * @param zoneId 구역 ID
 * @param state  playing·ended
 * @param t      마지막으로 재생한 초 (시작 전 0)
 * @param loop   끝에서 처음으로 돌아가는지
 */
public record ZoneHealth(String zoneId, String state, int t, boolean loop) {
}
```
```java
/**
 * GET /api/health 응답.
 *
 * @param status     늘 "UP" (응답하면 살아 있다)
 * @param zones      구역별 재생 상태 (설정 순서)
 * @param sessions   모든 구역 WebSocket 접속 수
 * @param lastTickMs 마지막 tick 처리 시간(ms). tick 전이면 null
 * @param maxTickMs  서버 시작부터 가장 긴 tick 처리 시간(ms). tick 전이면 null
 */
public record HealthResponse(String status, List<ZoneHealth> zones, int sessions, Double lastTickMs,
                             Double maxTickMs) {

    public static final String UP = "UP";

    public HealthResponse {
        zones = List.copyOf(zones);
    }
}
```

### 5.3 `api/ZoneController.java` (추가)
```java
package com.tripley.crowdsight.api;

import java.util.List;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import com.tripley.crowdsight.replay.ZoneRegistry;

import lombok.RequiredArgsConstructor;
import tools.jackson.databind.JsonNode;

/**
 * 카메라·구역 목록과 구역 meta 조회 (api-spec 2절·5절). 화면은 목록에서 카메라를 골라 /ws/zones/{zone_id}에 접속한다.
 * 없는 구역은 404(본문 없음).
 * 스레드 규칙: Tomcat 요청 스레드에서 동시에 불린다. 상태가 없고 ZoneRegistry는 바뀌지 않는다.
 */
@RestController
@RequestMapping("/api/zones")
@RequiredArgsConstructor
public class ZoneController {

    private final ZoneRegistry zones;

    /** 카메라·구역 목록 (설정 순서). */
    @GetMapping
    public List<ZoneSummary> list() {
        return zones.all().stream().map(z -> ZoneSummary.of(z.player().timeline())).toList();
    }

    /** 타임라인 meta 원본 (hello.meta와 같다). 없는 구역은 404. */
    @GetMapping("/{zoneId}/meta")
    public ResponseEntity<JsonNode> meta(@PathVariable String zoneId) {
        return zones.find(zoneId)
                .map(z -> ResponseEntity.ok(z.player().timeline().metaJson()))
                .orElseGet(() -> ResponseEntity.notFound().build());
    }
}
```
- `/api/zones/{zoneId}/alerts`(S6 `AlertController`)와 경로가 겹치지 않는다.
- `JsonNode`는 이름 바꾸기(`SNAKE_CASE`)를 거치지 않아 원본 키가 그대로 나간다.

### 5.4 `api/HealthController.java` (추가)
```java
/**
 * 서버 상태 (api-spec 2절 GET /api/health). 구역별 재생 상태, WebSocket 접속 수, tick 처리 시간 last·max.
 * 스레드 규칙: Tomcat 요청 스레드에서 불린다. 상태가 없고, 읽는 대상(ZonePlayer·ZoneSessions·TickStats)이 각자 스레드 안전하다.
 */
@RestController
@RequestMapping("/api")
@RequiredArgsConstructor
public class HealthController {

    private final ZoneRegistry zones;
    private final ZoneSessions sessions;
    private final TickStats tickStats;

    /** 서버 상태. 응답하면 status는 늘 UP. */
    @GetMapping("/health")
    public HealthResponse health() {
        List<ZoneHealth> zoneHealth = zones.all().stream().map(z -> {
            PlaybackSnapshot s = z.player().snapshot();
            return new ZoneHealth(z.zoneId(), MessageFactory.stateName(s.state()), s.t(), s.loop());
        }).toList();
        return new HealthResponse(HealthResponse.UP, zoneHealth, sessions.sessionCount(), tickStats.lastMs(),
                tickStats.maxMs());
    }
}
```
- 구역마다 `snapshot()`을 따로 잠그므로 구역끼리 같은 순간 값은 아니다(MVP 구역 1개라 문제없음).
- Spring Boot Actuator(`/actuator/health`)는 쓰지 않는다: 의존성이 늘고, 필요한 값(재생 `t`, 접속 수, tick 시간)은 어차피 직접 만들어야 한다.

## 6. 엔드포인트 정리
| 방식 | 경로 | 200 응답 | 그 밖 |
|---|---|---|---|
| GET | `/api/zones` | `[{"zone_id","camera_id","video_id"}]` (설정 순서) | — |
| GET | `/api/zones/{zone_id}/meta` | 타임라인 `meta` 원본 객체 | 404 본문 없음 |
| GET | `/api/health` | `{"status":"UP","zones":[{"zone_id","state","t","loop"}],"sessions","last_tick_ms","max_tick_ms"}` | — |

## 7. 동시성
- 새 공유 상태는 `TickStats` 하나다. 단일 작성자(재생 스레드) + `volatile` 읽기라 잠금이 없다.
- `HealthController`는 `ZonePlayer.snapshot()`(이미 `synchronized`)과 `ZoneSessions.sessionCount()`(Concurrent 맵)를 읽기만 한다. 재생 스레드의 판정 상태(`ZoneGrader`, `AlertDetector`)는 건드리지 않는다.
- WARN 로그는 재생 스레드에서 남긴다. 느린 화면이 계속 있으면 매 tick WARN이 쌓일 수 있으나, 느린 세션은 2초 뒤 닫힌다(결정 기록 1).

## 8. 테스트
공통 상수 (단위 테스트):
```java
static final Clock FIXED = Clock.fixed(Instant.parse("2026-11-18T05:02:31.512Z"), ZoneId.of("Asia/Seoul"));
```

### 8.1 `config/CrowdsightPropertiesTest` (수정·추가), `CrowdsightServerApplicationIntegrationTest` (+1)
- `defaults()`에 `map.put("crowdsight.replay.slow-tick-ms", "500")`.

| 메서드 | `@DisplayName` | 입력 | 기대 |
|---|---|---|---|
| `bindsSlowTickMs` | 느린 tick 기준을 묶는다 | defaults | `replay().slowTickMs()` = 500 |
| `rejectsNonPositiveSlowTick` (`@ValueSource(longs = {0, -1})`) | 느린 tick 기준이 0 이하이면 거부한다 | 값 | `BindException`, root cause 메시지에 `crowdsight.replay.slow-tick-ms` |
| `rejectsMissingSlowTick` | 느린 tick 기준이 없으면 거부한다 | 키 삭제 | 같음 |
| `CrowdsightServerApplicationIntegrationTest.bindsDefaultSlowTickMs` | application.yml의 느린 tick 기준을 읽는다 | yml | `props.replay().slowTickMs()` = `TestProperties.SLOW_TICK_MS` |

### 8.2 `replay/TickStatsTest` (추가)
| 메서드 | `@DisplayName` | 입력 | 기대 |
|---|---|---|---|
| `emptyBeforeFirstRecord` | 기록 전에는 null이다 | 새 객체 | `lastMs()`·`maxMs()` null |
| `recordsLastAndMax` | 마지막 값과 최댓값을 ms로 준다 | record 1_234_567, 500_000, 2_000_000 | 각 뒤 last [1.235, 0.5, 2.0], max [1.235, 1.235, 2.0] |
| `roundsToMicroseconds` | 소수 3자리로 반올림한다 | record 999, 1_499 | last 0.001, 0.001 |
| `rejectsNegative` | 음수 시간은 거부한다 | record -1 | `IllegalArgumentException` |

### 8.3 `replay/ReplaySchedulerTest` (추가 1, 생성자 5곳에 `new TickStats()`)
| 메서드 | `@DisplayName` | 입력 | 기대 |
|---|---|---|---|
| `recordsTickTime` | tick 처리 시간을 기록한다 | `TickStats stats`, (5, loop), `tickAll` 전·후 | 전 `lastMs()` null, 후 `lastMs()` ≥ 0, `maxMs()` ≥ `lastMs()` |
- 기존 5개(`survivesZoneException`, `ticksOnSchedule`, `wrapSendsPlaybackBeforeZoneState`, `endSendsPlaybackOnce`, `broadcastFailureDoesNotStopOtherZones`)는 생성자 인자만 늘고 그대로 통과.
- WARN 로그는 단위 테스트하지 않는다(시간에 기대는 테스트가 된다). 12장 검증과 리뷰로 확인한다.

### 8.4 `ws/MessageFactoryTest` (수정, 결정 #8)
- `playbackStateLowercase`의 `@CsvSource({"PLAYING,playing", "PAUSED,paused", "ENDED,ended"})` → `@CsvSource({"PLAYING,playing", "ENDED,ended"})`. 테스트 이름·단언은 그대로.

### 8.5 `api/ZoneControllerTest` (추가, 평범한 Java 객체)
```java
CrowdsightProperties props = TestProperties.replay(1000, true);
ZoneRegistry zones = new ZoneRegistry(new TimelineLoader(MAPPER, props), props);   // fixture zone-test, 길이 5
ZoneController controller = new ZoneController(zones);
```
| 메서드 | `@DisplayName` | 입력 | 기대 |
|---|---|---|---|
| `listsZones` | 카메라·구역 목록에 zone·camera·video ID를 준다 | `list()` | `[new ZoneSummary("zone-test", "cam-test", "TEST_001")]` |
| `metaReturnsOriginalTree` | meta는 타임라인 원본을 그대로 준다 | `meta("zone-test")` | 200, body `isSameAs(timeline.metaJson())`, `isEqualTo(MAPPER.readTree(fixturePath()).get("meta"))` |
| `metaUnknownZoneIs404` | 없는 구역 meta는 404 | `meta("zone-nope")` | 404, body null |

### 8.6 `api/HealthControllerTest` (추가)
`stats = new TickStats()`, `sessions = new ZoneSessions(props)`, `controller = new HealthController(zones, sessions, stats)`.

| 메서드 | `@DisplayName` | 입력 | 기대 |
|---|---|---|---|
| `healthBeforeFirstTick` | tick 전에는 처리 시간이 null이다 | `health()` | `new HealthResponse("UP", [new ZoneHealth("zone-test", "playing", 0, true)], 0, null, null)` |
| `healthReportsTickTime` | 처리 시간 last·max를 준다 | record 1_234_567, 500_000 | `lastTickMs` 0.5, `maxTickMs` 1.235 |
| `healthReflectsPlaybackState` | 재생 상태를 반영한다 | `TestProperties.replay(1000, false)`로 만든 registry, 구역 `tick()` 6번(길이 5) | 구역 `new ZoneHealth("zone-test", "ended", 4, false)` |

### 8.7 `api/ZoneControllerIntegrationTest` (추가)
```java
@SpringBootTest(properties = {
        "crowdsight.timeline-dir=src/test/resources/timeline",
        "crowdsight.timeline-files=valid_v02.json"
})
@AutoConfigureMockMvc
class ZoneControllerIntegrationTest {
    @Autowired private MockMvcTester mvc;

    private static JsonNode json(MvcTestResult r) throws Exception {
        return MAPPER.readTree(r.getResponse().getContentAsString(StandardCharsets.UTF_8));
    }
}
```
- 속성 2개 + `@AutoConfigureMockMvc` 조합은 기존 클래스에 없다(`CrowdsightServerApplicationIntegrationTest`는 MockMvc 없음, `AlertControllerIntegrationTest`는 `alert-log` 추가). 이 클래스 전용 컨텍스트다. 조회만 하므로 상태가 새지 않는다.

| 메서드 | `@DisplayName` | 요청 | 기대 |
|---|---|---|---|
| `listZonesOverHttp` | 구역 목록 키가 정해져 있다 | `GET /api/zones` | 200, 배열 1개, 키 정확히 `zone_id, camera_id, video_id`, 값 `zone-test, cam-test, TEST_001` |
| `metaOverHttp` | meta를 원본 그대로 준다 | `GET /api/zones/zone-test/meta` | 200, body = `MAPPER.readTree(fixturePath()).get("meta")` |
| `metaUnknownZoneIs404` | 없는 구역 meta는 404이고 본문이 없다 | `GET /api/zones/zone-nope/meta` | 404, 본문 길이 0 |
| `healthOverHttp` | health 키가 정해져 있고 처리 시간이 찍힌다 | `GET /api/health` (Awaitility 3초, `last_tick_ms` non-null까지) | 200, 키 정확히 `status, zones, sessions, last_tick_ms, max_tick_ms`, `status` "UP", `zones[0]` 키 정확히 `zone_id, state, t, loop`, `state` "playing", `sessions` 0 |
| `corsAllowsDevOrigin` | 허용 출처의 조회에 CORS 헤더를 준다 | `GET /api/zones`, `Origin: http://localhost:5173` | 200, `Access-Control-Allow-Origin` = origin |

### 8.8 `ws/ZoneWebSocketIntegrationTest` (추가 1)
- 같은 컨텍스트(RANDOM_PORT, interval 100)와 `connect` 헬퍼를 쓴다. JDK `java.net.http.HttpClient`로 `GET http://localhost:{port}/api/health`.

| 메서드 | `@DisplayName` | 순서 | 기대 |
|---|---|---|---|
| `healthCountsSessions` | health 접속 수는 연결된 화면 수다 | `connect("zone-test").next()`(hello) → health | Awaitility 3초 안에 `sessions` 1 (hello 전송 뒤 방송 대상에 넣으므로 기다린다). `@AfterEach`가 닫고 0을 기다린다(그대로) |

## 9. 출력 예시 (PR 설명·나예린 님 전달용)
```http
GET /api/zones
[{"zone_id":"zone-e04-039","camera_id":"cam-e04","video_id":"E04_039"}]

GET /api/zones/zone-e04-039/meta
{"zone_id":"zone-e04-039","camera_id":"cam-e04","video_id":"E04_039","duration_s":180,"interval_s":1,"cell_size_m":2.0,"models":{...},"prediction":{...},"cells":[...]}

GET /api/health
{"status":"UP","zones":[{"zone_id":"zone-e04-039","state":"playing","t":57,"loop":true}],"sessions":1,"last_tick_ms":0.412,"max_tick_ms":3.871}

GET /api/zones/zone-nope/meta
HTTP/1.1 404   (본문 없음)
```
- 실제 키 값은 구현 뒤 실제 출력으로 바꿔 적는다.

### 9.1 화면(web) 처리 제안 (나예린 님)
- 시작: `GET /api/zones`로 카메라 목록 → 고른 카메라의 `/ws/zones/{zone_id}`에 접속 → `hello`·`zone_state`로 그 CCTV의 현재 밀도·흐름·예측을 그린다.
- 재생 버튼(재생·정지·이동)은 서버로 보내지 않는다. 서버 재생은 실시간 CCTV처럼 늘 흐른다. 화면 안 영상 맞춤(`lib/video.ts`)은 `zone_state.t`를 따른다(api-spec 6절).
- `playback`은 `playing`(반복으로 0, 피드 재시작)과 `ended`(피드 끝) 두 값만 온다.

## 10. 이후 할 일 (S7에서 만들지 않음)
| 언제 | 붙는 곳 | 내용 |
|---|---|---|
| G2(11-18) | `/api/health` | 30분 반복 시험(E8) 중 `max_tick_ms`·`sessions`·`loop` 확인. `slow-tick-ms`를 넘으면 WARN 로그로 시각 확인 |
| G2 뒤, 카메라를 더 붙일 때 | `/api/zones` | 여러 CCTV 한눈에 보기: 원소에 최근 구역 요약(`grade`, `max_density`, `inflow_alert`, `t`)을 더한다. 재생 스레드가 tick마다 구역 요약을 `volatile`로 남기고 요청 스레드가 읽는다 |
| 합의 후 | `/api/health` | 구역별 접속 수·미확인 알림 수(S4·S5 계획 11장) |
| MVP 밖 | 과거 구간 보기 | 녹화기(NVR)식: 관제요원 한 명이 지난 구간을 따로 본다. 실시간 판정은 계속 돈다. 공유 재생 상태를 바꾸지 않는 별도 기록 조회 API로 만든다 |
| MVP 밖 | 인증 | 확인 API 보호 |

## 11. 문서 정정 (이 PR의 docs 커밋)

### 11.1 `server_impl_plan.md`
1. 1.1 패키지: `replay/` 줄에 `TickStats`. `api/` 줄 → `AlertController, AckResponse, AlertView (S6), ZoneController, HealthController, ZoneSummary, HealthResponse, ZoneHealth (S7)`.
2. 1.2: "또는 없음(일시정지·끝)" → "또는 없음(끝)". "REST 제어(S7)는 `ZonePlayer`의 `synchronized` 메서드로 "다음 tick에 할 일"만 표시." 줄 삭제, 대신 "tick 처리 시간은 `TickStats`(S7). 화면은 재생을 제어하지 않는다(실시간 CCTV 전제, S7 계획 1.1)."
3. 2장 S7 행: 브랜치 `feat/server-zones-health`, 내용 "`/api/zones`(카메라 목록), `/meta`, `/health`, tick 처리 시간 (재생 제어 없음: 실시간 CCTV 전제)".
4. 2장 `### S7` 절 제목 "구역 조회와 서버 상태 (`feat/server-zones-health`)", 본문을 이 계획 1.2 결정 #1·#3~#6·#8, 6장 표, 8장 요약으로 바꾼다. "상세는 `docs/plans/server_s7_zones_health_plan.md`".
5. S1 코드 블록 `Tick` 주석 "첫 프레임·반복·이동 직후" → "첫 프레임·반복 직후". S4 `reset()` 주석 "(반복·이동)" → "(첫 프레임·반복)", 그 아래 줄 "초기화(반복·이동)" → "초기화(첫 프레임·반복)". 결정 기록 표(맨 위)는 당시 기록이라 고치지 않는다.
6. 4장 yml `replay`에 `slow-tick-ms: 500`.
7. 5장 "p95 ≤ 5초" 행: "500 ms 넘으면 WARN" → "`crowdsight.replay.slow-tick-ms`(500 ms)를 넘으면 WARN".
8. 8장 11행: "`playback` 일시정지·이동을 영상에도 반영" → "`playback`(반복 0·끝)을 영상에도 반영".

### 11.2 `docs/api-spec.md` (WS 키 변경 없음 → v0.2 유지)
1. 문서 상태 표에 행 추가: `| S7 보충 | (구현한 날짜): 재생 제어 REST 삭제(실시간 CCTV 전제), `playback` 상태 값 `playing`·`ended`, `/api/zones`·`/meta`·`/health` 응답(5절), 오류 본문(4.5) |`.
2. 1절 첫 줄 뒤에 추가: "녹화 영상을 실시간 CCTV처럼 끊김 없이 재생한다. 화면은 재생을 제어하지 않는다 (5절)."
3. 2절 표: `GET /api/zones` → "카메라·구역 목록 (`zone_id`, `camera_id`, `video_id`)". `POST /api/zones/{zone_id}/playback` 행 삭제. `GET /api/health` → "서버 상태 (구역별 재생 상태, 접속 수, tick 처리 시간)".
4. 3.4: 예시 → `{ "type": "playback", "zone_id": "zone-e04-039", "state": "ended", "t": 179, "loop": false }`. `state`: `playing`, `ended`. "이동(seek)하면 이 메시지 다음에 새 `t`의 `zone_state`가 온다." 줄 삭제. 추가: "보내는 때: 반복으로 처음(0)으로 돌아갈 때(피드 재시작), 끝에 닿았고 `loop`가 꺼져 있을 때(피드 끝)."
5. 4.2: "이동(seek)이나 반복 재생으로 `t`가 불연속이 되면" → "반복 재생으로 `t`가 불연속이 되면". "반복·이동 때" → "반복 때". 4.4: "초기화(반복·이동, 4.2절)" → "초기화(반복, 4.2절)".
6. 4.5 마지막 줄 → "`404` 본문은 없다. `400`은 Spring 기본 응답이고 화면은 상태 코드만 본다. 화면에 이유를 보여 줄 REST 입력이 생기면 그때 ProblemDetail(RFC 9457)로 정한다."
7. 5절 교체: 제목 "## 5. 재생 (실시간 CCTV 흉내)".
   - "서버는 구역마다 타임라인을 1초에 한 칸씩 끊김 없이 재생한다. 실시간 CCTV 분석은 멈추거나 되돌릴 수 없으므로 화면은 재생을 제어하지 않는다 (11-16 결정, 10절 22번)."
   - "끝에 닿으면 `crowdsight.replay.loop`(기본 `true`)대로 처음부터 다시 재생하거나 끝난다. 반복은 계속 들어오는 피드를 흉내 낸다 (E8 30분 무중단 시험)."
   - 5.1 `GET /api/zones`: 응답 예(9장), 설정 순서, 원소 키 3개.
   - 5.2 `GET /api/zones/{zone_id}/meta`: 타임라인 `meta` 그대로(`hello.meta`와 같음), 없는 구역 `404` 본문 없음.
   - 5.3 `GET /api/health`: 응답 예(9장). `state`·`t`·`loop`는 `hello.playback`과 같은 뜻, `sessions`는 모든 구역 WebSocket 접속 수, `last_tick_ms`·`max_tick_ms`는 tick 1번(판정+방송) 처리 시간 ms(tick 전 `null`, max는 서버 시작부터).
8. 6절: "일시정지·이동은 `playback` 메시지를 따라 영상도 같이 멈추거나 옮긴다." 삭제. "`playback`(반복으로 0)을 받으면 영상도 0으로 옮긴다."로 바꾼다.
9. 8절 yml `replay`에 `slow-tick-ms: 500`.
10. 10절: 4번 초안 → "**닫힘 (S7)**: 재생 제어를 두지 않아 재생 상태는 서버가 정한다". 안건 추가: 22 "재생 제어 REST 삭제 (실시간 CCTV 전제). 화면 재생 버튼은 서버로 보내지 않음, `paused` 처리 불필요" 초안 "5절", 나예린. 23 "`GET /api/zones` 원소 키 (`duration_s` 제외)" 초안 "5.1절", 나예린.

### 11.3 `server/README.md`
- 44줄 "반복·이동 뒤 처음 4초는 평균이 없다." → "반복 뒤 처음 4초는 평균이 없다."
- `## 알림 확인 (S6)` 아래에 추가:
````markdown
## 조회와 서버 상태 (S7)
- 재생은 실시간 CCTV처럼 끊김 없이 흐른다. 재생 제어 API는 없다 (`docs/api-spec.md` 5절).
- 카메라·구역 목록: `GET /api/zones` → `[{"zone_id","camera_id","video_id"}]`.
- 구역 meta: `GET /api/zones/{zone_id}/meta` (타임라인 meta 그대로, `hello.meta`와 같음). 없는 구역은 `404`.
- 서버 상태: `GET /api/health` → 구역별 재생 상태(`state`·`t`·`loop`), 접속 수 `sessions`, tick 처리 시간 `last_tick_ms`·`max_tick_ms`.
- tick 1번(판정+방송) 처리가 `crowdsight.replay.slow-tick-ms`(500 ms)를 넘으면 WARN `tick 처리가 느림`이 남는다.
- 확인 예 (Git Bash): `curl http://localhost:8080/api/zones`, `curl http://localhost:8080/api/health`
````

## 12. TDD 단계
공통 (Git Bash, `server/`):
```bash
cd /c/Users/Woori/Desktop/project/Triple-Y/server && JAVA_HOME="/c/Program Files/Eclipse Adoptium/jdk-21.0.13.9-hotspot" ./gradlew test --tests '<패턴>' --no-daemon
```
> **에이전트는 `bootRun`을 실행하지 않는다** (포그라운드·백그라운드 모두). 확인은 `test`·`build`로 한다.

각 단계의 Red는 "테스트 먼저 작성 → 컴파일 실패 또는 단언 실패 확인"이다.

| 단계 | 할 일 (Red → Green) | `--tests` | 완료 조건 |
|---|---|---|---|
| 0 | 브랜치 이름 바꾸기 `git branch -m feat/server-playback-api feat/server-zones-health`, `git log --oneline -1`이 `d5281e3` | — | `git status --short`에 `?? CLAUDE.local.md`·`?? docs/roadmap.md`·`?? docs/plans/server_s7_zones_health_plan.md`만. 시작 전 전체 `./gradlew test --no-daemon` 통과 |
| 1 | `CrowdsightPropertiesTest`(`defaults`, +3), `bindsDefaultSlowTickMs`, `TestProperties`(`SLOW_TICK_MS`, `full`) → `Replay.slowTickMs`, yml `replay.slow-tick-ms` | `'com.tripley.crowdsight.config.*'` 다음 `'com.tripley.crowdsight.CrowdsightServerApplicationIntegrationTest'` | config 기존 + 3메서드, 앱 통합 +1 통과 |
| 2 | `TickStatsTest` → `TickStats`. `ReplaySchedulerTest` +1·생성자 5곳 → `ReplayScheduler`(`tickStats`, WARN) | `'com.tripley.crowdsight.replay.*'` | replay 전체 통과 (`ReplaySchedulerIntegrationTest` 포함) |
| 3 | (결정 #8 승인 시) `MessageFactoryTest` CsvSource에서 PAUSED 행 삭제 → `PlaybackState`에서 `PAUSED` 삭제. 4.4절 Javadoc·주석 정정. 테스트 기대가 바뀌지 않는 정리라 Red 없음(전후 통과) | `'com.tripley.crowdsight.ws.*'` 다음 `'com.tripley.crowdsight.replay.*'` 다음 `'com.tripley.crowdsight.grade.*'` 다음 `'com.tripley.crowdsight.alert.*'` | 모두 통과, `grep -rn 'S7\|이동\|PAUSED\|paused' src/main` 출력 없음 |
| 4 | `ZoneControllerTest` → `MessageFactory.stateName` 공개, `ZoneSummary`, `ZoneController` | `'com.tripley.crowdsight.api.ZoneControllerTest'` | 3메서드 통과 |
| 5 | `HealthControllerTest` → `ZoneHealth`, `HealthResponse`, `HealthController` | `'com.tripley.crowdsight.api.HealthControllerTest'` | 3메서드 통과 |
| 6 | `ZoneControllerIntegrationTest` | `'com.tripley.crowdsight.api.ZoneControllerIntegrationTest'` | 5메서드 통과 |
| 7 | `ZoneWebSocketIntegrationTest.healthCountsSessions` | `'com.tripley.crowdsight.ws.ZoneWebSocketIntegrationTest'` | 기존 10 + 1 통과 |
| 8 | 회귀: api·ws·alert 전체 | `'com.tripley.crowdsight.api.*'` 다음 `'com.tripley.crowdsight.ws.*'` 다음 `'com.tripley.crowdsight.alert.*'` | S3~S6 테스트 모두 통과 |
| 9 | 전체 실행 | 없음 (`./gradlew test --no-daemon`) | 모든 테스트 통과. `server/logs/`가 생기지 않았다 |
| 10 | README(11.3절), 11.1·11.2절 문서 정정 | — | 문구만 |
| 11 | 전체 검증 (아래 표) | — | 모두 기대대로 |

11단계 검증:

| # | 명령 (`server/`) | 기대 |
|---|---|---|
| 1 | `JAVA_HOME=… ./gradlew clean build --no-daemon` | `BUILD SUCCESSFUL` |
| 2 | `grep -h -o 'tests="[0-9]*" skipped="[0-9]*" failures="[0-9]*" errors="[0-9]*"' build/test-results/test/*.xml` | 모든 줄 `failures="0" errors="0"` |
| 3 | `ls logs 2>/dev/null` | 출력 없음 |
| 4 | `grep -rn 'S7' src/main` | 출력 없음 (yml 주석에도 넣지 않는다) |
| 5 | `grep -rn '이동' src/main` | 출력 없음 (seek 흔적 정리) |
| 6 | `grep -rn 'PAUSED\|paused' src` | 출력 없음 (결정 #8 승인 시) |
| 7 | `grep -rn 'PostMapping\|playback' src/main/java/com/tripley/crowdsight/api` | `AlertController.java` 2줄(import, ack `@PostMapping`)만 (재생 제어 없음) |
| 8 | `grep -rn 'nanoTime' src/main` | `ReplayScheduler.java`만 (경과 시간) |
| 9 | `grep -rnE 'Instant\.now\|currentTimeMillis\|LocalDate\.now\(\)' src/main` (표 안 `\|`는 `|`) | 출력 없음 |
| 10 | `grep -rn 'springframework' src/main/java/com/tripley/crowdsight/replay/ZonePlayer.java src/main/java/com/tripley/crowdsight/replay/ZoneRuntime.java src/main/java/com/tripley/crowdsight/grade` | 출력 없음 |
| 11 | `grep -rn 'import com.tripley.crowdsight.\(ws\|api\)' src/main/java/com/tripley/crowdsight/replay` | 출력 없음 (순환 없음) |
| 12 | `grep -rnE '500\b' src/main/java` | 출력 없음 (기준은 yml에만) |
| 13 | `grep -rnE '@(Data\|Getter\|Setter\|Builder\|Value\|AllArgsConstructor\|NoArgsConstructor)\b' src` | 출력 없음 |
| 14 | `grep -rn 'com.fasterxml.jackson.databind' src` | 출력 없음 |
| 15 | `grep -rnP '\t' src README.md` | 출력 없음 |
| 16 | 바뀐 `.java` 파일에 120자 초과 줄 없음 (문자 수 기준) | 출력 없음 |
| 17 | stage 뒤 `git -C .. ls-files --eol server \| grep -v 'i/lf'` | `gradle-wrapper.jar`, `gradlew.bat`만 |
| 18 | `git -C .. status --short` | `CLAUDE.local.md`·`docs/roadmap.md`가 stage되지 않음, `server/logs/` 없음 |

## 13. 커밋 제안 (커밋·푸시·PR은 사용자가 요청할 때만)
1. `feat: 느린 tick 기준과 tick 처리 시간 기록` (`CrowdsightProperties.Replay`, yml, `TestProperties`, `TickStats`, `ReplayScheduler`, 설정·replay 테스트)
2. `refactor: 쓰지 않는 일시정지 상태 삭제와 재생 제어 주석 정리` (`PlaybackState`, `MessageFactoryTest`, 4.4절 Javadoc·주석. 결정 #8 반려 시 주석만)
3. `feat: 카메라·구역 목록, meta, health 조회 API (S7)` (`api/`, `MessageFactory.stateName`, api·ws 테스트)
4. `docs: S7 계획 추가, 재생 제어 삭제 반영 (api-spec·구현 계획·README)`
- `docs/roadmap.md`는 올리지 않는다(사용자 개인 확인용, 11-16 사용자 지시).

## 14. PR 설명 (초안)
제목: `feat: 카메라·구역 목록, meta, health 조회 API (S7)` / 기준 `main` ← `feat/server-zones-health`

> [!NOTE]
> **#50·#51 병합 전 diff**
> 이 브랜치는 `feat/server-alert-ack`(S6) 위에서 만들었다. #50(S5)·#51(S6)이 `main`에 병합되기 전에는 그 커밋(S5 `efe29ff`, `755c880`; S6 `be6ec26`, `2c8f6ad`, `d5281e3`)이 이 PR에도 보인다. S7 변경은 그 뒤 커밋들이다.
> 권장 병합 순서: **#50 → #51 → 이 PR**. 앞 PR이 병합되면 이 PR의 diff는 S7 커밋만 남는다.

- 목적: 영상을 실시간 CCTV로 보는 전제에서, 화면이 고를 카메라 목록과 셀 배치(`meta`)를 REST로 주고, 30분 반복 시험(E8) 중 서버 상태·tick 처리 시간을 `/api/health`로 본다.
- 변경:
  - `GET /api/zones`(`zone_id`, `camera_id`, `video_id`), `GET /api/zones/{zone_id}/meta`(원본, 없는 구역 404), `GET /api/health`
  - `TickStats`: tick 처리 시간 last·max(`System.nanoTime`), `crowdsight.replay.slow-tick-ms`(500) 넘으면 WARN
  - 재생 제어 REST는 만들지 않음(api-spec 5절 삭제). 쓰지 않는 `PlaybackState.PAUSED` 삭제, seek를 전제한 주석 정리
- 바뀌지 않은 것: WS 메시지 키, `hello.schema_version` `"0.2"`, 판정·알림 규칙, 알림 확인 API, 재생 동작.
- 출력 예시: 계획 9장.

> [!IMPORTANT]
> **CS 이슈**
> | **주제** | **내용** |
> |---|---|
> | **단일 작성자(single writer)와 volatile 가시성** | 처리 시간은 재생 스레드만 쓰고 요청 스레드가 읽는다. 쓰는 스레드가 하나라 `volatile`로 충분하다(읽기-비교-쓰기 경쟁 없음) |
> | **단조 시계(monotonic clock)** | 처리 시간은 `System.nanoTime()` 차이. 벽시계(`Clock`)는 NTP 보정·시간대 변경에 뒤로 갈 수 있어 경과 시간에 쓰지 않는다 |
> | **스레드 한정(thread confinement)** | 판정기는 재생 스레드 전용 그대로다. REST는 이미 `synchronized`인 `snapshot()`과 Concurrent 맵만 읽는다. 잠금을 더하지 않는다 |
> | **공유 가변 상태 줄이기** | 화면이 재생을 바꾸지 않으므로 재생 상태를 쓰는 스레드는 재생 스레드 하나다. 제어 경쟁·방송 순서 문제가 생기지 않는다 |
> | **헬스 체크(liveness)** | 응답 자체가 살아 있다는 신호라 `status`는 늘 `UP`. Actuator 대신 필요한 값(재생 `t`, 접속 수, tick 시간)만 직접 낸다 |
> | **쓰지 않는 상태 지우기** | 만드는 곳이 없는 `PAUSED`를 지워 상태 기계를 `PLAYING → ENDED` 하나로 줄인다 |

| 선택 | 대안 | 고른 이유 |
|---|---|---|
| 재생 제어 없음 | 공용 재생 제어 REST | 실시간 CCTV는 멈추거나 되돌릴 수 없다. 공용 일시정지는 판정·알림을 모두 멈춘다 |
| `/api/zones`에 `duration_s` 없음 | 계획의 `duration_s` | 카메라 목록이다. 길이는 녹화 재생 값 |
| 직접 만든 `/api/health` | Spring Boot Actuator | 의존성 없이 필요한 값만 |
| 느린 tick 기준을 설정으로 | 코드 상수 500 | CLAUDE.md 기준값은 설정 한 곳 |
| 오류 본문 Spring 기본 | ProblemDetail 설정 | 새 400이 없다. 필요해지면 그때 |

리뷰 요청:
- 재생 제어 삭제와 api-spec 5절 교체 (나예린 님: 화면 재생 버튼을 서버로 보내지 않음)
- `/api/zones` 키(`duration_s` 제외), `PAUSED` 삭제

남은 일:
- G2: 30분 반복 시험에서 `/api/health` 확인
- 화면: `/api/zones`로 카메라 목록, 재생 제어 UI는 만들지 않음 (나예린 님)

## 15. 위험·가정·`[토론]`
| 위험 | 대응 |
|---|---|
| 화면이 재생 제어를 계획했을 수 있다 | `web/src`에 서버 재생 REST 호출이 없다(0장). api-spec 10절 22번으로 나예린 님께 알린다 |
| 시연에서 원하는 장면으로 옮길 수 없다 | 실시간 CCTV 전제상 의도된 제약이다. 장면 시작점이 필요하면 타임라인을 장면 길이로 자르거나 영상마다 카메라로 등록한다(합의 후, G2 뒤) |
| `PAUSED` 삭제가 화면 코드와 어긋난다 | 화면은 아직 v0.2 `playback`을 처리하지 않는다(0장). 값 집합이 줄어드는 것이라 키는 그대로 |
| `ReplaySchedulerTest` 생성자 5곳 변경 누락 | 컴파일 실패로 바로 드러남(2단계) |
| 느린 화면이 계속 있으면 매 tick WARN이 쌓인다 | 느린 세션은 2초 뒤 닫힌다(결정 기록 1). 반복되면 로그로 원인 확인 |
| 인증이 없어 같은 네트워크의 누구나 조회할 수 있다 | 조회 값은 셀·구역 집계뿐(개인정보 없음). 시연은 같은 PC·내부망(가정). 운영 전 인증 |
| `healthCountsSessions`가 hello 직후 접속 수를 읽어 0이 나온다 | hello 전송 뒤 방송 대상에 넣으므로 Awaitility로 1을 기다린다(8.8절) |

가정:
- (가정) 영상은 실시간 CCTV 피드를 흉내 낸다. 반복은 계속 들어오는 피드다.
- (가정) `status`는 늘 `"UP"`. 타임라인이 틀리면 서버가 아예 뜨지 않으므로 DOWN 상태가 없다.
- (가정) tick 처리 시간 max는 서버 시작부터 누적(초기화 API 없음).

결정 (조영준, 11-16 확정. 모두 추천안):
| # | 안건 | 결정 |
|---|---|---|
| 1 | `GET /api/zones` 원소에서 `duration_s` 빼기 | 뺀다 (1.2 #3) |
| 2 | `PlaybackState.PAUSED` 삭제 | 지운다 (1.2 #8) |
| 3 | api-spec 4.5 오류 본문 `[토론]`을 "404 본문 없음, 400 Spring 기본"으로 닫기 | 닫는다 (1.2 #10) |

`[토론]`:
| # | 안건 | 초안 | 누구와 |
|---|---|---|---|
| 1 | 재생 제어 REST 삭제, 화면 재생 버튼을 서버로 보내지 않음 | 1.1절, api-spec 5절 | 나예린 |
| 2 | `/api/zones` 키 (`zone_id`, `camera_id`, `video_id`) | 1.2 #3 | 나예린 |
| 3 | `slow-tick-ms` 500 ms와 health `max_tick_ms`를 E8 기록에 쓸지 | 1.2 #6 | 이유노 |

## 16. 변경 이력
| 버전 | 날짜 | 내용 |
|---|---|---|
| v1 | 11-13 | `server_s7_playback_api_plan.md`: 재생 제어 REST(`play`·`pause`·`seek`·`loop`, 다음 tick 반영), `/api/zones`·`/meta`·`/health`, ProblemDetail 400 |
| v1 점검 1차 | 11-16 | 이동 직후 멈춤 프레임 누락 수정 등 9건 반영 |
| v2 | 11-16 | 사용자 결정(영상 = 실시간 CCTV, 시연용 기능 금지)으로 재생 제어 삭제. 이 문서로 대체하고 v1 파일 삭제. 브랜치 `feat/server-zones-health`. 남은 범위: 카메라·구역 목록(`duration_s` 제외), `meta`, `health`, `TickStats`. `PAUSED` 삭제·주석 정리 추가. ProblemDetail 설정 빼고 오류 본문 `[토론]`을 닫는 안 |
| v2 확정 | 11-16 | 사용자 점검 완료. 결정 1~3(`duration_s` 제외, `PAUSED` 삭제, 오류 본문 `[토론]` 닫기) 추천안대로 확정 |
