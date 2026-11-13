# 서버 S5 알림 `alert`와 미확인 알림 구현 계획 (`feat/server-alert`)

| 항목 | 내용 |
|---|---|
| 작성일 | 2026-11-13 |
| 기준 | `docs/plans/server_impl_plan.md`(1.1·1.2절, 2장 S5·S6, 4장 설정, 5장 동시성, 6장 null, 9장 가정·`[토론]` 3), `docs/api-spec.md` v0.2(3.1 `hello.unacked_alerts`, 3.3 `alert`, 4.2 초기화, 4.5 S6 확인 기록, 7절 E8, 10절 9번), `docs/plans/server_s3_ws_plan.md`(1장 #5·#14, 8장 S5 행), `docs/plans/server_s4_instability_inflow_plan.md`(8장 S5 행, 12장 `[토론]` 3), `docs/plans/server_s2_grade_plan.md`(7장 S5 행), `docs/proposal-detail.md` 4.4(비상 알림·재전송)·5.4(알림 시퀀스·지연 예산) |
| 대상 | `server/` (`main` `3ce4601`(S0~S4, S3 리뷰 반영 포함, #49)에서 분기한 `feat/server-alert`), `docs/plans/`, `docs/api-spec.md`(보충) |
| 범위 | 알림 판정(`GRADE_UP`·`INSTABILITY`·`INFLOW`, 올라가는 순간만), 알림 ID 발급, 구역별 미확인 알림 저장(상한 `crowdsight.unacked-alert-limit`), WS `alert` 메시지(같은 tick의 `zone_state` 다음, 같은 `frame_ts`), `hello.unacked_alerts` 실제 값. **확인(ack) REST·`logs/alerts.jsonl`(S6), 재생 제어 REST(S7) 없음** |
| 상태 | 계획. 사용자 사전 승인(2026-11-13) |

## 0. 확인한 사실 (코드·문서·jar로 확인)
- 작업 트리:
  - 브랜치 `feat/server-alert`, `main` `3ce4601`과 같다. untracked 파일은 `CLAUDE.local.md`와 이 계획 문서다. `CLAUDE.local.md`는 stage하지 않는다.
  - PR은 `main`을 기준으로 연다(쌓인 PR 아님).
- S4 코드 상태 (S5가 붙는 자리):
  - `ZoneRuntime(ZonePlayer, ZoneGrader)`. `evaluate(tick)`는 `tick.discontinuity()`면 `grader.reset()` 뒤 `new ZoneStep(tick, grader.evaluate(frame))`. Javadoc에 "S5에서 AlertDetector를 더한다"가 있다.
  - `ZoneStep(Tick tick, ZoneEvaluation evaluation)`. `new ZoneStep(`는 `ZoneRuntime` 한 곳뿐이다(테스트에도 없음).
  - `new ZoneRuntime(`: main `ZoneRegistry.register` 1곳, 테스트 `ZoneRuntimeTest.runtime`, `ReplaySchedulerTest.runtime`, `MessageFactoryTest.fixtureRuntime`, `MessageJsonTest.helloMetaPassthrough` 4곳.
  - `ZoneEvaluation(t, zoneGrade, maxDensity, inflowAvg, inflowAlert, cells)`, `CellEvaluation(cellId, grade, gradePred60s, eligible, unstable, state)`. 둘 다 Javadoc에 "S5 입력"이라고 적혀 있다. `unstable`이면 `state().pressure()`는 기준(> 0)을 넘은 non-null 값이다(`InstabilityTracker`).
  - `InflowMonitor`: 경보가 꺼짐 → 켜짐으로 바뀌는 초는 조건이 참인 초다. 조건에 `average != null`이 있으므로 그 초의 `inflowAvg`는 non-null이다.
  - `ReplayScheduler.tickZone`: `zone.tick()` → `pollStateChange()` → `broadcaster.playback` → DEBUG 로그 → `broadcaster.zoneState(zoneId, step)`.
  - `ZoneBroadcaster`(replay 패키지 포트): `playback(zoneId, snapshot)`, `zoneState(zoneId, step)`. Javadoc: "replay가 ws에 의존하지 않도록".
  - `WsZoneBroadcaster.zoneState`는 `messages.zoneState(zoneId, step, messages.frameTs())`로 tick마다 `frame_ts`를 한 번 만든다. `MessageFactory.frameTs()` Javadoc: "한 tick의 zone_state와 alert(S5)는 같은 값을 쓴다".
  - `MessageFactory.hello(ZoneRuntime)`는 `unackedAlerts`에 `List.of()`를 넣는다. 호출: main `ZoneWebSocketHandler.afterConnectionEstablished` 1곳, 테스트 `MessageFactoryTest` 2곳, `MessageJsonTest` 3곳.
  - `HelloMessage.unackedAlerts`는 `List<Object>`이고 Javadoc에 "S5에서 List&lt;AlertMessage&gt;로 바꾼다"가 있다.
  - `ZoneSessions.join`: Tomcat 속성 → 감싸기 → hello 전송 → 집합 추가 → `isOpen` 재확인. hello가 늘 첫 메시지다. 이 순서가 7.3절 경쟁 분석의 전제다.
  - `CrowdsightProperties(timelineDir, timelineFiles, timeZone, replay, grade, instability, inflow, ws, corsOriginPatterns)`. 직접 만드는 곳은 `TestProperties.full` 하나다. 키가 빠진 기본형은 0으로 묶이고 compact constructor가 거부한다(S2 결정 #2).
  - `application.yml` 맨 위 주석: `# crowdsight.* 설정은 그 값을 읽는 클래스와 같은 PR에서 추가한다 (S6: alert-log)`.
  - `ClockConfig`가 `Clock.system(props.clockZone())` 빈을 만든다(Asia/Seoul).
  - `server/README.md` 절: 준비, 실행, WebSocket (S3), 판정 기준 (S4), 타임라인 파일, IDE.
- fixture `valid_v02.json` 판정 결과(S3 0장, S4 0장 표): 구역 등급은 t0~t3 NORMAL, t4 CAUTION. `unstable`은 모두 false, 유입 경보는 꺼져 있다. → **fixture로는 알림이 하나도 생기지 않는다.** 그래서 S3·S4의 `zone_state` 예시와 통합 테스트 기대값은 그대로다. 알림은 합성 타임라인(`timelineWithDensity`)과 손으로 만든 `ZoneEvaluation`으로 시험한다.
- 테스트 도구: Mockito 5.23.0(Gradle 캐시). 기본 mock maker가 inline이라 `final` 클래스도 mock할 수 있다(`ReplaySchedulerTest`가 `final class ZonePlayer`를 mock한다).
- JDK: `ZonedDateTime.now(clock)`은 `clock.instant()`를 한 번 부른다. 그래서 부를 때마다 1 ms씩 가는 시험 시계로 "`frame_ts`를 tick마다 한 번만 만든다"를 확인할 수 있다(6.7절).
- api-spec v0.2:
  - 3.1 `hello.unacked_alerts`: "재접속하면 미확인 알림을 다시 받는다". 형식은 3.3 `alert`와 같다.
  - 3.3 `alert` 키: `type, alert_id, zone_id, t, frame_ts, level, reason, message, value, cell_ids`. `t`·`frame_ts`는 같은 초 `zone_state`와 같고, 한 초 안에서는 `zone_state` 다음에 `alert`가 온다.
  - 3.3 `GRADE_UP`: 경계 이상이고 이번 사건에서 보낸 가장 높은 단계보다 높을 때만. 경계 아래로 내려가면 사건 끝. 예: N, C, A, CR, A, CR, C, A → 3번째·4번째·8번째.
  - 3.3 `cell_ids`(meta 순서): `GRADE_UP` = 판정 대상 셀 중 등급이 `level` 이상, `INSTABILITY` = 불안정이 된 판정 대상 셀(가정), `INFLOW` = `[]`(가정).
  - 3.3: `INFLOW`·`INSTABILITY`는 조건이 풀리기 전에는 다시 보내지 않는다. 주의로 오르는 것은 알림 없음.
  - 3.3·10절 9번: 불안정은 `INSTABILITY`(t2)와 `GRADE_UP` 심각(t3)을 둘 다 만든다. 줄일지는 `[토론]`.
  - 4.2: 반복·이동 때 알림 사건 상태도 초기화한다. 그래서 반복할 때마다 같은 알림이 다시 온다(가정).
  - 4.5: 확인 기록·`acked_at`·재시작 시 미확인 목록 비움은 S6 범위다. 미확인 알림은 메모리에만 둔다(DB 없음, 기획서 5.1).
  - 7절: `onset_t`·`onset_ts`는 합의 전에는 넣지 않는다.
- `docs/proposal-detail.md`: 4.4 "알림은 DB에 저장하고, 다시 연결되면 확인하지 않은 알림을 재전송한다", 5.4 지연 예산 합계 ≤ 3.0초(난류 ≤ 5.0초), 메시지마다 `frame_ts`. MVP는 DB 대신 메모리 + S6 로그 파일이다(기획서 5.1, api-spec 4.5).
- `server_impl_plan.md` 2장 S5 초안과 다른 점(1장 결정에서 고르고 9장에서 정정): `AlertDetector(zoneId, ids, clock)` → 인자 없음, `Alert.value` `double` → `Double`, `AlertStore`의 `find`·`ack`는 S6, 구역당 100은 상수 → 설정, `ZoneRuntimeTest.alertAfterState`·`thirtyMinuteLoop`는 `WsZoneBroadcasterTest`로.

## 1. 이번 계획에서 정한 것 (계획 대비)
| # | 항목 | 결정 | 이유 |
|---|---|---|---|
| 1 | 패키지 | `alert/`: `AlertReason`, `AlertEvent`, `Alert`, `AlertDetector`, `AlertIdGenerator`(패키지 전용), `AlertStore`. `ws/message/AlertMessage` | 계획 1.1절. `AlertDetector`·`AlertEvent`·`Alert`는 Spring 없음. `AlertStore`만 `@Component` |
| 2 | 판정과 발급을 나눔 | `AlertDetector.detect(ZoneEvaluation)` → `List<AlertEvent>`(무엇이 생겼나: level·reason·message·value·cell_ids). ID·`frame_ts`·저장은 `AlertStore.issue(zoneId, t, frameTs, event)` → `Alert` | 계획 초안은 `AlertDetector(zoneId, ids, clock)`가 `frame_ts`까지 만들었다. 그러면 `zone_state`의 `frame_ts`(ws가 만듦)와 값이 달라진다(api-spec 3.3 위반). `frame_ts`는 보내는 쪽 값이므로 보내는 곳에서 한 번 만들고 둘이 나눠 쓴다(S3 결정 #14) |
| 3 | 판정기 위치 | `ZoneRuntime`이 `AlertDetector`를 직접 만들어 가진다(생성자 인자 없음). 불연속이면 `grader.reset()`과 함께 `reset()`. `ZoneStep(tick, evaluation, alerts)` | S2 계획 7장 "ZoneRuntime이 AlertDetector 보유, 불연속이면 reset, ZoneStep에 알림 목록". 판정기는 설정이 없어(기준 = 등급) 주입할 것이 없다. `ZoneRuntime` 생성자가 그대로라 호출 5곳이 바뀌지 않는다 |
| 4 | 발급·전송 위치 | `WsZoneBroadcaster.zoneState`: `frameTs` 1번 → `zone_state` 전송 → 알림마다 [`AlertStore.issue` → `alert` 전송] | S3 계획 8장 "S5: ZoneBroadcaster, WsZoneBroadcaster — 같은 tick frame_ts로 zone_state → alert 순서". `ZoneBroadcaster` 인터페이스·`ReplayScheduler`는 바뀌지 않는다. replay가 ws(`FrameTimestamps`)에 의존하지 않는다 |
| 5 | `GRADE_UP` | 구역 등급 < ALERT이면 사건 끝(`sentPeak` = null). ≥ ALERT이고 `sentPeak`이 null이거나 더 높으면 보내고 `sentPeak` = 그 등급. level = 지금 등급, value = `maxDensity`, cell_ids = 판정 대상 셀 중 등급 ≥ level(meta 순서), message = `"구역 등급이 {직전 초 구역 등급} → {지금}로/으로 올랐다"` | api-spec 3.3 그대로. 문구의 "앞 등급"은 직전 초 구역 등급이다(예시 "주의 → 경계"). `sentPeak` 규칙이면 앞 등급은 늘 지금보다 낮다(4.1절) |
| 6 | `INSTABILITY` | "판정 대상(`eligible`) 셀 중 `unstable`이 하나라도 있음"이 거짓 → 참인 초에 1번. level CRITICAL, value = 그 셀들의 최대 `pressure`, cell_ids = 그 셀들. 모두 풀리면 다시 보낼 수 있다 | api-spec 3.3 "구역 단위", "해제 전 재전송 없음". 사건 중 다른 셀이 더 불안정해져도 보내지 않는다(심각 등급과 셀 `grade`로 보인다) |
| 7 | `INFLOW` | `inflowAlert` 거짓 → 참인 초에 1번. level CAUTION, value = `inflowAvg` 소수 3자리 반올림, cell_ids `[]` | api-spec 3.3. 평균은 `0.6599999999999999` 같은 값이 나온다(S4 12장 위험). 입력이 2자리이고 5개 평균이라 3자리면 정확한 값을 잃지 않는다(예: 0.775) |
| 8 | 한 초 여러 알림 | 순서 `INSTABILITY` → `GRADE_UP` → `INFLOW` (심각도 높은 이유 먼저). ID도 이 순서로 붙는다 | 결정적 순서가 있어야 테스트·화면이 안정된다. 순서 자체는 `[토론]` 2 |
| 9 | `value` 타입 | `Double` | CLAUDE.md "없을 수 있는 숫자는 Double". `GRADE_UP`의 `maxDensity`는 `Double`이고 방어용 null 밀도 셀만 있으면 null이 될 수 있다(검증기가 막지만 `ZoneEvaluation` 타입이 `Double`). 반올림·언박싱 NPE를 피한다 |
| 10 | 알림 ID | `a-yyyyMMdd-NNNN`. 번호는 서버 시작부터 1씩(구역 공통, 날짜가 바뀌어도 이어짐), 날짜는 주입한 `Clock`의 날짜(Asia/Seoul). 9999 다음은 5자리 | 계획 2장 S5. `AtomicLong`. 재시작하면 번호가 1로 돌아간다(`[토론]` 5) |
| 11 | 미확인 알림 저장 | `AlertStore`: 구역별 `ArrayDeque<Alert>`(오래된 것 앞), 모든 공개 메서드 `synchronized`, 읽기는 `List.copyOf` 복사본 | 7.2절. 쓰기 1 Hz 이하, 읽기는 접속 때뿐이라 잠금 경합이 없다. 덧붙이기 + 상한 넘으면 맨 앞 버리기 + 크기 확인을 한 번에 해야 해서 Concurrent 컬렉션 하나로는 원자성이 안 된다 |
| 12 | 상한 | `crowdsight.unacked-alert-limit: 100`(구역당). 넘으면 가장 오래된 것부터 버리고 WARN | 계획 2장 S5 "구역당 최대 100". 메모리 상한이므로 `ws.buffer-size-limit-bytes`처럼 설정에 둔다(CLAUDE.md 설정 규칙). 이 PR이 읽으므로 이 PR에서 추가한다 |
| 13 | S5의 "미확인" | S5에는 확인 기능이 없으므로 저장된 알림 = 미확인 알림. 메서드는 `issue`, `unacked(zoneId)` 2개만 | `find`·`ack`·확인 시각은 그 값을 쓰는 S6이 더한다(설정 규칙과 같은 원칙). 8장 |
| 14 | `hello.unacked_alerts` | `MessageFactory.hello(ZoneRuntime zone, List<Alert> unacked)`. 핸들러가 `AlertStore.unacked(zoneId)`를 넘긴다. 오래된 것부터 | `MessageFactory`는 상태 없이 남는다("재생·Tomcat 스레드에서 같이 불러도 된다" Javadoc 유지). 테스트는 목록만 넘기면 된다 |
| 15 | `HelloMessage.unackedAlerts` | `List<AlertMessage>` | S3 결정 #5. JSON 형식은 같다(배열) |
| 16 | `AlertMessage` | `ws/message` record `(type, alertId, zoneId, t, frameTs, level, reason, message, value, cellIds)`. `MessageFactory.alert(Alert)` | 다른 메시지와 같은 방식(`type` 상수 + 편의 생성자). 키 순서가 api-spec 3.3과 같다 |
| 17 | 알림 로그 | `AlertStore.issue`가 INFO `알림 zone= t= alert_id= reason= level= value=` | bootRun에서 알림을 확인할 곳. 상한으로 버리면 WARN |
| 18 | `hello.schema_version` | `"0.2"` 그대로 | `alert`·`unacked_alerts` 형식은 api-spec v0.2가 이미 정의했다 |
| 19 | 접속과 알림 발송의 경쟁 | 잠금을 더하지 않는다. 같은 알림을 hello와 `alert`로 두 번 받을 수 있고(화면이 `alert_id`로 거른다), 아주 드물게 하나를 놓칠 수 있다(재접속·S6 `GET .../alerts`로 복구) | 7.3절. 막으려면 hello 전송 동안 재생 스레드를 붙잡거나 S3 `join`을 고쳐야 한다. 창은 hello 전송 시간(ms)이고 알림은 몇 분에 한 번이다. `[토론]` 4 |
| 20 | 테스트 위치 | 판정 규칙은 `AlertDetectorTest`(손으로 만든 `ZoneEvaluation` + 실제 `ZoneGrader` 1개), 반복 재생은 `ZoneRuntimeTest`, 순서·`frame_ts` 공유·30분 상한은 `WsZoneBroadcasterTest`(새), hello 연결은 통합 테스트 | 계획 2장 표의 `ZoneRuntimeTest.alertAfterState`는 `ZoneRuntime`이 보내지 않으므로 그 자리에서 시험할 수 없다 |

## 2. 구조와 파일

### 2.1 추가·수정 파일
```text
server/
├─ README.md                                                     수정 (알림 절)
├─ src/main/resources/application.yml                            수정 (unacked-alert-limit)
├─ src/main/java/com/tripley/crowdsight/
│  ├─ config/  CrowdsightProperties                              수정 (unackedAlertLimit)
│  ├─ alert/   AlertReason, AlertEvent, Alert, AlertDetector, AlertIdGenerator, AlertStore      추가
│  ├─ replay/  ZoneStep (alerts), ZoneRuntime (AlertDetector), ZoneBroadcaster (Javadoc만)      수정
│  └─ ws/      MessageFactory (hello 인자, alert), WsZoneBroadcaster (발급·전송),
│              ZoneWebSocketHandler (hello에 미확인 알림)                                       수정
│      ws/message/ AlertMessage 추가, HelloMessage (List<AlertMessage>) 수정
└─ src/test/java/com/tripley/crowdsight/
   ├─ CrowdsightServerApplicationIntegrationTest                 수정 (+1)
   ├─ config/   CrowdsightPropertiesTest (+3, defaults), TestProperties (UNACKED_ALERT_LIMIT)
   ├─ alert/    AlertDetectorTest, AlertIdGeneratorTest, AlertStoreTest                         추가
   ├─ replay/   ZoneRuntimeTest (+1)
   └─ ws/       WsZoneBroadcasterTest 추가, MessageFactoryTest (1개 수정, +2),
                MessageJsonTest (hello 호출 3곳, +3), ZoneWebSocketIntegrationTest (1개 완화, +1)
docs/plans/server_s5_alert_plan.md                               (이 문서)
docs/plans/server_impl_plan.md                                   정정 (9장)
docs/api-spec.md                                                 보충 (9장)
```

### 2.2 1초 흐름 (S5, 바뀐 곳만 굵게)
```text
ReplayScheduler.tickAll() → tickZone(zone)                         (바뀌지 않음)
  ZoneRuntime.tick()
    ZonePlayer.tick()              → Tick(frame, discontinuity, wrapped)
    discontinuity이면 ZoneGrader.reset() **+ AlertDetector.reset()**
    ZoneGrader.evaluate(frame)     → ZoneEvaluation
    **AlertDetector.detect(eval)   → List<AlertEvent> (INSTABILITY → GRADE_UP → INFLOW)**
    → ZoneStep(tick, evaluation, **alerts**)
  [playback] → broadcaster.zoneState(zoneId, step)
    WsZoneBroadcaster.zoneState
      frameTs = messages.frameTs()                        ← tick마다 1번
      zone_state(frameTs) → JSON → ZoneSessions.broadcast
      **알림마다: AlertStore.issue(zoneId, t, frameTs, event) → Alert(ID 발급, 저장, INFO 로그)**
      **         alert(Alert) → JSON → ZoneSessions.broadcast**
접속: ZoneWebSocketHandler → **AlertStore.unacked(zoneId)** → MessageFactory.hello(zone, **unacked**) → join
```

### 2.3 의존 방향
```text
ws ──→ alert ──→ grade
 │       ↑
 └──→ replay ──→ grade
alert.AlertStore ──→ config (CrowdsightProperties)
```
- `replay`는 `alert`(`AlertDetector`, `AlertEvent`)를 쓴다. `alert`는 `replay`·`ws`를 모른다. 순환 없음.

### 2.4 스레드 규칙
| 클래스 | 누가 부르나 | 규칙 |
|---|---|---|
| `AlertDetector` | 재생 스레드(`ZoneRuntime.tick` 안) | 잠금 없음. `ZoneGrader`와 같다 |
| `AlertStore.issue` | 재생 스레드(`WsZoneBroadcaster`) | `synchronized` |
| `AlertStore.unacked` | Tomcat 스레드(hello), S6부터 REST 스레드 | `synchronized`, 불변 복사본을 준다 |
| `AlertIdGenerator.next` | `issue` 안 | `AtomicLong`. 잠금 안에서 불려 번호 순서 = 저장 순서 |
| `Alert`, `AlertEvent`, `AlertMessage` | 어디서나 | 불변 record(목록은 `List.copyOf`) |

## 3. 설정

### 3.1 `application.yml` (수정분)
`inflow:` 다음, `ws:` 앞에 넣는다. 맨 위 주석은 그대로(`(S6: alert-log)`).
```yaml
  unacked-alert-limit: 100                   # 구역당 미확인 알림 최대 개수. 넘으면 가장 오래된 것부터 버린다 (메모리 상한)
```

### 3.2 `config/CrowdsightProperties.java` (수정분)
```java
/**
 * ... (기존 설명)
 * alert-log는 그 값을 쓰는 PR(S6)에서 추가한다.
 *
 * ... (기존 @param)
 * @param inflow             유입 경보 설정 (crowdsight.inflow.*)
 * @param unackedAlertLimit  구역당 미확인 알림 최대 개수 (1 이상). 넘으면 가장 오래된 것부터 버린다
 * @param ws                 WebSocket 설정 (crowdsight.ws.*)
 * ...
 */
@ConfigurationProperties("crowdsight")
public record CrowdsightProperties(String timelineDir, List<String> timelineFiles, String timeZone, Replay replay,
                                   GradeSettings grade, InstabilitySettings instability, InflowSettings inflow,
                                   int unackedAlertLimit, Ws ws, List<String> corsOriginPatterns) {

    public CrowdsightProperties {
        // ... (inflow null 검사 뒤)
        if (unackedAlertLimit < 1) {     // 키가 없으면 0으로 묶여 여기서 거부된다
            throw new IllegalArgumentException(
                    "crowdsight.unacked-alert-limit 는 1 이상이어야 합니다: " + unackedAlertLimit);
        }
        // ... (ws 이하 그대로)
    }
```

### 3.3 `config/TestProperties.java` (수정분)
```java
    /** application.yml crowdsight.unacked-alert-limit 기본값과 같다 (bindsDefaultUnackedAlertLimit가 확인). */
    public static final int UNACKED_ALERT_LIMIT = 100;

    private static CrowdsightProperties full(String dir, List<String> files, long intervalMs, boolean loop,
                                             CrowdsightProperties.Ws ws) {
        return new CrowdsightProperties(dir, files, TIME_ZONE, new CrowdsightProperties.Replay(intervalMs, loop),
                GRADE, INSTABILITY, INFLOW, UNACKED_ALERT_LIMIT, ws, CORS);
    }
```
- 클래스 Javadoc "S3~S6이 성분을 늘리면 여기만 고친다"는 그대로 맞다.

## 4. 판정

### 4.1 `alert/AlertReason.java`, `alert/AlertEvent.java` (추가)
```java
package com.tripley.crowdsight.alert;

/** 알림 이유 (api-spec 3.3). JSON에는 이름 그대로 나간다. */
public enum AlertReason {
    /** 구역 등급이 경계·심각으로 오름. */
    GRADE_UP,
    /** 유입 경보가 켜짐. */
    INFLOW,
    /** 판정 대상 셀 중 하나라도 불안정이 됨 (구역 단위). */
    INSTABILITY
}
```
```java
package com.tripley.crowdsight.alert;

import java.util.List;
import java.util.Objects;

import com.tripley.crowdsight.grade.Grade;

/**
 * 한 초에 새로 생긴 알림 사건. ID·frame_ts·구역은 아직 없다 (AlertStore.issue가 붙인다).
 *
 * @param level   알림 등급 (GRADE_UP: 오른 등급, INFLOW: CAUTION, INSTABILITY: CRITICAL)
 * @param reason  알림 이유
 * @param message 화면에 보일 한국어 문구
 * @param value   GRADE_UP: 최대 밀도, INFLOW: 유입 비율 5초 평균(소수 3자리), INSTABILITY: 불안정 셀 최대 압력.
 *                방어용으로 null일 수 있다
 * @param cellIds 관련 판정 대상 셀 (meta 순서). INFLOW는 빈 목록
 */
public record AlertEvent(Grade level, AlertReason reason, String message, Double value, List<String> cellIds) {

    public AlertEvent {
        Objects.requireNonNull(level, "level");
        Objects.requireNonNull(reason, "reason");
        Objects.requireNonNull(message, "message");
        cellIds = List.copyOf(cellIds);
    }
}
```

### 4.2 `alert/AlertDetector.java` (추가)
```java
package com.tripley.crowdsight.alert;

import java.util.ArrayList;
import java.util.List;

import com.tripley.crowdsight.grade.CellEvaluation;
import com.tripley.crowdsight.grade.Grade;
import com.tripley.crowdsight.grade.ZoneEvaluation;

/**
 * 구역 1개의 알림 사건 판정 (api-spec 3.3). 매 초 판정 결과를 받아 새로 생긴 사건만 돌려준다 (올라가는 순간만).
 * GRADE_UP: 구역 등급이 경계 이상이고 이번 사건에서 보낸 가장 높은 단계보다 높을 때. 경계 아래로 내려가면 사건 끝.
 * INSTABILITY: 판정 대상 셀 중 불안정 셀이 없다가 생긴 초. 모두 풀리기 전에는 다시 보내지 않는다.
 * INFLOW: 유입 경보가 꺼져 있다가 켜진 초.
 * 한 초에 여러 개면 INSTABILITY → GRADE_UP → INFLOW 순서다. 주의로 오르는 것은 알림이 없다.
 * 스레드 규칙: detect·reset은 재생 스레드 하나만 부른다 (ZoneRuntime 안). 잠금 없음.
 */
public final class AlertDetector {

    private Grade lastGrade = Grade.NORMAL;   // 직전 초 구역 등급 (GRADE_UP 문구)
    private Grade sentPeak;                   // 이번 사건에서 보낸 가장 높은 GRADE_UP 등급. 사건이 없으면 null
    private boolean lastUnstable;             // 직전 초에 판정 대상 불안정 셀이 있었는지
    private boolean lastInflow;               // 직전 초 유입 경보

    /** 이번 초 판정 결과에서 새로 생긴 알림 사건. 없으면 빈 목록. */
    public List<AlertEvent> detect(ZoneEvaluation eval) {
        List<AlertEvent> events = new ArrayList<>(3);

        List<CellEvaluation> unstable = eval.cells().stream().filter(c -> c.eligible() && c.unstable()).toList();
        if (!unstable.isEmpty() && !lastUnstable) {
            events.add(instability(unstable));
        }
        lastUnstable = !unstable.isEmpty();

        Grade grade = eval.zoneGrade();
        if (grade.compareTo(Grade.ALERT) < 0) {
            sentPeak = null;                                  // 경계 아래: 사건 끝
        } else if (sentPeak == null || grade.compareTo(sentPeak) > 0) {
            events.add(gradeUp(eval, lastGrade, grade));
            sentPeak = grade;
        }
        lastGrade = grade;

        if (eval.inflowAlert() && !lastInflow) {
            events.add(inflow(eval.inflowAvg()));
        }
        lastInflow = eval.inflowAlert();

        return List.copyOf(events);
    }

    /** 사건 상태를 처음으로 되돌린다 (첫 프레임·반복·이동). 그래서 반복할 때마다 같은 알림이 다시 생긴다. */
    public void reset() {
        lastGrade = Grade.NORMAL;
        sentPeak = null;
        lastUnstable = false;
        lastInflow = false;
    }

    private static AlertEvent gradeUp(ZoneEvaluation eval, Grade from, Grade to) {
        List<String> cellIds = eval.cells().stream()
                .filter(c -> c.eligible() && c.grade().compareTo(to) >= 0)
                .map(CellEvaluation::cellId)
                .toList();
        String particle = to == Grade.CRITICAL ? "으로" : "로";   // 심각(받침 있음)·경계(받침 없음)만 온다
        String message = "구역 등급이 " + from.label() + " → " + to.label() + particle + " 올랐다";
        return new AlertEvent(to, AlertReason.GRADE_UP, message, eval.maxDensity(), cellIds);
    }

    private static AlertEvent instability(List<CellEvaluation> unstable) {
        List<String> cellIds = unstable.stream().map(CellEvaluation::cellId).toList();
        double maxPressure = unstable.stream()
                .mapToDouble(c -> c.state().pressure())   // unstable이면 pressure는 기준을 넘은 non-null 값
                .max()
                .orElseThrow();
        String message = "셀 " + String.join(", ", cellIds) + "에서 군중 불안정이 감지됐다";
        return new AlertEvent(Grade.CRITICAL, AlertReason.INSTABILITY, message, maxPressure, cellIds);
    }

    private static AlertEvent inflow(Double average) {
        Double value = average == null ? null : Math.round(average * 1000) / 1000.0;   // 소수 3자리
        return new AlertEvent(Grade.CAUTION, AlertReason.INFLOW, "구역으로 들어오는 인원이 몰린다", value, List.of());
    }
}
```
- 문구의 "앞 등급"이 지금 등급보다 늘 낮다: 직전 등급이 경계 아래면 지금(≥ 경계)보다 낮다. 직전 등급이 경계 이상이면 사건 중이라 `sentPeak` ≥ 직전 등급이고, 보내는 조건이 지금 > `sentPeak`이다.
- `grade.compareTo`: `CellEvaluation.grade`는 히스테리시스 등급이라 null이 아니다.
- `INFLOW` value null은 실제로 생기지 않는다(0장: 켜지는 초의 평균은 non-null). 타입만 막는다.

### 4.3 `replay/ZoneStep.java`, `replay/ZoneRuntime.java` (수정)
```java
/**
 * 구역 1개의 tick 한 번 결과.
 *
 * @param tick       재생 결과. S3가 wrapped(→ playback)와 통과 필드(inflow_ratio·count)에 쓴다
 * @param evaluation 이번 프레임 판정
 * @param alerts     이번 초에 새로 생긴 알림 사건 (INSTABILITY → GRADE_UP → INFLOW). ID·frame_ts는 보낼 때 붙인다
 */
public record ZoneStep(Tick tick, ZoneEvaluation evaluation, List<AlertEvent> alerts) {

    public ZoneStep {
        alerts = List.copyOf(alerts);
    }
}
```
```java
/**
 * 구역 1개의 재생기·판정기·알림 판정기를 묶는다. 불연속 tick(첫 프레임·반복·이동)이면 판정·알림 상태를 먼저 초기화한다.
 * 스레드 규칙: tick()은 재생 스레드만 부른다 (ZoneGrader·AlertDetector는 잠금 없음).
 * player()가 주는 ZonePlayer는 synchronized라 다른 스레드(S3 hello, S7 제어)에서 써도 된다.
 */
public final class ZoneRuntime {

    private final ZonePlayer player;
    private final ZoneGrader grader;
    private final AlertDetector alerts = new AlertDetector();   // 설정이 없어 주입하지 않는다

    // 생성자·zoneId()·player()·tick() 그대로

    private ZoneStep evaluate(Tick tick) {
        if (tick.discontinuity()) {
            grader.reset();
            alerts.reset();
        }
        ZoneEvaluation evaluation = grader.evaluate(tick.frame());
        return new ZoneStep(tick, evaluation, alerts.detect(evaluation));
    }
}
```
- `grader.evaluate`가 예외를 던지면(셀 불일치) 알림 상태도 바뀌지 않는다.
- `ZoneBroadcaster` Javadoc만 고친다: "`zoneState`: 한 초 판정 결과와 그 초 알림(`step.alerts()`). 구현은 같은 `frame_ts`로 `zone_state` 다음 `alert`를 보낸다".

## 5. 발급·저장

### 5.1 `alert/AlertIdGenerator.java` (추가, 패키지 전용)
```java
package com.tripley.crowdsight.alert;

import java.time.Clock;
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.util.Locale;
import java.util.Objects;
import java.util.concurrent.atomic.AtomicLong;

/**
 * 알림 ID a-yyyyMMdd-NNNN (api-spec 3.3). 번호는 서버 시작부터 구역 공통으로 1씩 늘고 날짜가 바뀌어도 이어진다.
 * 날짜는 주입한 Clock의 시간대 날짜다. 9999 다음은 5자리가 된다.
 * 스레드 규칙: AtomicLong이라 여러 스레드에서 불러도 번호가 겹치지 않는다.
 */
final class AlertIdGenerator {

    private static final DateTimeFormatter DATE = DateTimeFormatter.ofPattern("uuuuMMdd");

    private final Clock clock;
    private final AtomicLong sequence = new AtomicLong();

    AlertIdGenerator(Clock clock) {
        this.clock = Objects.requireNonNull(clock, "clock");
    }

    /** 다음 알림 ID. */
    String next() {
        return "a-" + LocalDate.now(clock).format(DATE) + "-"
                + String.format(Locale.ROOT, "%04d", sequence.incrementAndGet());
    }
}
```

### 5.2 `alert/Alert.java` (추가)
```java
package com.tripley.crowdsight.alert;

import java.util.List;

import com.tripley.crowdsight.grade.Grade;

/**
 * 발급한 알림 (api-spec 3.3). alert 메시지와 hello.unacked_alerts의 원본이다. S6 확인 기록의 sent_at은 frameTs다.
 *
 * @param alertId 알림 ID (a-yyyyMMdd-NNNN)
 * @param zoneId  구역 ID
 * @param t       알림이 생긴 프레임 t (같은 초 zone_state의 t)
 * @param frameTs 보낸 시각 (같은 초 zone_state의 frame_ts)
 * @param level   알림 등급
 * @param reason  알림 이유
 * @param message 한국어 문구
 * @param value   AlertEvent.value
 * @param cellIds 관련 셀 (meta 순서)
 */
public record Alert(String alertId, String zoneId, int t, String frameTs, Grade level, AlertReason reason,
                    String message, Double value, List<String> cellIds) {

    public Alert {
        cellIds = List.copyOf(cellIds);
    }
}
```

### 5.3 `alert/AlertStore.java` (추가)
```java
package com.tripley.crowdsight.alert;

import java.time.Clock;
import java.util.ArrayDeque;
import java.util.Deque;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

import org.springframework.stereotype.Component;

import com.tripley.crowdsight.config.CrowdsightProperties;

import lombok.extern.slf4j.Slf4j;

/**
 * 구역별 미확인 알림 (api-spec 3.1·3.3). 메모리에만 두고 서버를 재시작하면 비워진다 (api-spec 4.5).
 * 구역당 unacked-alert-limit개까지 두고, 넘으면 가장 오래된 것부터 버린다.
 * S5에는 확인 기능이 없어 저장한 알림이 곧 미확인 알림이다. find·ack는 S6이 더한다.
 * 스레드 규칙: issue는 재생 스레드, unacked는 Tomcat 스레드(hello)가 부른다. 모든 공개 메서드는 this로 잠근다.
 * 덧붙이기·상한 확인·맨 앞 버리기를 한 번에 해야 해서 Concurrent 컬렉션 대신 잠금을 쓴다. 쓰기는 1초에 몇 번 이하다.
 */
@Slf4j
@Component
public final class AlertStore {

    private final int limit;
    private final AlertIdGenerator ids;
    private final Map<String, Deque<Alert>> byZone = new HashMap<>();   // this 잠금 안에서만 읽고 쓴다

    public AlertStore(CrowdsightProperties props, Clock clock) {
        this.limit = props.unackedAlertLimit();
        this.ids = new AlertIdGenerator(clock);
    }

    /** 사건에 ID·구역·t·frame_ts를 붙여 저장하고 돌려준다. 같은 초 zone_state의 t·frame_ts를 넘긴다. */
    public synchronized Alert issue(String zoneId, int t, String frameTs, AlertEvent event) {
        Alert alert = new Alert(ids.next(), zoneId, t, frameTs, event.level(), event.reason(), event.message(),
                event.value(), event.cellIds());
        Deque<Alert> alerts = byZone.computeIfAbsent(zoneId, k -> new ArrayDeque<>());
        alerts.addLast(alert);
        log.info("알림 zone={} t={} alert_id={} reason={} level={} value={}", zoneId, t, alert.alertId(),
                alert.reason(), alert.level(), alert.value());
        if (alerts.size() > limit) {
            Alert dropped = alerts.removeFirst();
            log.warn("미확인 알림이 {}개를 넘어 가장 오래된 알림을 버림 zone={} alert_id={}", limit, zoneId,
                    dropped.alertId());
        }
        return alert;
    }

    /** 구역의 미확인 알림 (오래된 것부터). 불변 복사본이라 받은 뒤 바뀌지 않는다. 없는 구역은 빈 목록. */
    public synchronized List<Alert> unacked(String zoneId) {
        Deque<Alert> alerts = byZone.get(zoneId);
        return alerts == null ? List.of() : List.copyOf(alerts);
    }
}
```
- `@Component`이면서 `final`: `ZoneSessions`와 같다(프록시가 필요한 어노테이션이 없다). 생성자는 하나뿐이라 Spring이 그것을 쓴다.

## 6. 메시지와 전송

### 6.1 `ws/message/AlertMessage.java` (추가)
```java
package com.tripley.crowdsight.ws.message;

import java.util.List;

import com.tripley.crowdsight.alert.AlertReason;
import com.tripley.crowdsight.grade.Grade;

/**
 * 알림 메시지 (api-spec 3.3). 사건이 생긴 초에 그 초 zone_state 다음으로 보내고, hello.unacked_alerts에도 담는다.
 *
 * @param type    "alert"
 * @param alertId 알림 ID
 * @param zoneId  구역 ID
 * @param t       같은 초 zone_state의 t
 * @param frameTs 같은 초 zone_state의 frame_ts
 * @param level   알림 등급
 * @param reason  GRADE_UP·INFLOW·INSTABILITY
 * @param message 한국어 문구
 * @param value   최대 밀도·유입 5초 평균·최대 압력
 * @param cellIds 관련 셀 (meta 순서). INFLOW는 빈 배열
 */
public record AlertMessage(String type, String alertId, String zoneId, int t, String frameTs, Grade level,
                           AlertReason reason, String message, Double value, List<String> cellIds) {

    public static final String TYPE = "alert";

    public AlertMessage {
        cellIds = List.copyOf(cellIds);
    }

    /** type을 "alert"로 채운다. */
    public AlertMessage(String alertId, String zoneId, int t, String frameTs, Grade level, AlertReason reason,
                        String message, Double value, List<String> cellIds) {
        this(TYPE, alertId, zoneId, t, frameTs, level, reason, message, value, cellIds);
    }
}
```

### 6.2 `ws/message/HelloMessage.java` (수정분)
```java
 * @param unackedAlerts 미확인 알림 (오래된 것부터, api-spec 3.1)
 */
public record HelloMessage(String type, String schemaVersion, String zoneId, JsonNode meta, PlaybackView playback,
                           ThresholdsView thresholds, List<AlertMessage> unackedAlerts) {
    // compact constructor·편의 생성자: List<Object> → List<AlertMessage>만 바뀐다
```

### 6.3 `ws/MessageFactory.java` (수정분)
```java
    /** 접속한 화면에 보낼 hello. 재생 상태는 지금 snapshot, unacked는 AlertStore.unacked(zoneId)다. */
    public HelloMessage hello(ZoneRuntime zone, List<Alert> unacked) {
        ZonePlayer player = zone.player();
        ThresholdsView thresholds = new ThresholdsView(props.grade().density(), props.instability().pressure(),
                props.inflow().ratio());
        return new HelloMessage(API_SCHEMA_VERSION, zone.zoneId(), player.timeline().metaJson(),
                playbackView(player.snapshot()), thresholds, unacked.stream().map(this::alert).toList());
    }

    /** 발급한 알림 (api-spec 3.3). */
    public AlertMessage alert(Alert a) {
        return new AlertMessage(a.alertId(), a.zoneId(), a.t(), a.frameTs(), a.level(), a.reason(), a.message(),
                a.value(), a.cellIds());
    }
```
- 클래스 Javadoc("상태가 없어 재생 스레드와 Tomcat 접속 스레드에서 같이 불러도 된다")은 그대로 맞다.

### 6.4 `ws/WsZoneBroadcaster.java` (수정분)
```java
/**
 * 재생 결과를 메시지당 JSON 한 번으로 바꿔 그 구역 화면 모두에 보낸다.
 * zoneState: frame_ts를 tick마다 한 번 만들고, zone_state 다음에 그 초 알림을 발급(AlertStore)해 alert로 보낸다.
 * 화면이 없어도 알림은 발급·저장한다 (다음 hello의 unacked_alerts).
 * 스레드 규칙: 재생 작업에서만 불린다. 세션별 전송 안전은 ZoneSessions, 저장 안전은 AlertStore가 맡는다.
 */
@Component
@RequiredArgsConstructor
public class WsZoneBroadcaster implements ZoneBroadcaster {

    private final MessageFactory messages;
    private final ZoneSessions sessions;
    private final JsonMapper jsonMapper;
    private final AlertStore alerts;

    // playback 그대로

    @Override
    public void zoneState(String zoneId, ZoneStep step) {
        String frameTs = messages.frameTs();
        send(zoneId, messages.zoneState(zoneId, step, frameTs));
        for (AlertEvent event : step.alerts()) {
            Alert alert = alerts.issue(zoneId, step.evaluation().t(), frameTs, event);
            send(zoneId, messages.alert(alert));
        }
    }
```
- 저장(`issue`)을 그 알림 전송보다 먼저 한다. 그래서 그 사이 접속한 화면은 hello로 받거나 `alert`로 받는다(7.3절).

### 6.5 `ws/ZoneWebSocketHandler.java` (수정분)
```java
    private final ZoneRegistry zones;
    private final ZoneSessions sessions;
    private final MessageFactory messages;
    private final JsonMapper jsonMapper;
    private final AlertStore alerts;

    @Override
    public void afterConnectionEstablished(WebSocketSession session) throws Exception {
        Optional<ZoneRuntime> zone = zoneIdOf(session.getUri()).flatMap(zones::find);
        if (zone.isEmpty()) {
            // 그대로
        }
        ZoneRuntime runtime = zone.get();
        String hello = jsonMapper.writeValueAsString(messages.hello(runtime, alerts.unacked(runtime.zoneId())));
        sessions.join(runtime.zoneId(), session, hello);
    }
```
- 클래스 Javadoc에 "hello에는 그 구역 미확인 알림을 담는다 (api-spec 3.1)"를 더한다.

## 7. 판정 규칙·동시성·메모리 정리

### 7.1 알림 규칙 표
| 이유 | 켜는 순간 (edge) | 다시 보내는 조건 | level | value | cell_ids |
|---|---|---|---|---|---|
| `GRADE_UP` | 구역 등급 ≥ ALERT이고 (사건 없음 또는 > `sentPeak`) | 사건 중 더 높은 등급(경계 → 심각). 경계 아래로 내려가 사건이 끝난 뒤 다시 경계 이상 | 지금 구역 등급 | `maxDensity` | 대상 셀 중 등급 ≥ level |
| `INSTABILITY` | 대상 불안정 셀 없음 → 있음 | 대상 불안정 셀이 모두 풀린 뒤 다시 생김 | CRITICAL | 그 셀들의 최대 `pressure` | 그 초에 불안정인 대상 셀 |
| `INFLOW` | `inflowAlert` F → T | 꺼진 뒤(10초 연속 거짓) 다시 켜짐 | CAUTION | `inflowAvg` 3자리 | `[]` |
- 모두 "수준"이 아니라 "올라가는 순간(rising edge)"에만 보낸다. 같은 사건은 1번이다.
- 판정 대상이 아닌 작은 셀(< 2㎡)은 어느 알림에도 들어가지 않는다(결정 4, S4 결정 #8).
- 초기화: 첫 프레임·반복·이동(S7)에서 `AlertDetector.reset()`. 직후 등급은 NORMAL에서 다시 시작하므로 반복마다 같은 알림이 새 ID로 다시 생긴다(api-spec 4.2 가정). 미확인 목록은 초기화하지 않는다(확인 전 알림은 남는다).
- 한 tick 안 메시지 순서: [`playback`] → `zone_state` → `alert`(INSTABILITY → GRADE_UP → INFLOW). 모든 `alert`의 `t`·`frame_ts`는 그 `zone_state`와 같다.
- 지연(E8): `alert`의 `frame_ts`는 그 초 `zone_state`와 같다. 판정 → 전송 사이에 추가 대기가 없다. 히스테리시스 확인 지연(밀도 +1초, 불안정 +2초)은 api-spec 7절대로 따로 다룬다(`onset_*` 필드 넣지 않음).

### 7.2 미확인 알림 저장소 동시성
| 후보 | 판단 |
|---|---|
| **`synchronized` + `HashMap<String, ArrayDeque<Alert>>` + 복사본 읽기 (고름)** | 덧붙이기·상한 확인·맨 앞 버리기·ID 번호 붙이기가 한 잠금 안에서 원자적이다. 잠금 안 작업은 O(1)(읽기는 O(상한 100)). 쓰기 1 Hz 이하, 읽기는 접속 때뿐이라 경합이 없다. `Alert`는 불변이고 `List.copyOf`로 넘기므로 잠금을 놓은 뒤에도 안전하다(잠금 해제·획득이 happens-before를 만든다) |
| `ConcurrentHashMap` + `ConcurrentLinkedDeque` | 원소 단위로는 안전하지만 "더하고 101개면 맨 앞 빼기"가 원자적이지 않다. `size()`가 O(n)이고 약한 일관성이다. 두 스레드가 같이 쓰는 경우가 S6(ack)부터 생기면 더 복잡해진다 |
| `CopyOnWriteArrayList` | 읽기 잠금이 없지만 쓸 때마다 배열 복사, 맨 앞 지우기 O(n). 이득이 없다 |
| 재생 스레드 전용(잠금 없음) | hello(Tomcat 스레드)와 S6 REST가 읽어야 하므로 불가 |

### 7.3 접속(hello)과 알림 발송의 경쟁
- 접속 스레드: ① `unacked` 읽기 → ② hello 전송 → ③ 방송 집합에 추가(S3 `join`, hello가 늘 첫 메시지).
- 재생 스레드: ⓐ `issue`(저장) → ⓑ `alert` 방송(그때 집합에 있는 세션).
- 경우:
  - ⓐ가 ① 앞: hello에 들어간다. ③이 ⓑ 앞이면 `alert`로도 받는다 → **중복**(같은 `alert_id`). 화면이 `alert_id`로 거른다.
  - ⓐ가 ① 뒤이고 ③이 ⓑ 앞: `alert`로 받는다. 정상.
  - ⓐ가 ① 뒤이고 ③이 ⓑ 뒤: ②(hello 전송, 수 ms) 사이에 ⓐ·ⓑ가 모두 끝난 경우 → **놓침**. 그 알림은 다음 재접속 hello(또는 S6 `GET /api/zones/{id}/alerts?unacked=true`)로 받는다. 등급 자체는 다음 초 `zone_state`로 보인다.
- 놓침을 없애는 방법과 비용:
  - 구역 잠금으로 ①~③과 ⓐ~ⓑ를 묶음: hello 전송(최악 2초, 결정 기록 1) 동안 재생 스레드가 멈춘다.
  - ③ 뒤에 `unacked`를 다시 읽어 ①에 없던 알림을 그 세션에 따로 보냄: S3 `ZoneSessions.join`을 고쳐야 한다(감싼 세션 반환). 중복은 남는다.
- 이 PR은 둘 다 하지 않는다. 창이 hello 전송 시간(ms)이고 알림은 반복 재생 한 바퀴(180초)에 몇 개다. 시연에서 생길 확률이 무시할 만하다. `[토론]` 4에서 정한다.

### 7.4 메모리 상한
| 상태 | 크기 |
|---|---|
| `AlertDetector` | 구역당 필드 4개 (O(1)) |
| `AlertStore` | 구역당 최대 `unacked-alert-limit`(100)개. 알림 1개 수백 바이트 → 구역당 수십 KB |
| `AlertIdGenerator` | `AtomicLong` 1개 |
| `hello` 크기 | `unacked_alerts` 최대 100개(약 25 KB) + meta. 버퍼 한도 512 KB 안 |
- 30분 반복(E8): 반복마다 같은 알림이 새로 생겨 쌓이지만 100개에서 멈춘다(`WsZoneBroadcasterTest.thirtyMinuteLoopKeepsStoreBounded`). S6 확인이 생기면 확인한 알림을 뺄지 S6이 정한다.

## 8. 테스트
공통 표기: N=NORMAL, C=CAUTION, A=ALERT, CR=CRITICAL, T=true, F=false. 고정 시계 `FIXED = Clock.fixed(Instant.parse("2026-11-18T05:02:31.512Z"), ZoneId.of("Asia/Seoul"))`(`MessageFactoryTest.FIXED`), `FIXED_TS = "2026-11-18T14:02:31.512+09:00"`.

### 8.1 `alert/AlertDetectorTest` (추가)
도우미:
```java
    private final AlertDetector detector = new AlertDetector();

    /** 판정 대상 셀. pressure는 unstable일 때만 의미가 있다. */
    private static CellEvaluation cell(String id, Grade grade, boolean eligible, boolean unstable, double density,
                                       Double pressure) {
        return new CellEvaluation(id, grade, null, eligible, unstable,
                new CellState(id, density, null, null, null, pressure, null, null));
    }

    private static ZoneEvaluation eval(int t, Grade zoneGrade, Double maxDensity, Double inflowAvg,
                                       boolean inflowAlert, CellEvaluation... cells) {
        return new ZoneEvaluation(t, zoneGrade, maxDensity, inflowAvg, inflowAlert, List.of(cells));
    }

    /** 구역 등급만 바꾸며 detect를 부르고 초마다 사건 목록을 모은다 (셀 없음, max_density 4.5). */
    private List<List<AlertEvent>> runGrades(Grade... grades) { ... }
```

| 메서드 | `@DisplayName` | 입력 (t0부터) | 기대 |
|---|---|---|---|
| `gradeUpRules` | "경계 이상으로 오르고 사건 최고 단계를 넘을 때만 GRADE_UP을 보낸다" | 구역 N, C, A, CR, A, CR, C, A | 사건 있는 초 t2(A), t3(CR), t7(A). 나머지 빈 목록 (api-spec 3.3 예시) |
| `gradeUpMessages` | "문구는 직전 등급 → 지금 등급이다" | 같은 입력 | t2 `"구역 등급이 주의 → 경계로 올랐다"`, t3 `"구역 등급이 경계 → 심각으로 올랐다"`, t7 `"구역 등급이 주의 → 경계로 올랐다"` |
| `gradeUpJumpFromNormal` | "정상에서 심각으로 바로 오르면 심각 하나만 보낸다" | N, CR, A | t1 level CR, `"구역 등급이 정상 → 심각으로 올랐다"`. t2 없음 |
| `noAlertForCaution` | "주의로 오르는 것은 알림이 없다" | N, C, C, N, C | 모두 빈 목록 |
| `gradeUpPayload` | "GRADE_UP 값은 최대 밀도, 셀은 등급이 level 이상인 판정 대상 셀이다" | t0 구역 C, t1 구역 A, max 4.3, 셀 [c-0000 A 대상 4.3, c-0001 C 대상 3.5, c-0102 CR 비대상 6.0] | t1 사건 1개: level A, reason GRADE_UP, value 4.3, cell_ids ["c-0000"] |
| `gradeUpCellsAtOrAboveLevel` | "심각 알림의 셀은 심각인 셀만이다" | t0 구역 CR, max 5.5, 셀 [c-0000 A 대상 4.5, c-0001 CR 대상 5.5] | cell_ids ["c-0001"], value 5.5 |
| `instabilityEdge` | "판정 대상 불안정 셀이 처음 생긴 초에만 INSTABILITY를 보낸다" | 구역 N. c-0000 unstable [F, F, T, T], c-0001 [F, F, F, T], pressure 0.03 | t2만 사건 1개: level CR, reason INSTABILITY, cell_ids ["c-0000"], value 0.03, message `"셀 c-0000에서 군중 불안정이 감지됐다"` |
| `instabilityPayload` | "같은 초에 여러 셀이 불안정이면 모두 담고 최대 압력을 값으로 한다" | t0 c-0000 T(0.03), c-0001 T(0.05) | cell_ids ["c-0000", "c-0001"], value 0.05, message `"셀 c-0000, c-0001에서 군중 불안정이 감지됐다"` |
| `instabilityIgnoresSmallCells` | "판정 대상이 아닌 셀의 불안정은 알리지 않는다" | c-0102 비대상 unstable T × 3 | 모두 빈 목록 |
| `instabilityResendsAfterRelease` | "불안정이 모두 풀린 뒤 다시 생기면 다시 보낸다" | c-0000 [T, F, T] | t0, t2 |
| `inflowEdge` | "유입 경보가 켜진 초에만 INFLOW를 보낸다" | inflowAlert [F, F, F, F, T, T], t4·t5 inflowAvg 0.6599999999999999 | t4만 사건 1개: level C, reason INFLOW, value 0.66, cell_ids [], message `"구역으로 들어오는 인원이 몰린다"` |
| `inflowValueRounded` | "INFLOW 값은 소수 3자리로 반올림한다" | t0 inflowAlert T, avg 0.775000000000001 | value 0.775 |
| `inflowResendsAfterOff` | "유입 경보가 꺼졌다가 다시 켜지면 다시 보낸다" | inflowAlert [T, F, T] | t0, t2 |
| `sameTickOrder` | "한 초에 여러 알림이면 불안정, 등급, 유입 순서다" | t0 구역 CR, max 5.5, c-0000 CR 대상 unstable T(0.03), inflowAlert T avg 0.8 | reasons [INSTABILITY, GRADE_UP, INFLOW] |
| `resetStartsNewIncident` | "초기화하면 같은 사건을 다시 보낸다" | 구역 A + c-0000 unstable T + inflowAlert T(avg 0.8), reset, 같은 eval | reset 앞·뒤 모두 사건 3개. reset 뒤 GRADE_UP 문구 `"구역 등급이 정상 → 경계로 올랐다"` |
| `instabilityThenCriticalGradeUp` | "불안정은 INSTABILITY 다음 초에 심각 GRADE_UP을 만든다" | 실제 `TestProperties.grader(ONE)`(c-0000 4.0㎡), 밀도 1.0, pressure 0.03, t0~t3 프레임 → evaluate → detect | t2 [INSTABILITY(value 0.03, ["c-0000"])], t3 [GRADE_UP(level CR, value 1.0, ["c-0000"], `"구역 등급이 정상 → 심각으로 올랐다"`)]. t0·t1 없음. api-spec 10절 9번 동작을 고정한다(`[토론]` 1) |
- `instabilityThenCriticalGradeUp` 손 계산: S4 `instabilityToCritical`과 같다. `unstable` [F, F, T, T], 셀·구역 등급 [N, N, N, CR]. 구역이 t2에 N이라 GRADE_UP은 t3 하나다.
- 프레임 도우미: `new Frame(t, null, null, List.of(new CellState("c-0000", 1.0, null, null, null, 0.03, null, null)))`, `ONE = List.of(new CellMeta("c-0000", 0, 0, 4.0, List.of()))`.

### 8.2 `alert/AlertIdGeneratorTest` (추가)
| 메서드 | `@DisplayName` | 입력 | 기대 |
|---|---|---|---|
| `formatAndSequence` | "ID는 a-날짜-4자리 번호이고 1부터 늘어난다" | `FIXED`, `next()` 2번 | `"a-20261118-0001"`, `"a-20261118-0002"` |
| `dateUsesClockZone` | "날짜는 시계 시간대 기준이다" | `Clock.fixed(2026-11-17T15:30:00Z, Asia/Seoul)` | `"a-20261118-0001"` (UTC로는 17일) |
| `widensAfter9999` | "9999 다음은 5자리 번호다" | `next()` 10000번 | 마지막 `"a-20261118-10000"` |

### 8.3 `alert/AlertStoreTest` (추가)
`store = new AlertStore(TestProperties.replay(1000, true), FIXED)`(상한 100). 도우미 `event(Grade, AlertReason)` → `new AlertEvent(level, reason, "시험", 4.5, List.of("c-0000"))`.

| 메서드 | `@DisplayName` | 입력 | 기대 |
|---|---|---|---|
| `issueAssignsIdAndCopiesFields` | "발급하면 ID·구역·t·frame_ts를 붙이고 사건 값을 옮긴다" | `issue("zone-test", 3, FIXED_TS, event(ALERT, GRADE_UP))` | `new Alert("a-20261118-0001", "zone-test", 3, FIXED_TS, ALERT, GRADE_UP, "시험", 4.5, ["c-0000"])` |
| `unackedOldestFirst` | "미확인 알림은 오래된 것부터 준다" | 3개 발급 | ID [-0001, -0002, -0003] |
| `unackedPerZone` | "구역마다 따로 모은다" | zone-a 2개, zone-b 1개 | zone-a 2개, zone-b 1개(ID -0003), zone-c 빈 목록 |
| `capDropsOldest` | "구역당 100개를 넘으면 가장 오래된 것부터 버린다" | zone-test 101개 | 크기 100, 첫 ID -0002, 마지막 -0101. 다른 구역은 영향 없음 |
| `unackedIsSnapshot` | "받은 목록은 나중 발급에 바뀌지 않고 고칠 수 없다" | 1개 → `unacked` → 1개 더 | 앞서 받은 목록 크기 1, `add`는 `UnsupportedOperationException` |
| `concurrentIssueAndRead` | "발급과 조회를 동시에 해도 예외 없이 상한·순서를 지킨다" | 스레드 A: `issue` 1000번, 스레드 B: `unacked` 1000번(`CountDownLatch`로 같이 시작) | 예외 없음. B가 본 모든 목록 크기 ≤ 100이고 ID가 오름차순. 끝 크기 100, 마지막 ID -1000 |

### 8.4 `replay/ZoneRuntimeTest` (추가)
| 메서드 | `@DisplayName` | 입력 | 기대 |
|---|---|---|---|
| `alertRepeatsNextLoop` | "반복으로 처음에 돌아오면 같은 알림이 다시 생긴다" | `timelineWithDensity(5, 4.5)`, loop, tick 10번 | 초마다 알림 수 [0, 1, 0, 0, 0, 0, 1, 0, 0, 0]. 2번째·7번째(t1): GRADE_UP, level A, value 4.5, cell_ids ["c-0000"], `"구역 등급이 정상 → 경계로 올랐다"` |
- 기존 3개(`resetOnWrap`, `resetsInflowOnWrap`, `emptyAfterEnd`)는 그대로 통과한다.

### 8.5 `ws/MessageFactoryTest` (수정·추가)
`ALERT_SAMPLE = new Alert("a-20261118-0001", "zone-test", 1, FIXED_TS, ALERT, GRADE_UP, "구역 등급이 정상 → 경계로 올랐다", 4.5, List.of("c-0000"))`.

| 메서드 | `@DisplayName` | 입력 | 기대 |
|---|---|---|---|
| `helloFromFixture` (수정) | 그대로 | `hello(runtime, List.of())` | 기존 단언 그대로(`unackedAlerts` 비어 있음) |
| `helloReflectsCurrentPlayback` (수정) | 그대로 | `hello(runtime, List.of())` | 그대로 |
| `helloCarriesUnackedAlerts` | "hello는 받은 미확인 알림을 순서대로 담는다" | `hello(runtime, List.of(ALERT_SAMPLE, 두번째))` | `unackedAlerts` == [`messages.alert(ALERT_SAMPLE)`, `messages.alert(두번째)`] |
| `alertFromAlert` | "alert 메시지는 발급한 알림 값을 옮긴다" | `messages.alert(ALERT_SAMPLE)` | `new AlertMessage("alert", "a-20261118-0001", "zone-test", 1, FIXED_TS, ALERT, GRADE_UP, "구역 등급이 정상 → 경계로 올랐다", 4.5, ["c-0000"])` |

### 8.6 `ws/MessageJsonTest` (수정·추가)
- `messages.hello(runtime)` 3곳을 `messages.hello(runtime, List.of())`로 바꾼다. `HELLO_SAMPLE`·`helloKeys`는 그대로(`unacked_alerts` 빈 배열).
- `ALERT_SAMPLE` JSON은 10.1절.

| 메서드 | `@DisplayName` | 입력 | 기대 |
|---|---|---|---|
| `alertKeys` | "alert 키는 api-spec 3.3과 같다" | `messages.alert(GRADE_UP 알림)` | 키 {type, alert_id, zone_id, t, frame_ts, level, reason, message, value, cell_ids}. 문자열이 `{"type":"alert","alert_id":`로 시작(선언 순서) |
| `alertMatchesSample` | "alert 출력이 10.1절 예시와 같다" | 같은 알림, INFLOW 알림(`cell_ids` []) | 트리가 10.1의 두 예시와 같다. INFLOW `cell_ids`는 빈 배열(null 아님) |
| `helloUnackedAlertKeys` | "hello.unacked_alerts 원소는 alert 메시지와 같은 키다" | `hello(runtime, List.of(알림))` | `unacked_alerts` 크기 1, 원소 키 10개, `type` `"alert"` |

### 8.7 `ws/WsZoneBroadcasterTest` (추가)
도우미:
```java
    /** instant()를 부를 때마다 1 ms씩 가는 시계. frame_ts를 한 tick에 두 번 만들면 값이 달라진다. */
    private static final class SteppingClock extends Clock {
        private final AtomicLong millis = new AtomicLong(Instant.parse("2026-11-18T05:02:31.512Z").toEpochMilli());

        @Override
        public ZoneId getZone() {
            return ZoneId.of("Asia/Seoul");
        }

        @Override
        public Clock withZone(ZoneId zone) {
            throw new UnsupportedOperationException();
        }

        @Override
        public Instant instant() {
            return Instant.ofEpochMilli(millis.getAndIncrement());
        }
    }
```
- `props = TestProperties.replay(1000, true)`, `store = new AlertStore(props, FIXED)`, `MAPPER`.

| 메서드 | `@DisplayName` | 입력 | 기대 |
|---|---|---|---|
| `alertFollowsZoneStateWithSameFrameTs` | "알림은 그 초 zone_state 다음에 같은 t·frame_ts로 보낸다" | `sessions = mock(ZoneSessions.class)`, `new MessageFactory(new SteppingClock(), props)`, 런타임 `timelineWithDensity(3, 4.5)` loop, tick 2번, 매번 `zoneState("zone-test", step)` | `broadcast("zone-test", json)` 3번, 순서 [zone_state t0 `…31.512+09:00`, zone_state t1 `…31.513+09:00`, alert t1 `…31.513+09:00`]. alert `alert_id` `"a-20261118-0001"`, reason GRADE_UP, level ALERT, value 4.5, cell_ids ["c-0000"]. `store.unacked("zone-test")` ID 1개 같음 |
| `noAlertNoExtraMessage` | "알림이 없는 초에는 zone_state만 보낸다" | 같은 구성, tick 1번 | `broadcast` 1번(zone_state), `store.unacked` 빈 목록 |
| `thirtyMinuteLoopKeepsStoreBounded` | "30분 반복 재생에도 미확인 알림은 상한에서 멈춘다" | 실제 `new ZoneSessions(props)`(접속 없음), `FIXED` 시계, `timelineWithDensity(10, 4.5)` loop, tick·`zoneState` 1800번 | 예외 없음. 마지막 `player().snapshot().t()` 9. `store.unacked` 크기 100, 첫 ID `"a-20261118-0081"`, 마지막 `"a-20261118-0180"` (반복 180번 × t1 GRADE_UP 1개) |
- `ZoneSessions`는 `final`이지만 Mockito 5 inline으로 mock된다(0장). 순서는 `ArgumentCaptor<String>` + `verify(sessions, times(3)).broadcast(eq("zone-test"), captor.capture())`로 읽는다.

### 8.8 `config/CrowdsightPropertiesTest`, `CrowdsightServerApplicationIntegrationTest`
`defaults()`에 `crowdsight.unacked-alert-limit`=100을 더한다.

| 메서드 | `@DisplayName` | 입력 | 기대 |
|---|---|---|---|
| (기존 21개) | 그대로 | 기본 맵 | 그대로 통과 |
| `bindsUnackedAlertLimit` | "미확인 알림 상한을 묶는다" | 기본 맵 | `unackedAlertLimit()` == 100 |
| `rejectsNonPositiveUnackedAlertLimit` (`@ValueSource(ints = {0, -1})`) | "미확인 알림 상한이 1 미만이면 거부한다" | 값 | `BindException`, 원인 메시지에 `crowdsight.unacked-alert-limit` |
| `rejectsMissingUnackedAlertLimit` | "미확인 알림 상한이 없으면 거부한다" | 키 제거 | 원인 메시지에 `crowdsight.unacked-alert-limit` (0으로 묶여 거부) |
| `CrowdsightServerApplicationIntegrationTest.bindsDefaultUnackedAlertLimit` | "application.yml의 미확인 알림 상한을 읽는다" | 앱 컨텍스트 | `props.unackedAlertLimit()` == `TestProperties.UNACKED_ALERT_LIMIT` |

### 8.9 통합 테스트 (`ws/ZoneWebSocketIntegrationTest`)
- `@Autowired AlertStore alerts`를 더한다.
- `helloFirst`: `unacked_alerts` 단언을 `.size()).isZero()`에서 `.isArray()).isTrue()`로 완화한다. 컨텍스트를 테스트끼리 같이 쓰므로 아래 테스트가 넣은 알림이 남을 수 있다(실행 순서 미정). fixture 자체는 알림을 만들지 않는다(0장).

| 메서드 | `@DisplayName` | 입력 | 기대 |
|---|---|---|---|
| `helloCarriesUnackedAlerts` | "접속하면 그 구역 미확인 알림을 hello로 받는다" | `alerts.issue("zone-test", 3, "2026-11-18T14:02:31.512+09:00", new AlertEvent(ALERT, GRADE_UP, "구역 등급이 주의 → 경계로 올랐다", 4.3, List.of("c-0000")))` 뒤 `connect("zone-test").next()` | hello `unacked_alerts` 중 `alert_id`가 발급 ID와 같은 원소가 있다. 그 원소 키 10개, `type` `"alert"`, `t` 3, `level` `"ALERT"`, `cell_ids` ["c-0000"] |
- 실제 재생으로 알림이 방송되는 경로는 fixture로 만들 수 없어 `WsZoneBroadcasterTest`가 맡는다(0장).

## 9. 문서 정정 (이 PR의 docs 커밋)

### 9.1 `server_impl_plan.md`
1. 1.1절 `alert/`: `AlertReason, AlertEvent, Alert, AlertDetector, AlertIdGenerator, AlertStore` (S5), `AlertLogWriter, AlertController` (S6). `ws/message/`의 `AlertMessage(S5)`는 그대로.
2. 1.2절 흐름: `ZoneRuntime.tick()` 안에서 discontinuity면 `ZoneGrader.reset()`·`AlertDetector.reset()`, `AlertDetector.detect(eval) → List<AlertEvent>`, `ZoneStep(tick, evaluation, alerts)`. 방송 줄은 "`WsZoneBroadcaster.zoneState`: `frame_ts` 1번 → `zone_state` → 알림마다 `AlertStore.issue` → `alert`".
3. 2장 S5 코드 블록:
   - `public record AlertEvent(Grade level, AlertReason reason, String message, Double value, List<String> cellIds) {}` 추가.
   - `Alert(..., Double value, List<String> cellIds)` (`double` → `Double`).
   - `AlertDetector()` 인자 없음, `detect(ZoneEvaluation) → List<AlertEvent>`, `reset()`. `ZoneRuntime`이 직접 만든다.
   - `AlertIdGenerator(Clock)` 패키지 전용, `AlertStore(CrowdsightProperties, Clock)`: `issue(zoneId, t, frameTs, event)`, `unacked(zoneId)`. `find`·`ack`는 S6.
   - "구역당 최대 100"을 "`crowdsight.unacked-alert-limit`(기본 100)"으로.
4. 2장 S5 규칙 목록: INFLOW value 소수 3자리, 한 초 순서 INSTABILITY → GRADE_UP → INFLOW, GRADE_UP 문구의 앞 등급 = 직전 초 구역 등급, `hello` = `MessageFactory.hello(zone, AlertStore.unacked(zoneId))`.
5. 2장 S5 테스트 표: `ZoneRuntimeTest.alertAfterState` → `WsZoneBroadcasterTest.alertFollowsZoneStateWithSameFrameTs`, `ZoneRuntimeTest.thirtyMinuteLoop` → `WsZoneBroadcasterTest.thirtyMinuteLoopKeepsStoreBounded`(첫 ID -0081). `instabilityThenCriticalGradeUp`을 더한다. 끝에 "상세는 `docs/plans/server_s5_alert_plan.md` 8장".
6. 4장 yml: `inflow` 다음에 `unacked-alert-limit: 100` 줄. 설명 문단 검사 목록에 "`unacked-alert-limit` ≥ 1".
7. 5장 동시성 표에 행 추가: "미확인 알림 | `AlertStore` `synchronized` + 불변 복사본. 쓰기 재생 스레드, 읽기 hello(·S6 REST). 접속과 발송 사이 중복·드문 놓침은 허용(S5 계획 7.3)".
8. 9장 `[토론]`에 S5 12장 2·4·5를 더한다.

### 9.2 `docs/api-spec.md` (보충, 형식 변경 없음 → v0.2 유지)
1. 3.1: "`unacked_alerts`는 오래된 것부터, 구역당 최근 100개(`crowdsight.unacked-alert-limit`)까지다. 넘으면 오래된 것부터 버린다. 같은 알림을 `hello`와 `alert`로 두 번 받을 수 있으니 화면은 `alert_id`로 거른다."
2. 3.3: "한 초에 알림이 여럿이면 `INSTABILITY` → `GRADE_UP` → `INFLOW` 순서다." "`INFLOW`의 `value`는 소수 3자리로 반올림한다." "`alert_id`는 `a-yyyyMMdd-NNNN`이고 번호는 서버 시작부터 1씩 는다(재시작하면 1부터)."
3. 8절 yml: `inflow` 다음에 `unacked-alert-limit: 100` 줄.

## 10. 출력 예시 (PR 설명·나예린 님 전달용)
`MessageJsonTest`가 10.1과 같은지 트리로 확인한다. `frame_ts`는 시험용 고정 시계 값이다.

### 10.1 `alert`
`GRADE_UP` (합성 타임라인 `timelineWithDensity(5, 4.5)` t1):
```json
{
  "type": "alert",
  "alert_id": "a-20261118-0001",
  "zone_id": "zone-test",
  "t": 1,
  "frame_ts": "2026-11-18T14:02:31.512+09:00",
  "level": "ALERT",
  "reason": "GRADE_UP",
  "message": "구역 등급이 정상 → 경계로 올랐다",
  "value": 4.5,
  "cell_ids": ["c-0000"]
}
```
`INFLOW` (합성 `timelineWithInflow(5, 0.8, 5.0)` t4):
```json
{
  "type": "alert",
  "alert_id": "a-20261118-0002",
  "zone_id": "zone-test",
  "t": 4,
  "frame_ts": "2026-11-18T14:02:31.512+09:00",
  "level": "CAUTION",
  "reason": "INFLOW",
  "message": "구역으로 들어오는 인원이 몰린다",
  "value": 0.8,
  "cell_ids": []
}
```
`INSTABILITY` (설명용, `instabilityThenCriticalGradeUp` t2):
```json
{ "type": "alert", "alert_id": "a-20261118-0003", "zone_id": "zone-test", "t": 2,
  "frame_ts": "2026-11-18T14:02:31.512+09:00", "level": "CRITICAL", "reason": "INSTABILITY",
  "message": "셀 c-0000에서 군중 불안정이 감지됐다", "value": 0.03, "cell_ids": ["c-0000"] }
```
- 같은 상황의 다음 초(t3)에 `GRADE_UP` `level` `CRITICAL`, `"구역 등급이 정상 → 심각으로 올랐다"`가 이어 온다(`[토론]` 1).

### 10.2 한 tick의 메시지 순서 (`alertFollowsZoneStateWithSameFrameTs` t1)
```text
{"type":"zone_state","zone_id":"zone-test","t":1,"frame_ts":"2026-11-18T14:02:31.513+09:00",...}
{"type":"alert","alert_id":"a-20261118-0001","zone_id":"zone-test","t":1,"frame_ts":"2026-11-18T14:02:31.513+09:00",...}
```

### 10.3 `hello` (미확인 알림 1개가 있을 때)
```json
{
  "type": "hello",
  "schema_version": "0.2",
  "zone_id": "zone-test",
  "meta": { "...": "S3 계획 7.1과 같다" },
  "playback": { "state": "playing", "t": 2, "loop": true, "duration_s": 5 },
  "thresholds": { "density": { "caution": 3.0, "alert": 4.0, "critical": 5.0 }, "pressure": 0.02, "inflow_ratio": 0.6 },
  "unacked_alerts": [
    { "type": "alert", "alert_id": "a-20261118-0001", "zone_id": "zone-test", "t": 1,
      "frame_ts": "2026-11-18T14:02:31.512+09:00", "level": "ALERT", "reason": "GRADE_UP",
      "message": "구역 등급이 정상 → 경계로 올랐다", "value": 4.5, "cell_ids": ["c-0000"] }
  ]
}
```
- 알림이 없으면 S4 7.1과 같다(`"unacked_alerts": []`). fixture 재생은 알림을 만들지 않는다.

### 10.4 화면(web) 처리 제안 (나예린 님)
- `type: "alert"`를 받으면 `alert_id`로 이미 있는지 보고 없을 때만 목록에 더한다(`hello`와 중복될 수 있음, 7.3절).
- `hello.unacked_alerts`로 목록을 새로 채운다(재접속 때마다).
- `playback`(`playing`, `t: 0`)을 받아도 알림 목록은 비우지 않는다(확인 전 알림은 남는다). 확인 버튼·REST는 S6.

## 11. 이후 PR이 붙일 곳 (S5에서 만들지 않음)
| PR | 붙는 곳 | 내용 |
|---|---|---|
| S6 | `AlertStore` | `find(alertId)`(ID 색인 맵), `ack(alertId)` → 처음 확인 시각(`Clock`)·이미 확인이면 처음 시각. `unacked`는 확인한 알림을 뺀다. 확인한 알림을 덱에서 지울지(상한 계산) S6이 정한다 |
| S6 | `AlertLogWriter` | 확인할 때 `logs/alerts.jsonl` 한 줄 `{alert_id, zone_id, t, level, reason, sent_at = Alert.frameTs, acked_at}`. 설정 `crowdsight.alert-log` |
| S6 | `AlertController` | `POST /api/alerts/{alertId}/ack`, `GET /api/zones/{zoneId}/alerts?unacked=true`(7.3절 놓침 복구 경로). 응답 알림 형식은 `MessageFactory.alert`와 같게 |
| S7 | `ZonePlayer.seek` | `pendingDiscontinuity` → `ZoneRuntime`이 `AlertDetector.reset()`까지 부른다. S5 코드 변경 없음 |
| S7 | `/api/health` | 필요하면 구역별 미확인 알림 수. 지금은 계획에 없음 |
| 합의 후 | `AlertEvent`·`Alert` | E8 `onset_t`·`onset_ts`(api-spec 7절, `[토론]`) |

## 12. TDD 단계
공통 (Git Bash, `server/`):
```bash
cd /c/Users/Woori/Desktop/project/Triple-Y/server && JAVA_HOME="/c/Program Files/Eclipse Adoptium/jdk-21.0.13.9-hotspot" ./gradlew test --tests '<패턴>' --no-daemon
```
> **에이전트는 `bootRun`을 실행하지 않는다** (포그라운드·백그라운드 모두). 확인은 `test`·`build`로 한다.

각 단계의 Red는 "테스트 먼저 작성 → 컴파일 실패 또는 단언 실패 확인"이다.

| 단계 | 할 일 (Red → Green) | `--tests` | 완료 조건 |
|---|---|---|---|
| 0 | 브랜치 확인: `git switch feat/server-alert`, `git log --oneline -1`이 `3ce4601` | — | `git status --short`에 `?? CLAUDE.local.md`·`?? docs/plans/server_s5_alert_plan.md`만. 시작 전 전체 `./gradlew test --no-daemon` 통과 |
| 1 | `CrowdsightPropertiesTest` `defaults()`·추가 3개, `bindsDefaultUnackedAlertLimit`, `TestProperties.UNACKED_ALERT_LIMIT·full` → `CrowdsightProperties.unackedAlertLimit`, yml | `'com.tripley.crowdsight.config.*'` 다음 `'com.tripley.crowdsight.CrowdsightServerApplicationIntegrationTest'` | config 기존 + 3메서드(4회) 통과, 앱 통합 7메서드 통과 |
| 2 | `AlertIdGeneratorTest` → `AlertIdGenerator` | `'com.tripley.crowdsight.alert.AlertIdGeneratorTest'` | 3메서드 통과 |
| 3 | `AlertDetectorTest` → `AlertReason`, `AlertEvent`, `AlertDetector` | `'com.tripley.crowdsight.alert.AlertDetectorTest'` | 16메서드 통과 |
| 4 | `AlertStoreTest` → `Alert`, `AlertStore` | `'com.tripley.crowdsight.alert.AlertStoreTest'` | 6메서드 통과 |
| 5 | `ZoneRuntimeTest.alertRepeatsNextLoop` → `ZoneStep.alerts`, `ZoneRuntime`(판정기·reset), `ZoneBroadcaster` Javadoc | `'com.tripley.crowdsight.replay.*'` | `ZoneRuntimeTest` 4메서드, replay 기존 테스트 통과 |
| 6 | `MessageFactoryTest`(수정 2, 추가 2), `MessageJsonTest`(호출 3곳, 추가 3) → `AlertMessage`, `HelloMessage`(타입), `MessageFactory`(`hello` 인자, `alert`) | `'com.tripley.crowdsight.ws.Message*'` | Message 테스트 모두 통과 |
| 7 | `WsZoneBroadcasterTest`, `ZoneWebSocketIntegrationTest`(완화 1, 추가 1) → `WsZoneBroadcaster`, `ZoneWebSocketHandler` | `'com.tripley.crowdsight.ws.WsZoneBroadcasterTest'` 다음 `'com.tripley.crowdsight.ws.ZoneWebSocketIntegrationTest'` | 3메서드, 통합 기존 + 1 통과 |
| 8 | 전체 실행 | 없음 (`./gradlew test --no-daemon`) | 모든 테스트 통과 |
| 9 | README 알림 절(아래), 9장 문서 정정 | — | 문구만 |
| 10 | 전체 검증 (아래 표) | — | 모두 기대대로 |

README 추가 절 (`## 판정 기준 (S4)` 아래):
````markdown
## 알림 (S5)
- 서버가 `alert`를 보낸다: 구역 등급이 경계·심각으로 오를 때(`GRADE_UP`), 판정 대상 셀이 불안정이 될 때(`INSTABILITY`), 유입 경보가 켜질 때(`INFLOW`). 같은 사건은 한 번만 보낸다.
- 한 초 안에서는 `zone_state` 다음에 `alert`가 오고, 둘의 `t`·`frame_ts`가 같다.
- 확인하지 않은 알림은 구역당 최근 100개(`crowdsight.unacked-alert-limit`)까지 메모리에 두고, 접속할 때 `hello.unacked_alerts`로 다시 보낸다. 서버를 재시작하면 사라진다. 확인(ack)은 S6.
- 반복 재생으로 처음에 돌아오면 알림 판정이 초기화되어 같은 알림이 새 ID로 다시 온다.
- 알림마다 INFO 로그 `알림 zone=… t=… alert_id=… reason=… level=… value=…`가 남는다.
- fixture와 가짜 타임라인 대부분은 경계에 닿지 않아 알림이 없을 수 있다. 판정은 단위 테스트로 확인한다.
````

10단계 검증:

| # | 명령 (`server/`) | 기대 |
|---|---|---|
| 1 | `JAVA_HOME=… ./gradlew clean build --no-daemon` | `BUILD SUCCESSFUL` |
| 2 | `grep -h -o 'tests="[0-9]*" skipped="[0-9]*" failures="[0-9]*" errors="[0-9]*"' build/test-results/test/*.xml` | 모든 줄 `failures="0" errors="0"` |
| 3 | `grep -rn 'springframework' src/main/java/com/tripley/crowdsight/grade src/main/java/com/tripley/crowdsight/alert/AlertDetector.java src/main/java/com/tripley/crowdsight/alert/AlertEvent.java src/main/java/com/tripley/crowdsight/alert/Alert.java` | 출력 없음 |
| 4 | `grep -rn 'List<Object>' src/main` | 출력 없음 (`unackedAlerts` 타입 교체) |
| 5 | `grep -rnE '\b100\b' src/main/java` | 출력 없음 (상한은 yml에만) |
| 6 | `grep -rn 'S5에서' src/main` | 출력 없음 (S5 자리 주석 정리) |
| 7 | `grep -rnE 'Instant\.now\|currentTimeMillis\|LocalDate\.now\(\)' src/main` | 출력 없음 (`LocalDate.now(clock)`만) |
| 8 | `grep -rnE '@(Data\|Getter\|Setter\|Builder\|Value\|AllArgsConstructor\|NoArgsConstructor)\b' src` | 출력 없음 |
| 9 | `grep -rn 'com.fasterxml.jackson.databind' src` | 출력 없음 |
| 10 | `grep -rnP '\t' src README.md` | 출력 없음 |
| 11 | 바뀐 `.java` 파일에 120자 초과 줄 없음 (문자 수 기준) | 출력 없음 |
| 12 | stage 뒤 `git -C .. ls-files --eol server \| grep -v 'i/lf'` | `gradle-wrapper.jar`, `gradlew.bat`만 |
| 13 | `git -C .. status --short` | `CLAUDE.local.md`가 stage되지 않음 |

커밋 제안 (커밋·푸시·PR은 사용자가 요청할 때만):
1. `feat: 미확인 알림 상한 설정 추가` (`CrowdsightProperties`, yml, `TestProperties`, 설정 테스트)
2. `feat: 알림 alert 방송과 미확인 알림 (S5)` (`alert/` 6개, `ZoneStep`, `ZoneRuntime`, 메시지, `MessageFactory`, `WsZoneBroadcaster`, `ZoneWebSocketHandler`, 테스트)
3. `docs: S5 계획 추가, 구현 계획·api-spec 정정, README 알림 설명`

## 13. PR 설명 (초안)
제목: `feat: 알림 alert 방송과 미확인 알림 (S5)` / 기준 `main` ← `feat/server-alert` (쌓인 PR 아님)

- 목적: 구역 등급이 경계·심각으로 오르거나, 셀이 불안정해지거나, 유입 경보가 켜지는 순간 화면에 `alert`를 보낸다. 확인하지 않은 알림은 서버가 들고 있다가 다시 접속한 화면에 `hello.unacked_alerts`로 준다.
- 변경:
  - `alert/`: `AlertDetector`(올라가는 순간만 판정, 사건 최고 단계 기억), `AlertEvent`·`Alert`·`AlertReason`, `AlertIdGenerator`(`a-yyyyMMdd-NNNN`), `AlertStore`(구역별 미확인 알림, 상한 100, `synchronized`)
  - `ZoneRuntime`이 판정 뒤 알림을 판정하고 반복·이동 때 초기화한다. `ZoneStep.alerts`
  - `WsZoneBroadcaster`: tick마다 `frame_ts` 한 번 → `zone_state` → 알림 발급·저장 → `alert`
  - `hello.unacked_alerts` 실제 값(`List<AlertMessage>`), `AlertMessage`
  - 설정 `crowdsight.unacked-alert-limit: 100`
- 바뀌지 않은 것: `zone_state`·`playback` 형식, `hello.schema_version` `"0.2"`, `ZoneBroadcaster`·`ReplayScheduler`. fixture는 알림을 만들지 않아 S3·S4 출력 예시가 그대로다.
- 출력 예시: 계획 10.1(`alert` 세 종류), 10.3(`hello`).
- 참고: api-spec 3.1·3.3·4.2, S3 결정 #5·#14, S4 8장.

> [!IMPORTANT]
> **CS 이슈**
> | **주제** | **내용** |
> |---|---|
> | **엣지 트리거 vs 레벨 트리거** | 알림은 조건이 "켜진 순간"(rising edge)에만 낸다. 직전 상태 1비트(불안정·유입)와 사건 최고 단계(`GRADE_UP`)만 기억하면 되어 O(1)이다. 레벨로 보내면 1초마다 같은 알림이 쏟아진다 |
> | **래치(latch)와 사건 경계** | `GRADE_UP`은 사건 안에서 보낸 최고 단계를 래치한다. 경계 아래로 내려가야 래치가 풀린다. 히스테리시스(S2)가 등급 깜빡임을 막고, 래치가 알림 깜빡임을 막는다 |
> | **모니터 락과 원자성** | `AlertStore`는 덧붙이기·상한 확인·맨 앞 버리기를 `synchronized` 하나로 묶는다. Concurrent 컬렉션은 연산 하나씩만 원자적이라 "확인 후 행동(check-then-act)"이 깨진다 |
> | **불변 스냅샷과 안전한 공개** | 읽기는 `List.copyOf` 복사본, 원소는 불변 record다. 잠금 해제·획득의 happens-before로 다른 스레드가 완성된 값을 본다 |
> | **스냅샷 + 구독 경쟁** | "현재 목록 받기(hello)"와 "이후 변경 구독(방송 집합)"이 원자적이지 않으면 중복이나 누락이 생긴다. 저장을 방송보다 먼저 해 대부분 중복 쪽으로 기울이고, 화면이 `alert_id`로 걸러 멱등(idempotent)하게 처리한다 |
> | **유한 버퍼(bounded buffer)** | 미확인 알림은 구역당 100개에서 가장 오래된 것을 버린다(drop-oldest). 30분 반복에도 메모리가 늘지 않는다 |
> | **단조 증가 ID** | `AtomicLong`의 CAS로 잠금 없이 번호가 겹치지 않는다. 프로세스 안에서만 유일하고 재시작하면 다시 1이다 |
> | **포트와 의존 방향** | 판정(`alert`·`grade`)은 전송(`ws`)을 모른다. `frame_ts`는 보내는 쪽이 tick마다 한 번 만들어 `zone_state`와 `alert`가 같은 값을 쓴다 |

| 선택 | 대안 | 고른 이유 |
|---|---|---|
| 판정(`AlertDetector`)과 발급(`AlertStore.issue`) 분리 | 판정기가 ID·`frame_ts`까지(계획 초안) | `frame_ts`를 `zone_state`와 공유해야 한다. 판정기는 설정·시계 없이 순수하게 시험된다 |
| `WsZoneBroadcaster`에서 발급 | `ReplayScheduler`가 `frame_ts`를 만들어 발급 | replay가 ws(`FrameTimestamps`)에 의존하지 않고, `ZoneBroadcaster`·`ReplayScheduler`가 바뀌지 않는다 |
| `synchronized` 저장소 | `ConcurrentHashMap` + `ConcurrentLinkedDeque` | 상한 처리의 원자성. 경합이 없어 비용이 없다 |
| 상한을 설정에 | `AlertStore` 상수 100 | 기준값·크기는 `crowdsight.*` 한 곳(CLAUDE.md) |
| `hello(zone, unacked)` 인자 | `MessageFactory`가 `AlertStore`를 읽음 | `MessageFactory`가 상태 없이 남고 테스트가 쉽다 |
| 접속 경쟁 허용 + `alert_id` 거르기 | 구역 잠금, `join` 뒤 따라잡기 전송 | 창이 ms이고 알림이 드물다. 잠금은 hello 전송 동안 재생을 멈춘다 |
| `value` `Double` | `double` | 규칙(없을 수 있는 숫자)과 방어용 null 밀도 |

리뷰 요청:
- 알림 규칙(7.1절)과 한 초 순서 INSTABILITY → GRADE_UP → INFLOW
- 접속과 발송 사이 중복·드문 놓침을 허용한 것(7.3절)
- 반복 재생마다 같은 알림이 새 ID로 쌓이는 것(시연 30분에 100개 상한)
- 알림 문구

남은 일:
- S6(`ack` REST, `GET .../alerts`, `logs/alerts.jsonl`), S7(재생 제어)
- 화면: `alert` 처리·`alert_id` 중복 거르기(10.4절, 나예린 님)

## 14. 위험·가정·`[토론]`
| 위험 | 대응 |
|---|---|
| fixture·가짜 타임라인으로는 실제 재생 중 `alert` 방송을 통합 테스트로 볼 수 없다 | 합성 타임라인 + `WsZoneBroadcasterTest`(순서·`frame_ts`·상한), `AlertDetectorTest`(규칙), 통합 테스트는 hello 경로만. bootRun은 사용자가 INFO 로그로 확인 |
| 접속과 알림 발송이 겹치면 드물게 알림을 놓친다 | 7.3절. 등급은 다음 `zone_state`로 보이고, 재접속·S6 GET으로 복구. `[토론]` 4 |
| 반복 재생마다 알림이 쌓여 `hello`가 길어진다 | 상한 100(약 25 KB). S6 확인으로 줄어든다 |
| 재시작하면 ID가 `-0001`부터 다시 나와 S6 로그에 같은 ID가 생길 수 있다 | 미확인 목록도 재시작 때 비워지므로 서버 안에서는 겹치지 않는다. 로그는 `sent_at`으로 구분. `[토론]` 5 |
| 통합 테스트 컨텍스트 공유로 `helloFirst`의 "미확인 0개" 단언이 순서에 따라 깨진다 | 배열인지로 완화하고, 알림 내용은 `helloCarriesUnackedAlerts`가 ID로 찾는다 |
| `HelloMessage`·`MessageFactory.hello` 시그니처 변경으로 테스트 호출 5곳이 깨진다 | TDD 6단계에서 함께 고친다(0장 목록) |
| 불안정이 `INSTABILITY`와 `GRADE_UP` 심각을 1초 간격으로 둘 다 만든다 | 명세대로(api-spec 10절 9번). `instabilityThenCriticalGradeUp`가 동작을 고정한다. `[토론]` 1 |

가정:
- (가정) `GRADE_UP` 문구의 앞 등급은 직전 초 구역 등급이다.
- (가정) 한 초 순서는 INSTABILITY → GRADE_UP → INFLOW다.
- (가정) `INFLOW` `value`는 소수 3자리 반올림이다. 다른 값(최대 밀도·압력)은 타임라인 값 그대로다.
- (가정) 반복·이동 때 판정 사건은 초기화하지만 미확인 목록은 그대로 둔다.
- (가정) S5에서는 저장한 알림 = 미확인 알림이다(확인 기능 없음).

`[토론]`:

| # | 안건 | 초안 | 누구와 |
|---|---|---|---|
| 1 | 불안정이 `INSTABILITY`(t2)와 `GRADE_UP` 심각(t3)을 둘 다 만드는 것 (api-spec 10절 9번, S4 `[토론]` 3) | 명세대로 둘 다. 줄이면 "INSTABILITY 사건 중 심각 GRADE_UP 생략" 한 줄 | 이유노, 나예린 |
| 2 | 알림 문구 3종과 한 초 순서(INSTABILITY → GRADE_UP → INFLOW) | 1장 #5~#8 | 나예린 |
| 3 | 반복 재생마다 같은 알림이 새 ID로 쌓이는 것 (api-spec 4.2 가정). 30분 시연이면 hello에 100개 가까이 | 그대로. 화면이 최근 N개만 보이거나 S6 확인으로 정리 | 나예린 |
| 4 | 접속과 발송 사이 드문 놓침 허용 (7.3절). 막으려면 `join` 뒤 따라잡기 전송 | 허용 + 화면 `alert_id` 거르기 | 조영준, 나예린 |
| 5 | 재시작 시 알림 번호가 1로 돌아감. 로그 유일성이 필요하면 시작 시각(`HHmmss`)을 ID에 넣기 | 그대로(`a-yyyyMMdd-NNNN`, 계획 2장) | 조영준 |
| 6 | 미확인 상한 100과 넘칠 때 오래된 것 버리기 | 그대로 | 조영준 |
| 7 | E8 측정 시작점 `onset_t`·`onset_ts` (api-spec 7절) | 합의 전에는 넣지 않음 | 이유노 |

---

### Critical Files for Implementation
- C:\Users\Woori\Desktop\project\Triple-Y\server\src\main\java\com\tripley\crowdsight\replay\ZoneRuntime.java
- C:\Users\Woori\Desktop\project\Triple-Y\server\src\main\java\com\tripley\crowdsight\ws\WsZoneBroadcaster.java
- C:\Users\Woori\Desktop\project\Triple-Y\server\src\main\java\com\tripley\crowdsight\ws\MessageFactory.java
- C:\Users\Woori\Desktop\project\Triple-Y\server\src\main\java\com\tripley\crowdsight\ws\ZoneWebSocketHandler.java
- C:\Users\Woori\Desktop\project\Triple-Y\server\src\main\java\com\tripley\crowdsight\config\CrowdsightProperties.java
