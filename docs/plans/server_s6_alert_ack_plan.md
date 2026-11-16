# 서버 S6 알림 확인 ack와 알림 로그 구현 계획 (`feat/server-alert-ack`)

| 항목 | 내용 |
|---|---|
| 작성일 | 2026-11-13 |
| 기준 | `docs/plans/server_impl_plan.md`(0장 "S6 테스트에 `@AutoConfigureMockMvc`", 1.1 패키지, 2장 S6, 4장 설정 `alert-log`, 5장 동시성 "미확인 알림"), `docs/api-spec.md` v0.2(2절 엔드포인트·허용 출처, 3.1 `hello.unacked_alerts`, 3.3 `alert`, 4.5 확인 기록, 8절 설정), `docs/plans/server_s5_alert_plan.md`(1장 #10·#11·#13·#19, 7.3 접속 경쟁, 7.4 메모리, 11장 S6 행, 14장 `[토론]` 4·5·6), `docs/plans/server_s3_ws_plan.md`(1장 결정 기록 2 허용 출처, 8장 S6 행 `CorsConfig`), `docs/proposal-detail.md`(UC-06 "확인 버튼을 누르면 확인 기록이 남는다", 데이터 표 `alert`, REST 표 `POST /api/alerts/{id}/ack`), CLAUDE.md(서버 규칙, 데이터 규칙: 셀·구역 집계값만 저장) |
| 대상 | `server/` (`feat/server-alert`(S5, PR #50, `755c880`) 위에 쌓은 `feat/server-alert-ack`), `docs/plans/`, `docs/api-spec.md`(보충) |
| 범위 | `POST /api/alerts/{alert_id}/ack`(처음 확인 시각, 멱등, 없는 ID 404), `GET /api/zones/{zone_id}/alerts?unacked=`(`true`·`false`), 확인한 알림 보관(상한 안), `logs/alerts.jsonl` 한 줄 기록(`crowdsight.alert-log`), REST `/api/**` 허용 출처(CORS). **재생 제어 REST·`/api/zones`·`/meta`·`/health`(S7), 확인 WS 방송 없음** |
| 상태 | 계획. 사용자 승인(2026-11-13) |

## 0. 확인한 사실 (코드·문서·jar로 확인)
- 작업 트리:
  - 브랜치 `feat/server-alert-ack`, HEAD `755c880`(= `feat/server-alert` 끝). `main` `3ce4601` 위에 S5 커밋 2개(`efe29ff`, `755c880`).
  - PR #50(`feat/server-alert` → `main`)은 OPEN이다. 그래서 S6 PR은 **쌓인 PR**(기준 `feat/server-alert`)로 연다. CLAUDE.md "쌓인 PR" 절차를 13장 PR 설명에 넣는다.
  - untracked는 `CLAUDE.local.md`와 이 계획 문서다. `CLAUDE.local.md`는 stage하지 않는다.
- S5 코드 상태 (S6이 붙는 자리):
  - `AlertStore`(`@Component public final class`): `issue(zoneId, t, frameTs, event)`, `unacked(zoneId)` 2개. 내부 `Map<String, Deque<Alert>> byZone`(`HashMap` + `ArrayDeque`), 모든 공개 메서드 `synchronized`, 읽기는 `List.copyOf`. 상한을 넘으면 `removeFirst` + WARN. Javadoc: "find·ack는 S6이 더한다".
  - `AlertStore`는 `Clock`을 받아 `AlertIdGenerator`(패키지 전용, `AtomicLong`)에 넘긴다. ID `a-yyyyMMdd-NNNN`, 서버 시작부터 구역 공통 1씩, 재시작하면 1부터.
  - `Alert(alertId, zoneId, t, frameTs, level, reason, message, value, cellIds)`. Javadoc: "S6 확인 기록의 sent_at은 frameTs다".
  - `MessageFactory.alert(Alert)` → `AlertMessage`(키 `type, alert_id, zone_id, t, frame_ts, level, reason, message, value, cell_ids`). `hello(zone, alerts.unacked(zoneId))`는 `ZoneWebSocketHandler`가 부른다.
  - `FrameTimestamps.now(Clock)`(`ws` 패키지, `public final`): `uuuu-MM-dd'T'HH:mm:ss.SSSXXX`. `ws` → `alert` 의존이 이미 있으므로 `alert`가 `FrameTimestamps`를 쓰면 순환이 생긴다.
  - `ZoneRegistry.find(zoneId)` → `Optional<ZoneRuntime>`(null이면 빈 값, 여러 스레드 안전).
  - `CrowdsightProperties(timelineDir, timelineFiles, timeZone, replay, grade, instability, inflow, unackedAlertLimit, ws, corsOriginPatterns)`. Javadoc: "alert-log는 그 값을 쓰는 PR(S6)에서 추가한다". 직접 만드는 곳은 `TestProperties.full` 한 곳.
  - `application.yml` 맨 위 주석 `(S6: alert-log)`, `cors-origin-patterns` 주석 "WS(S3)·REST(S6) 허용 출처".
  - `WebSocketConfig`: `setAllowedOriginPatterns(props.corsOriginPatterns()...)`. REST CORS 설정은 아직 없다(`CorsConfig` 없음).
  - `src/main`에 `@RestController`가 없다. `api/` 패키지도 없다(계획 1.1의 `api/`는 S7 `ZoneController`·`HealthController` 자리).
  - 테스트 `ZoneWebSocketIntegrationTest`는 `AlertStore`를 주입받아 `issue`로 알림을 직접 만든다(fixture는 알림을 만들지 않는다, S5 0장). S6 통합 테스트도 같은 방식을 쓴다.
- git 제외: 루트 `.gitignore` 35행 `server/logs/`(S0). `server/.gitignore`에는 없지만 루트로 충분하다. 테스트는 `server/build/`(제외됨) 아래에 쓴다.
- 컴파일 옵션: `build/classes/.../AlertStore.class`에 `MethodParameters` 속성이 있다(Boot Gradle 플러그인이 `-parameters`를 켠다). `@PathVariable String alertId`, `@RequestParam boolean unacked`를 이름 없이 써도 된다.
- 테스트 의존성 (`spring-boot-starter-webmvc-test` 4.1.2 pom, Gradle 캐시 jar로 확인. **추가 의존성 없음**):
  - 포함: `spring-boot-starter-test`, `spring-boot-webmvc-test`, `spring-boot-resttestclient`, `spring-boot-starter-jackson-test`.
  - `org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc`(imports: `MockMvcAutoConfiguration` 등). `MockMvcTesterConfiguration`이 `@ConditionalOnClass`(AssertJ)로 `MockMvcTester.create(MockMvc)` 빈을 만든다.
  - spring-test 7.0.10: `org.springframework.test.web.servlet.assertj.MockMvcTester`(`get()`, `post()`, `options()`), 요청 빌더가 `AssertProvider<MvcTestResultAssert>`라 `assertThat(mvc.post().uri(...))`가 된다. `exchange()` → `MvcTestResult`. 단언: `hasStatusOk()`, `hasStatus(int)`, `hasHeader(name, value)`, `headers()`, `bodyJson()`(`extractingPath`, `isLenientlyEqualTo`), `bodyText()`.
  - `org.springframework.test.web.servlet.client.RestTestClient`도 있지만 MockMvcTester 하나로 충분하다.
- Spring MVC 7.0.10 (jar): `WebMvcConfigurer.addCorsMappings(CorsRegistry)`, `CorsRegistration.allowedOriginPatterns(String...)`, `allowedMethods(String...)`, `allowedHeaders`, `maxAge`. `ResponseEntity.ok(T)`, `notFound()`, `of(Optional)`.
- Jackson 3 record 직렬화: 키 순서는 record 성분 순서다(`MessageJsonTest`가 `{"type":"alert","alert_id":`로 시작함을 확인). 전역 `SNAKE_CASE`, `null`도 쓴다(S3 `zone_state`가 `null` 값을 보낸다).
- `MockHttpServletResponse.getContentAsString()`은 응답에 charset이 없으면 ISO-8859-1로 읽는다. 한국어 `message`를 비교할 때는 `getContentAsString(StandardCharsets.UTF_8)`을 쓴다.
- JDK `Files.writeString(path, s, cs, CREATE, APPEND)`: 옵션이 있으면 `WRITE`를 더해 연다. 매번 열고 닫으므로 내용은 닫을 때 OS로 넘어간다(fsync는 하지 않음).
- api-spec v0.2:
  - 2절: `GET /api/zones/{zone_id}/alerts?unacked=true` "알림 목록 (미확인만 선택 가능)", `POST /api/alerts/{alert_id}/ack` "확인 기록을 로그 파일에 남긴다". REST도 `crowdsight.cors-origin-patterns`를 쓴다.
  - 4.5: 줄 형식 `{"alert_id","zone_id","t","level","reason","sent_at","acked_at"}`. 응답 `200 {"alert_id","acked_at"}`, 이미 확인했으면 200 + 처음 시각, 없는 ID 404. DB 없음, 재시작하면 미확인 목록이 비워진다.
  - **정하지 않은 것**: GET 응답 형식, `unacked`를 빼면 무엇을 주는지, 없는 구역, 오류 본문, 확인을 다른 화면에 알리는지(`alert_ack` 같은 WS 메시지 없음). → 1장에서 정하고 9장에서 api-spec에 보충한다.
- `server_impl_plan.md` 2장 S6 표: 첫 확인 200 + 고정 Clock + 로그 1줄, 두 번째 200 + 처음 시각 + **로그 1줄 그대로**(두 번째는 쓰지 않음), 없는 ID 404, 확인 뒤 `?unacked=true`에서 빠짐. `AlertLogWriter`: `synchronized`, `Files.writeString(..., CREATE, APPEND)`, 부모 폴더 생성. CORS: `WebMvcConfigurer.addCorsMappings("/api/**")`.
- 계획과 다른 점(1장에서 고르고 9장에서 정정): `AlertController`를 `alert/` 대신 `api/`에 둔다(1장 #2), GET 응답 형식·기본값을 정한다(#6·#7).

## 1. 이번 계획에서 정한 것 (계획 대비)
| # | 항목 | 결정 | 이유 |
|---|---|---|---|
| 1 | 패키지 | `alert/`: `StoredAlert`, `AlertAck`, `AlertLogLine`, `AlertLogWriter` 추가, `AlertStore` 수정. `api/`: `AlertController`, `AckResponse`, `AlertView` 추가. `config/`: `CorsConfig` 추가 | 계획 1.1. `AlertLogWriter`는 파일 I/O라 `alert/`에 계획대로 둔다 |
| 2 | 컨트롤러 위치 | `api/AlertController` (계획 1.1은 `alert/`) | `acked_at`은 `frame_ts`와 같은 형식이어야 한다(`FrameTimestamps`, `ws`). `alert`가 `ws`를 쓰면 `ws → alert → ws` 순환이 된다. `api/`는 계획 1.1에 이미 있는 REST 자리(S7 `ZoneController`)다. 의존 `api → alert, ws, replay`는 한 방향이다 |
| 3 | `acked_at` 만드는 곳 | 컨트롤러가 `FrameTimestamps.now(clock)`로 만들어 `AlertStore.ack(alertId, ackedAt)`에 넘긴다. 저장소는 처음 값만 남긴다 | 저장소가 `ws`에 의존하지 않는다. 테스트는 고정 `Clock`을 컨트롤러에 넣어 정확한 값을 본다 |
| 4 | 확인 의미 | 처음 확인: `ackedAt` 기록, 미확인 목록에서 빠짐, 로그 1줄. 이미 확인: 200 + 처음 시각, 로그 없음. 없는 ID(처음부터 없음·상한으로 버려짐): 404 | api-spec 4.5, 계획 2장 S6 표. 멱등(idempotent): 같은 요청을 몇 번 보내도 결과와 기록이 같다. 화면 재시도·두 화면 동시 확인에 안전하다 |
| 5 | 확인한 알림 보관 | 구역마다 알림 목록 하나(`List<StoredAlert>`, 오래된 것 앞)에 미확인·확인을 함께 둔다. 상한(`unacked-alert-limit`)을 넘으면 **확인한 것 중 가장 오래된 것**을, 없으면 가장 오래된 미확인을 버린다 | 두 번째 확인이 처음 시각을 돌려주려면 확인한 알림을 기억해야 한다. 이 규칙이면 미확인 알림은 S5와 똑같이 "미확인이 상한을 넘을 때만" 버려지고(S5 테스트 그대로), 확인한 알림은 남는 자리만 쓴다. 메모리 상한은 구역당 `limit`개 그대로다. 목록이 하나라 순서(발급 순)가 저절로 맞는다. 대안 비교는 7.4절 |
| 6 | `GET .../alerts` 응답 | JSON 배열, 오래된 것부터. 원소 = `alert` 메시지 키 10개(api-spec 3.3) + `acked_at`(미확인이면 `null`) | 화면이 `hello.unacked_alerts`·`alert`와 같은 파서를 쓰고 `alert_id`로 거른다(S5 7.3 놓침 복구 경로). `acked_at`이 있어야 전체 목록에서 확인 여부가 보인다. `[토론]` 1 |
| 7 | `unacked` 기본값 | 빼면 `false`(보관 중인 전체), `true`면 미확인만. `true`·`false` 말고는 400(Spring 변환 오류) | api-spec "미확인만 **선택 가능**" = 기본은 전체. 보관 중인 전체는 최대 `limit`개다 |
| 8 | 없는 구역 GET | 404 | WS 없는 구역 4404와 같은 뜻. 알림이 없는 있는 구역은 200 `[]` |
| 9 | 오류 본문 | 404는 본문 없음(`ResponseEntity.notFound()`), 400은 Spring 기본 | api-spec이 오류 본문을 정하지 않았다. S7이 seek 400을 만들 때 오류 형식을 한 번에 정한다. `[토론]` 2 |
| 10 | 알림 로그 내용 | **처음 확인할 때만** 1줄: `{alert_id, zone_id, t, level, reason, sent_at, acked_at}`(api-spec 4.5 그대로, `sent_at` = `Alert.frameTs`). 발급은 기록하지 않는다(INFO 앱 로그만) | api-spec 4.5·계획 S6 표("두 번째: 로그 1줄"). 발급 줄을 더하면 줄 형식이 바뀐다. `[토론]` 3. 셀·구역 집계값과 ID·시각만이라 CLAUDE.md 데이터 규칙에 맞다(좌표·영상 없음) |
| 11 | 로그 쓰기 | `AlertLogWriter.append`: `synchronized`, 부모 폴더 `createDirectories`, `Files.writeString(UTF-8, CREATE, APPEND)`, 줄 끝 `\n`(LF). 시작할 때 절대 경로 INFO, 파일은 처음 쓸 때 만든다 | 계획 2장 S6. 열고 닫기를 매번 해서 열린 파일 핸들을 들고 있지 않는다(Windows에서 다른 프로그램이 열어도 서버가 잠그지 않음). 확인은 사람이 누르는 속도라 비용이 없다. `System.lineSeparator()`를 쓰면 Windows에서 CRLF가 된다 |
| 12 | 로그 쓰기 실패 | 예외를 밖으로 내지 않는다. ERROR 로그(경로·`alert_id`·쓰려던 줄)를 남기고 200을 돌려준다. 확인은 메모리에 이미 반영됐다 | 화면 상태(확인됨)와 서버 상태를 맞춘다. 줄 내용이 앱 로그에 남아 복구할 수 있다. 재생 스레드는 로그 파일을 쓰지 않으므로 디스크 문제가 재생을 멈추지 않는다. `[토론]` 4 |
| 13 | 로그 쓰기 위치 | 컨트롤러가 `AlertStore.ack` 뒤(저장소 잠금 밖)에 `firstAck`일 때만 부른다 | 저장소 잠금 안에서 디스크를 쓰면 재생 스레드 `issue`가 그동안 막힌다. `firstAck`는 잠금 안에서 정해지므로 동시에 두 번 확인해도 1줄만 쓴다 |
| 14 | 확인 대상 찾기 | `ack(alertId, ackedAt)`는 모든 구역 목록을 훑는다(최대 구역 수 × `limit`). ID 색인 맵 없음 | 경로에 구역이 없다(api-spec). 구역 1개 × 100개라 선형 탐색이 마이크로초다. 색인을 두면 상한으로 버릴 때 같이 지워야 해 일관성 버그 자리가 생긴다 |
| 15 | 확인을 다른 화면에 알림 | 하지 않는다(WS 메시지 없음) | api-spec에 없다. 다른 화면은 재접속 `hello`나 GET에서 빠진 것을 본다. 상황실 공용 화면 1~2개(가정). `[토론]` 5 |
| 16 | 확인과 재생 판정 | 확인은 판정(`AlertDetector`)에 영향이 없다. 확인한 `GRADE_UP` 뒤 더 높은 등급이면 새 알림이 온다. 반복 재생의 같은 사건은 새 ID라 따로 확인한다 | api-spec 3.3·4.2. 확인 = 사람이 봤다는 기록일 뿐이다 |
| 17 | 설정 | `crowdsight.alert-log: logs/alerts.jsonl`(`String`, 비거나 공백이면 시작 실패). `CrowdsightProperties`에 `ws` 다음, `corsOriginPatterns` 앞 | 계획 4장 yml 순서. `timeline-dir`처럼 `String`(PathEditor 회피). 이 PR이 읽으므로 이 PR에서 추가(CLAUDE.md 설정 규칙) |
| 18 | REST 허용 출처 | `config/CorsConfig implements WebMvcConfigurer`: `/api/**`, `allowedOriginPatterns(crowdsight.cors-origin-patterns)`, `allowedMethods("GET", "POST")`, 자격 증명 없음 | 결정 기록 2, api-spec 2절 "WebSocket과 REST 모두 같은 값". S7 재생 제어도 POST라 그대로 쓴다 |
| 19 | 테스트 도구 | `MockMvcTester` + `@AutoConfigureMockMvc`(통합), 컨트롤러는 평범한 Java 객체로도 시험(고정 `Clock`) | 계획 0장 "S6 테스트에 `@AutoConfigureMockMvc`". MockMvcTester는 AssertJ 단언(CLAUDE.md 테스트 규칙)이다. 통합 테스트 컨텍스트의 `Clock`은 시스템 시계라 정확한 `acked_at`은 단위 테스트에서 본다 |
| 20 | 테스트 로그 경로 | 통합 테스트는 `crowdsight.alert-log=build/test-logs/alerts.jsonl`, `@BeforeEach`에서 지운다. 단위 테스트는 `@TempDir` | 기본값 `logs/alerts.jsonl`이면 테스트가 `server/logs/`에 쓴다. `build/`는 git 제외. 다른 통합 테스트는 확인하지 않으므로 파일을 만들지 않는다(처음 쓸 때 생성, #11) |

## 2. 구조와 파일

### 2.1 추가·수정 파일
```text
server/
├─ README.md                                                     수정 (알림 확인 절, S5 절 한 줄)
├─ src/main/resources/application.yml                            수정 (alert-log, 주석 3곳)
├─ src/main/java/com/tripley/crowdsight/
│  ├─ config/  CrowdsightProperties (alertLog)                   수정
│  │           CorsConfig                                        추가
│  ├─ alert/   AlertStore (ack·list·보관 규칙), Alert (Javadoc)   수정
│  │           StoredAlert, AlertAck, AlertLogLine, AlertLogWriter   추가
│  └─ api/     AlertController, AckResponse, AlertView           추가 (새 패키지)
└─ src/test/java/com/tripley/crowdsight/
   ├─ CrowdsightServerApplicationIntegrationTest                 수정 (+1)
   ├─ config/   CrowdsightPropertiesTest (defaults, +3), TestProperties (ALERT_LOG, alertLog)   수정
   ├─ alert/    AlertStoreTest (+8), AlertLogWriterTest 추가
   └─ api/      AlertControllerTest, AlertControllerIntegrationTest   추가
docs/plans/server_s6_alert_ack_plan.md                           (이 문서)
docs/plans/server_impl_plan.md                                   정정 (9.1절)
docs/api-spec.md                                                 보충 (9.2절)
```
- 바뀌지 않는 것: `ws/`(메시지·`MessageFactory`·`WsZoneBroadcaster`·`ZoneWebSocketHandler`), `replay/`, `grade/`, `AlertDetector`, `AlertIdGenerator`, WS 메시지 형식, `hello.schema_version` `"0.2"`.

### 2.2 요청 흐름
```text
POST /api/alerts/{alertId}/ack            (Tomcat 요청 스레드)
  AlertController.ack
    ackedAt = FrameTimestamps.now(clock)
    AlertStore.ack(alertId, ackedAt)      ← synchronized. 모든 구역 목록에서 찾기
      없음          → 404
      이미 확인     → AlertAck(alert, 처음 ackedAt, firstAck=false)
      처음 확인     → 목록 원소를 StoredAlert(alert, ackedAt)로 바꿈, INFO → AlertAck(..., true)
    firstAck이면 AlertLogWriter.append(ack)   ← 저장소 잠금 밖, writer 자기 잠금. 실패는 ERROR만
    200 AckResponse(alert_id, acked_at)

GET /api/zones/{zoneId}/alerts?unacked=   (Tomcat 요청 스레드)
  ZoneRegistry.find(zoneId) 없음 → 404
  AlertStore.list(zoneId, unacked) → List<StoredAlert> (불변, 오래된 것부터)
  → List<AlertView> → 200

재생 (S5 그대로): WsZoneBroadcaster.zoneState → AlertStore.issue (상한: 확인한 것부터 버림)
접속 (S5 그대로): ZoneWebSocketHandler → AlertStore.unacked(zoneId) → hello
```

### 2.3 의존 방향
```text
api ──→ alert ──→ grade
 │ └──→ ws (FrameTimestamps)
 └──→ replay (ZoneRegistry)
ws ──→ alert          (S5 그대로)
config.CorsConfig ──→ config.CrowdsightProperties
alert.AlertLogWriter ──→ config, tools.jackson JsonMapper
```
- `alert`는 `api`·`ws`를 모른다. 순환 없음.

### 2.4 스레드 규칙
| 클래스 | 누가 부르나 | 규칙 |
|---|---|---|
| `AlertStore.issue` | 재생 스레드 | `synchronized` (S5) |
| `AlertStore.unacked` | Tomcat WS 스레드(hello) | `synchronized`, 불변 목록 |
| `AlertStore.ack`, `list` | Tomcat 요청 스레드(여럿 동시) | `synchronized`. `ack`의 "찾기 → 확인 여부 → 바꾸기"가 한 잠금 안이라 `firstAck`는 알림마다 한 번만 참 |
| `AlertLogWriter.append` | Tomcat 요청 스레드 | `synchronized`(writer 자신). 줄이 섞이지 않는다. 재생 스레드는 부르지 않는다 |
| `AlertController` | Tomcat 요청 스레드 | 상태 없음 |
| `StoredAlert`, `AlertAck`, `AlertLogLine`, `AckResponse`, `AlertView` | 어디서나 | 불변 record |
- 잠금 순서: `AlertStore` 잠금을 놓은 뒤 `AlertLogWriter` 잠금을 잡는다. 두 잠금을 같이 쥐는 곳이 없어 교착이 없다.

## 3. 설정

### 3.1 `application.yml` (수정분)
맨 위 주석에서 `(S6: alert-log)`를 뺀다(남은 키 없음). `ws:` 블록 다음, `cors-origin-patterns` 앞에 `alert-log`를 넣는다. `unacked-alert-limit` 주석을 보관 규칙에 맞게 고친다.
```yaml
# crowdsight.* 설정은 그 값을 읽는 클래스와 같은 PR에서 추가한다
crowdsight:
  # ... (그대로)
  unacked-alert-limit: 100                   # 구역당 보관 알림 최대 개수. 넘으면 확인한 것부터, 없으면 가장 오래된 미확인부터 버린다
  ws:
    # ... (그대로)
  alert-log: logs/alerts.jsonl               # 알림 확인 기록(JSON 한 줄씩). 작업 폴더(server/) 기준, git 제외(server/logs/)
  cors-origin-patterns: ["http://localhost:*", "http://127.0.0.1:*"]   # WS·REST(/api/**) 허용 출처 (결정 기록 2)
```

### 3.2 `config/CrowdsightProperties.java` (수정분)
```java
/**
 * ... (그대로)
 * (줄 삭제) alert-log는 그 값을 쓰는 PR(S6)에서 추가한다.
 *
 * @param unackedAlertLimit  구역당 보관 알림 최대 개수 (1 이상). 미확인은 이 개수를 넘을 때만 오래된 것부터 버린다
 * @param ws                 WebSocket 설정 (crowdsight.ws.*)
 * @param alertLog           알림 확인 기록 파일 (JSON 한 줄씩). 상대 경로면 작업 폴더(bootRun·test는 server/) 기준
 * @param corsOriginPatterns 허용 출처 패턴. WebSocket과 REST(/api/**)가 같이 쓴다 (결정 기록 2)
 */
@ConfigurationProperties("crowdsight")
public record CrowdsightProperties(String timelineDir, List<String> timelineFiles, String timeZone, Replay replay,
                                   GradeSettings grade, InstabilitySettings instability, InflowSettings inflow,
                                   int unackedAlertLimit, Ws ws, String alertLog, List<String> corsOriginPatterns) {

    public CrowdsightProperties {
        // ... ws 검사 다음에
        if (alertLog == null || alertLog.isBlank()) {
            throw new IllegalArgumentException("crowdsight.alert-log 가 없습니다.");
        }
        // ... corsOriginPatterns 검사 (그대로)
    }
```

### 3.3 `config/TestProperties.java` (수정분)
```java
    /** application.yml crowdsight.alert-log 기본값과 같다 (bindsDefaultAlertLog가 확인). */
    public static final String ALERT_LOG = "logs/alerts.jsonl";

    /** fixture 기본값에 알림 확인 기록 파일만 바꾼다. 단위 테스트는 @TempDir 아래 경로를 넘긴다. */
    public static CrowdsightProperties alertLog(String path) {
        return full("src/test/resources/timeline", List.of("valid_v02.json"), 1000, true, WS, path);
    }

    // of, ws는 full(..., ALERT_LOG)로 넘긴다
    private static CrowdsightProperties full(String dir, List<String> files, long intervalMs, boolean loop,
                                             CrowdsightProperties.Ws ws, String alertLog) {
        return new CrowdsightProperties(dir, files, TIME_ZONE, new CrowdsightProperties.Replay(intervalMs, loop),
                GRADE, INSTABILITY, INFLOW, UNACKED_ALERT_LIMIT, ws, alertLog, CORS);
    }
```
- 클래스 Javadoc "S3~S6이 성분을 늘리면 여기만 고친다"는 "설정 성분을 늘리면 여기만 고친다"로.

## 4. 저장소 확인 (`alert/`)

### 4.1 `alert/StoredAlert.java`, `alert/AlertAck.java` (추가)
```java
package com.tripley.crowdsight.alert;

import java.util.Objects;

/**
 * 저장소가 보관하는 알림 하나와 확인 시각. 불변이다. 확인하면 저장소가 새 값으로 바꿔 넣는다.
 *
 * @param alert   발급한 알림
 * @param ackedAt 처음 확인한 시각 (frame_ts 형식). 미확인이면 null
 */
public record StoredAlert(Alert alert, String ackedAt) {

    public StoredAlert {
        Objects.requireNonNull(alert, "alert");
    }

    /** 확인했는지. */
    public boolean acked() {
        return ackedAt != null;
    }
}
```
```java
package com.tripley.crowdsight.alert;

/**
 * 확인 요청 결과 (api-spec 4.5).
 *
 * @param alert    확인한 알림
 * @param ackedAt  처음 확인한 시각. 이미 확인한 알림이면 그때 시각
 * @param firstAck 이번 요청이 처음 확인이면 true. 이때만 확인 기록을 쓴다
 */
public record AlertAck(Alert alert, String ackedAt, boolean firstAck) {
}
```

### 4.2 `alert/AlertStore.java` (수정)
```java
/**
 * 구역별 알림 보관 (api-spec 3.1·3.3·4.5). 메모리에만 두고 서버를 재시작하면 비워진다.
 * 구역마다 발급 순 목록 하나에 미확인·확인한 알림을 함께 두고, unacked-alert-limit개를 넘으면
 * 확인한 것 중 가장 오래된 것을, 없으면 가장 오래된 미확인을 버린다. 그래서 미확인은 미확인만 limit개를 넘을 때 버려진다.
 * 확인(ack)은 처음 시각만 남기고, 다시 확인하면 그 시각을 돌려준다 (멱등).
 * 스레드 규칙: issue는 재생 스레드, unacked는 Tomcat WS 스레드(hello), ack·list는 Tomcat 요청 스레드가 부른다.
 * 모든 공개 메서드는 this로 잠근다. 덧붙이기·상한·확인 여부 판단을 한 번에 해야 해서 Concurrent 컬렉션 대신 잠금을 쓴다.
 * 잠금 안 작업은 최대 (구역 수 × limit)개 훑기이고 호출은 1초에 몇 번 이하다.
 */
@Slf4j
@Component
public final class AlertStore {

    private final int limit;
    private final AlertIdGenerator ids;
    private final Map<String, List<StoredAlert>> byZone = new HashMap<>();   // this 잠금 안에서만. 오래된 것 앞

    public AlertStore(CrowdsightProperties props, Clock clock) {
        this.limit = props.unackedAlertLimit();
        this.ids = new AlertIdGenerator(clock);
    }

    /** 사건에 ID·구역·t·frame_ts를 붙여 저장하고 돌려준다. 같은 초 zone_state의 t·frame_ts를 넘긴다. */
    public synchronized Alert issue(String zoneId, int t, String frameTs, AlertEvent event) {
        Alert alert = new Alert(ids.next(), zoneId, t, frameTs, event.level(), event.reason(), event.message(),
                event.value(), event.cellIds());
        List<StoredAlert> alerts = byZone.computeIfAbsent(zoneId, k -> new ArrayList<>());
        alerts.add(new StoredAlert(alert, null));
        log.info("알림 zone={} t={} alert_id={} reason={} level={} value={}", zoneId, t, alert.alertId(),
                alert.reason(), alert.level(), alert.value());
        if (alerts.size() > limit) {
            dropOne(zoneId, alerts);
        }
        return alert;
    }

    /** 구역의 미확인 알림 (오래된 것부터, hello용). 불변 목록이라 받은 뒤 바뀌지 않는다. 없는 구역은 빈 목록. */
    public synchronized List<Alert> unacked(String zoneId) {
        return byZone.getOrDefault(zoneId, List.of()).stream()
                .filter(s -> !s.acked())
                .map(StoredAlert::alert)
                .toList();
    }

    /** 구역의 보관 알림 (오래된 것부터). unackedOnly면 미확인만. 불변 목록. 없는 구역은 빈 목록. */
    public synchronized List<StoredAlert> list(String zoneId, boolean unackedOnly) {
        return byZone.getOrDefault(zoneId, List.of()).stream()
                .filter(s -> !unackedOnly || !s.acked())
                .toList();
    }

    /**
     * 알림을 확인한다. 처음이면 ackedAt을 기록하고 firstAck true, 이미 확인했으면 처음 시각과 false.
     * 보관 중이 아닌 ID(없음·상한으로 버려짐)는 빈 값.
     */
    public synchronized Optional<AlertAck> ack(String alertId, String ackedAt) {
        Objects.requireNonNull(ackedAt, "ackedAt");
        for (List<StoredAlert> alerts : byZone.values()) {
            for (int i = 0; i < alerts.size(); i++) {
                StoredAlert stored = alerts.get(i);
                if (!stored.alert().alertId().equals(alertId)) {
                    continue;
                }
                if (stored.acked()) {
                    return Optional.of(new AlertAck(stored.alert(), stored.ackedAt(), false));
                }
                alerts.set(i, new StoredAlert(stored.alert(), ackedAt));
                log.info("알림 확인 zone={} t={} alert_id={} acked_at={}", stored.alert().zoneId(), stored.alert().t(),
                        alertId, ackedAt);
                return Optional.of(new AlertAck(stored.alert(), ackedAt, true));
            }
        }
        return Optional.empty();
    }

    /** 상한을 넘은 목록에서 하나 버린다. 확인한 것 중 가장 오래된 것, 없으면 가장 오래된 미확인. */
    private void dropOne(String zoneId, List<StoredAlert> alerts) {
        for (int i = 0; i < alerts.size(); i++) {
            if (alerts.get(i).acked()) {
                StoredAlert dropped = alerts.remove(i);
                log.debug("보관 한도를 넘어 확인한 알림을 버림 zone={} alert_id={}", zoneId, dropped.alert().alertId());
                return;
            }
        }
        StoredAlert dropped = alerts.remove(0);
        log.warn("미확인 알림이 {}개를 넘어 가장 오래된 알림을 버림 zone={} alert_id={}", limit, zoneId,
                dropped.alert().alertId());
    }
}
```
- `ArrayDeque` → `ArrayList`: 확인하면 그 자리 원소를 바꾸고(`set`) 확인한 것을 중간에서 지워야(`remove(i)`) 한다. 길이 ≤ 100이라 O(n)이 문제없다.
- `Stream.toList()`는 수정 불가 목록이다. S5 `unackedIsSnapshot`(추가 시 `UnsupportedOperationException`)이 그대로 통과한다.
- `Alert.java` Javadoc: "S6 확인 기록의 sent_at은 frameTs다" → "확인 기록(alerts.jsonl)의 sent_at은 frameTs다".

## 5. 확인 기록 파일 (`alert/`)

### 5.1 `alert/AlertLogLine.java` (추가)
```java
package com.tripley.crowdsight.alert;

import com.tripley.crowdsight.grade.Grade;

/**
 * logs/alerts.jsonl 한 줄 (api-spec 4.5). 키 순서는 성분 순서다. 셀·구역 집계와 ID·시각만 담는다 (CLAUDE.md 데이터 규칙).
 *
 * @param alertId 알림 ID
 * @param zoneId  구역 ID
 * @param t       알림이 생긴 프레임 t
 * @param level   알림 등급
 * @param reason  알림 이유
 * @param sentAt  알림을 보낸 시각 (Alert.frameTs)
 * @param ackedAt 처음 확인한 시각
 */
public record AlertLogLine(String alertId, String zoneId, int t, Grade level, AlertReason reason, String sentAt,
                           String ackedAt) {

    /** 확인 결과에서 만든다. */
    public static AlertLogLine of(AlertAck ack) {
        Alert a = ack.alert();
        return new AlertLogLine(a.alertId(), a.zoneId(), a.t(), a.level(), a.reason(), a.frameTs(), ack.ackedAt());
    }
}
```

### 5.2 `alert/AlertLogWriter.java` (추가)
```java
package com.tripley.crowdsight.alert;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

import org.springframework.stereotype.Component;

import com.tripley.crowdsight.config.CrowdsightProperties;

import lombok.extern.slf4j.Slf4j;
import tools.jackson.databind.json.JsonMapper;

/**
 * 알림 확인 기록을 crowdsight.alert-log 파일에 JSON 한 줄씩 덧붙인다 (api-spec 4.5, JSON Lines, UTF-8, LF).
 * 파일과 부모 폴더는 처음 쓸 때 만든다. 쓸 때마다 열고 닫아 파일을 잡고 있지 않는다.
 * 쓰기에 실패하면 예외를 내지 않고 ERROR 로그에 쓰려던 줄을 남긴다 (확인 자체는 이미 반영됨).
 * 스레드 규칙: Tomcat 요청 스레드가 부른다. append는 this로 잠가 줄이 섞이지 않는다. 재생 스레드는 부르지 않는다.
 */
@Slf4j
@Component
public final class AlertLogWriter {

    private final Path path;
    private final JsonMapper jsonMapper;

    public AlertLogWriter(CrowdsightProperties props, JsonMapper jsonMapper) {
        this.path = Path.of(props.alertLog()).toAbsolutePath().normalize();
        this.jsonMapper = jsonMapper;
        log.info("알림 확인 기록 파일 path={}", path);
    }

    /** 확인 한 건을 한 줄로 덧붙인다. 처음 확인(AlertAck.firstAck)일 때만 부른다. */
    public synchronized void append(AlertAck ack) {
        String line = jsonMapper.writeValueAsString(AlertLogLine.of(ack));
        try {
            Path parent = path.getParent();
            if (parent != null) {
                Files.createDirectories(parent);
            }
            Files.writeString(path, line + "\n", StandardCharsets.UTF_8, StandardOpenOption.CREATE,
                    StandardOpenOption.APPEND);
        } catch (IOException e) {
            log.error("알림 확인 기록을 쓰지 못함 path={} alert_id={} 줄={}", path, ack.alert().alertId(), line, e);
        }
    }
}
```
- 단위 테스트는 `new AlertLogWriter(TestProperties.alertLog(tempDir.resolve(...).toString()), TimelineFixtures.MAPPER)`로 만든다(`MAPPER`는 `SNAKE_CASE`, application.yml과 같다).
- `JsonMapper` 빈은 Boot가 만든다(S3 `WsZoneBroadcaster`가 이미 주입받음).

## 6. REST (`api/`, `config/`)

### 6.1 `config/CorsConfig.java` (추가)
```java
package com.tripley.crowdsight.config;

import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.CorsRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

import lombok.RequiredArgsConstructor;

/** REST /api/** 허용 출처 (api-spec 2절, 결정 기록 2). WebSocket(WebSocketConfig)과 같은 패턴을 쓴다. */
@Configuration(proxyBeanMethods = false)
@RequiredArgsConstructor
public class CorsConfig implements WebMvcConfigurer {

    private final CrowdsightProperties props;

    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/api/**")
                .allowedOriginPatterns(props.corsOriginPatterns().toArray(String[]::new))
                .allowedMethods("GET", "POST");
    }
}
```
- 자격 증명(쿠키)은 쓰지 않으므로 `allowCredentials`는 기본(false). 허용 헤더는 기본(`*`). S7 `POST .../playback`(JSON 본문 → 사전 요청)도 이 설정으로 된다.

### 6.2 `api/AckResponse.java`, `api/AlertView.java` (추가)
```java
package com.tripley.crowdsight.api;

/**
 * 알림 확인 응답 (api-spec 4.5).
 *
 * @param alertId 확인한 알림 ID
 * @param ackedAt 처음 확인한 시각 (frame_ts 형식)
 */
public record AckResponse(String alertId, String ackedAt) {
}
```
```java
package com.tripley.crowdsight.api;

import java.util.List;

import com.tripley.crowdsight.alert.Alert;
import com.tripley.crowdsight.alert.AlertReason;
import com.tripley.crowdsight.alert.StoredAlert;
import com.tripley.crowdsight.grade.Grade;

/**
 * GET /api/zones/{zone_id}/alerts 원소. alert 메시지(api-spec 3.3)와 같은 키에 acked_at을 더한다.
 *
 * @param type    "alert" (화면이 alert 메시지와 같은 파서를 쓰도록)
 * @param alertId 알림 ID
 * @param zoneId  구역 ID
 * @param t       알림이 생긴 프레임 t
 * @param frameTs 보낸 시각
 * @param level   알림 등급
 * @param reason  알림 이유
 * @param message 한국어 문구
 * @param value   최대 밀도·유입 5초 평균·최대 압력
 * @param cellIds 관련 셀 (meta 순서)
 * @param ackedAt 처음 확인한 시각. 미확인이면 null
 */
public record AlertView(String type, String alertId, String zoneId, int t, String frameTs, Grade level,
                        AlertReason reason, String message, Double value, List<String> cellIds, String ackedAt) {

    public static final String TYPE = "alert";

    public AlertView {
        cellIds = List.copyOf(cellIds);
    }

    /** 보관 알림에서 만든다. */
    public static AlertView of(StoredAlert stored) {
        Alert a = stored.alert();
        return new AlertView(TYPE, a.alertId(), a.zoneId(), a.t(), a.frameTs(), a.level(), a.reason(), a.message(),
                a.value(), a.cellIds(), stored.ackedAt());
    }
}
```

### 6.3 `api/AlertController.java` (추가)
```java
package com.tripley.crowdsight.api;

import java.time.Clock;
import java.util.List;
import java.util.Optional;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import com.tripley.crowdsight.alert.AlertAck;
import com.tripley.crowdsight.alert.AlertLogWriter;
import com.tripley.crowdsight.alert.AlertStore;
import com.tripley.crowdsight.replay.ZoneRegistry;
import com.tripley.crowdsight.ws.FrameTimestamps;

import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;

/**
 * 알림 확인과 알림 목록 REST (api-spec 2절·4.5).
 * 확인은 처음 시각만 남기고(멱등), 처음 확인일 때만 확인 기록 파일에 한 줄을 쓴다. 확인은 다른 화면에 방송하지 않는다.
 * 스레드 규칙: Tomcat 요청 스레드에서 동시에 불린다. 상태가 없고, 저장소·기록 파일이 각자 잠근다.
 */
@Slf4j
@RestController
@RequestMapping("/api")
@RequiredArgsConstructor
public class AlertController {

    private final AlertStore alerts;
    private final AlertLogWriter alertLog;
    private final ZoneRegistry zones;
    private final Clock clock;

    /** 알림 확인. 200 {alert_id, acked_at}, 이미 확인했으면 처음 시각, 보관 중이 아니면 404. */
    @PostMapping("/alerts/{alertId}/ack")
    public ResponseEntity<AckResponse> ack(@PathVariable String alertId) {
        Optional<AlertAck> result = alerts.ack(alertId, FrameTimestamps.now(clock));
        if (result.isEmpty()) {
            log.info("없는 알림 확인 요청 alert_id={}", alertId);
            return ResponseEntity.notFound().build();
        }
        AlertAck ack = result.get();
        if (ack.firstAck()) {
            alertLog.append(ack);
        }
        return ResponseEntity.ok(new AckResponse(alertId, ack.ackedAt()));
    }

    /** 구역 알림 목록 (오래된 것부터). unacked=true면 미확인만. 없는 구역은 404. */
    @GetMapping("/zones/{zoneId}/alerts")
    public ResponseEntity<List<AlertView>> alerts(@PathVariable String zoneId,
                                                  @RequestParam(defaultValue = "false") boolean unacked) {
        if (zones.find(zoneId).isEmpty()) {
            return ResponseEntity.notFound().build();
        }
        return ResponseEntity.ok(alerts.list(zoneId, unacked).stream().map(AlertView::of).toList());
    }
}
```
- `ResponseEntity<List<AlertView>>`에서 `notFound().build()`는 `ResponseEntity<Object>`가 아니라 제네릭 추론으로 맞는다(`HeadersBuilder.build()`가 `<T> ResponseEntity<T>`).
- 컨트롤러는 상태가 없어 `final`로 두지 않는다(`MessageFactory`와 같음).

## 7. 확인 의미·동시성·로그 정리

### 7.1 확인 의미 표
| 경우 | 응답 | 저장소 | `alerts.jsonl` |
|---|---|---|---|
| 미확인 알림 처음 확인 | 200 `{alert_id, acked_at: 지금}` | `ackedAt` 기록. `unacked`·`?unacked=true`·다음 hello에서 빠짐 | 1줄 |
| 이미 확인한 알림 | 200 `{alert_id, acked_at: 처음 시각}` | 그대로 | 없음 |
| 두 화면이 동시에 확인 | 둘 다 200, 같은 `acked_at` | 한 번만 기록(잠금 안에서 `firstAck` 결정) | 1줄 |
| 없는 ID, 상한으로 버려진 ID | 404, 본문 없음 | 그대로 | 없음 |
| 서버 재시작 전 ID | 같은 번호의 새 알림이 없으면 404. **있으면 그 새 알림이 확인된다** | — | 1줄(다른 알림) |
| 반복 재생으로 같은 사건이 새 ID | 각각 따로 확인 | — | 각각 1줄 |
| 기록 파일 쓰기 실패 | 200 (확인 반영) | `ackedAt` 기록 | 없음, ERROR 로그에 줄 내용 |
- 확인은 판정에 영향이 없다. 확인한 `GRADE_UP` 사건에서 등급이 더 오르면 새 `GRADE_UP`이 온다(S5 규칙 그대로).
- 재시작 전 ID 문제: 화면이 서버 재시작을 넘어 예전 알림을 들고 있다가 확인하면 번호가 같은 새 알림을 확인할 수 있다(S5 `[토론]` 5가 S6에서 실제 위험이 됨). 화면은 재접속 `hello`를 받을 때 미확인 목록을 `hello.unacked_alerts`로 **바꿔야**(합치지 않고) 예전 ID가 사라진다. 서버에서 막으려면 ID에 시작 시각을 넣어야 한다(형식 변경). `[토론]` 6.

### 7.2 동시성
- 재생 스레드 `issue`(상한으로 버리기 포함)와 요청 스레드 `ack`·`list`는 `AlertStore` 잠금 하나로 직렬화된다. 확인과 버리기가 겹치면 둘 중 먼저 잠근 쪽 결과를 따른다(버린 뒤 확인 → 404, 확인 뒤 버리기 → 확인한 것이 먼저 버려질 수 있음).
- hello와 확인의 경쟁: 접속 스레드가 `unacked`를 읽은 뒤 다른 화면이 확인하면, 새 화면 hello에 이미 확인한 알림이 들어간다. 그 화면에서 다시 확인하면 200 + 같은 시각, 로그 없음(멱등). 해가 없다.
- S5 7.3 "접속과 발송 사이 드문 놓침"은 이제 `GET /api/zones/{zone_id}/alerts?unacked=true`로 복구할 수 있다(화면이 hello 뒤 한 번 부르면 완전히 메운다). 서버 변경은 없다. `[토론]` 7.
- 로그 쓰기는 저장소 잠금 밖이다. 디스크가 느려도 재생 스레드 `issue`와 접속 hello는 막히지 않는다. 막히는 것은 확인 요청 자신과 동시에 들어온 다른 확인 요청뿐이다.

### 7.3 `alerts.jsonl` 설계
| 항목 | 설계 |
|---|---|
| 형식 | JSON Lines: 한 줄 = JSON 객체 1개, UTF-8, `\n`. 줄 안에 줄바꿈 없음(`JsonMapper` 기본은 들여쓰기 없음, 문자열의 줄바꿈은 `\n` 이스케이프) |
| 키 | `alert_id, zone_id, t, level, reason, sent_at, acked_at` (api-spec 4.5 순서). 셀 ID·값·문구는 넣지 않는다 |
| 언제 | 처음 확인할 때만 |
| 위치 | `crowdsight.alert-log`(기본 `logs/alerts.jsonl`, 작업 폴더 `server/` 기준 → `server/logs/alerts.jsonl`). 시작 INFO에 절대 경로 |
| 만들기 | 처음 쓸 때 부모 폴더 `createDirectories`, 파일 `CREATE` |
| 덧붙이기 | `APPEND`. 서버를 다시 켜도 이어 쓴다. 지우거나 돌리지(rotate) 않는다(시연 규모: 줄당 약 200 B, 확인 수백 건) |
| 원자성 | `synchronized` + 한 번의 `writeString` → 서버 안에서 줄이 섞이지 않는다. 서버 두 개가 같은 파일을 쓰는 경우는 없다(가정) |
| 내구성 | 닫을 때 OS로 넘어간다. fsync(`SYNC`)는 하지 않는다: 전원이 꺼지면 마지막 몇 줄이 빠질 수 있다. 시연 기록 용도라 충분하다 |
| 실패 | `IOException`을 잡아 ERROR(경로, `alert_id`, 줄). 응답은 200 |
| 개인정보 | ID·구역·t·등급·이유·시각만. 영상·좌표·사용자 정보 없음(CLAUDE.md) |

### 7.4 보관 규칙 대안
| 후보 | 판단 |
|---|---|
| **목록 하나 + 확인한 것부터 버림 (고름)** | 미확인 버리기는 S5와 같다(미확인만으로 limit 초과일 때). 메모리 ≤ limit. 발급 순서가 저절로 유지된다. 두 번째 확인·전체 목록이 된다 |
| 확인하면 목록에서 지우고 `alertId → ackedAt` 맵만 남김 | 맵이 끝없이 커진다(30분 반복이면 수십 개라 작지만 상한이 없다). 전체 목록(`unacked=false`)을 줄 수 없다 |
| 미확인 목록 + 확인 목록 따로(각 limit) | 메모리 2배, 전체 목록을 주려면 두 목록을 발급 순으로 합쳐야 한다(번호 비교, 9999 넘으면 자릿수 변화) |
| 목록 하나 + 상태 무관하게 가장 오래된 것 버림 | 단순하지만 확인한 알림이 미확인 알림 자리를 차지해 미확인이 S5보다 일찍 버려진다 |
- 설정 이름 `unacked-alert-limit`은 그대로 둔다. 미확인 개수의 상한이라는 뜻은 그대로 참이고, 확인한 알림은 남는 자리만 쓴다. 이름을 바꾸면 S5 문서·api-spec·yml을 다시 고쳐야 한다.

## 8. 테스트
공통 상수 (단위 테스트):
```java
static final Clock FIXED = Clock.fixed(Instant.parse("2026-11-18T05:02:36.910Z"), ZoneId.of("Asia/Seoul"));
static final String ACKED_TS = "2026-11-18T14:02:36.910+09:00";
static final String LATER_TS = "2026-11-18T14:02:40.000+09:00";          // Instant 05:02:40Z
static final String SENT_TS = "2026-11-18T14:02:31.512+09:00";
```

### 8.1 `config/CrowdsightPropertiesTest` (수정·추가), `CrowdsightServerApplicationIntegrationTest` (+1)
- `defaults()`에 `map.put("crowdsight.alert-log", "logs/alerts.jsonl")`.

| 메서드 | 입력 | 기대 |
|---|---|---|
| `bindsAlertLog` `@DisplayName("알림 확인 기록 파일 경로를 묶는다")` | defaults | `alertLog()` = `"logs/alerts.jsonl"` |
| `rejectsBlankAlertLog` (`@ValueSource(strings = {"", " "})`) `"알림 확인 기록 경로가 비면 거부한다"` | 빈 값 | `BindException`, root cause 메시지에 `crowdsight.alert-log` |
| `rejectsMissingAlertLog` `"알림 확인 기록 경로가 없으면 거부한다"` | 키 삭제 | 같음 |
| `CrowdsightServerApplicationIntegrationTest.bindsDefaultAlertLog` `"application.yml의 알림 확인 기록 경로를 읽는다"` | yml | `props.alertLog()` = `TestProperties.ALERT_LOG` |

### 8.2 `alert/AlertStoreTest` (추가 8, 기존 6 그대로)
`store = new AlertStore(TestProperties.replay(1000, true), FIXED)` (기존 `FIXED`는 05:02:31.512Z, ID 날짜 20261118).

| 메서드 | `@DisplayName` | 입력 | 기대 |
|---|---|---|---|
| `ackMarksFirstTime` | 처음 확인하면 그 시각을 남기고 처음 확인이라고 알린다 | issue 1개(`a-20261118-0001`), `ack(id, ACKED_TS)` | `Optional.of(new AlertAck(alert, ACKED_TS, true))` |
| `ackTwiceKeepsFirstTime` | 다시 확인하면 처음 시각을 돌려주고 처음 확인이 아니다 | ack(ACKED_TS) 뒤 ack(LATER_TS) | 두 번째 `AlertAck(alert, ACKED_TS, false)` |
| `ackUnknownIdIsEmpty` | 보관 중이 아닌 ID는 빈 값 | 빈 저장소에 `ack("a-20261118-9999", ACKED_TS)` | `Optional.empty()` |
| `unackedExcludesAcked` | 확인한 알림은 미확인 목록에서 빠진다 | issue 3개, 2번째 ack | `unacked` ID `[-0001, -0003]`, `list(zone, true)`도 같은 ID |
| `listAllKeepsIssueOrderWithAckedAt` | 전체 목록은 발급 순이고 확인 시각을 담는다 | issue 3개, 2번째 ack | `list(zone, false)` ID `[-0001, -0002, -0003]`, `ackedAt` `[null, ACKED_TS, null]`, 수정 시 `UnsupportedOperationException` |
| `ackFindsAlertInAnyZone` | 구역을 몰라도 ID로 찾는다 | zone-a 1개(-0001), zone-b 1개(-0002), `ack(-0002)` | present, `alert().zoneId()` = zone-b, `unacked(zone-b)` 비어 있음, `unacked(zone-a)` 1개 |
| `capDropsOldestAckedFirst` | 상한을 넘으면 확인한 것부터 버린다 | issue 100개, `-0050` ack, issue 1개 더(-0101) | `list(false)` 100개에 `-0050` 없음, `unacked` 100개(첫 `-0001`, 끝 `-0101`), `ack(-0050)` 빈 값 |
| `concurrentAckCountsFirstOnce` | 두 스레드가 같은 알림들을 확인해도 처음 확인은 알림마다 한 번이다 | issue 50개, 스레드 2개가 `CountDownLatch` 뒤 50개 ID를 모두 `ack(id, ACKED_TS)` | `firstAck` true 개수 합 50, 모든 결과 present, `unacked` 비어 있음 |
- 기존 `capDropsOldest`(확인 없이 101개 → 첫 알림 빠짐)·`concurrentIssueAndRead`는 바뀌지 않고 통과해야 한다(S5 동작 보존).

### 8.3 `alert/AlertLogWriterTest` (추가, `@TempDir Path dir`)
`ack = new AlertAck(new Alert("a-20261118-0001", "zone-test", 3, SENT_TS, ALERT, GRADE_UP, "구역 등급이 주의 → 경계로 올랐다", 4.3, List.of("c-0000")), ACKED_TS, true)`.

| 메서드 | `@DisplayName` | 입력 | 기대 |
|---|---|---|---|
| `appendCreatesFileAndWritesOneLine` | 폴더가 없어도 만들고 JSON 한 줄을 쓴다 | path `dir/logs/alerts.jsonl`(logs 없음), append 1번 | 파일 내용이 정확히 `{"alert_id":"a-20261118-0001","zone_id":"zone-test","t":3,"level":"ALERT","reason":"GRADE_UP","sent_at":"2026-11-18T14:02:31.512+09:00","acked_at":"2026-11-18T14:02:36.910+09:00"}` + `"\n"` |
| `appendKeepsEarlierLines` | 덧붙이고 앞 줄을 지우지 않는다 | 파일에 `"{\"old\":1}\n"`을 미리 쓰고 append 2번(ID -0001, -0002) | `Files.readAllLines` 3줄, 1번째 `{"old":1}`, 3번째 `alert_id` -0002 |
| `appendUsesLfOnly` | 줄 끝은 LF이고 CR이 없다 | append 2번 | 바이트에 `\r` 없음, `\n` 2개 |
| `appendFailureDoesNotThrow` | 쓰지 못해도 예외를 내지 않는다 | `dir/blocker`를 일반 파일로 만들고 path `dir/blocker/alerts.jsonl` | `assertThatNoException()`, `dir/blocker`는 여전히 일반 파일 |

### 8.4 `api/AlertControllerTest` (추가, 평범한 Java 객체)
```java
@TempDir Path dir;
CrowdsightProperties props;  AlertStore store;  AlertLogWriter writer;  ZoneRegistry zones;  AlertController controller;
Path logFile;

@BeforeEach
void setUp() {
    logFile = dir.resolve("alerts.jsonl");
    props = TestProperties.alertLog(logFile.toString());
    store = new AlertStore(props, FIXED);
    writer = new AlertLogWriter(props, MAPPER);
    zones = new ZoneRegistry(new TimelineLoader(MAPPER, props), props);   // fixture zone-test
    controller = new AlertController(store, writer, zones, FIXED);
}
// 알림은 store.issue("zone-test", 3, SENT_TS, new AlertEvent(ALERT, GRADE_UP, "…", 4.3, List.of("c-0000")))
```

| 메서드 | `@DisplayName` | 입력 | 기대 |
|---|---|---|---|
| `ackReturnsAckedAtAndWritesLog` | 처음 확인하면 고정 시각을 돌려주고 기록 한 줄을 쓴다 | issue 1, `controller.ack(id)` | status 200, body `new AckResponse(id, ACKED_TS)`, 파일 1줄 = 8.3 첫 줄과 같은 JSON |
| `secondAckReturnsFirstTimeWithoutNewLine` | 다시 확인하면 처음 시각이고 기록을 더하지 않는다 | 첫 ack 뒤 `new AlertController(store, writer, zones, Clock.fixed(05:02:40Z))`로 ack | 200, `ackedAt` = `ACKED_TS`, 파일 1줄 |
| `unknownAlertIs404` | 없는 알림이면 404이고 기록 파일을 만들지 않는다 | `ack("a-20261118-9999")` | status 404, body null, `Files.notExists(logFile)` |
| `listUnackedExcludesAcked` | 미확인만 고르면 확인한 알림이 빠진다 | issue 2(-0001, -0002), -0001 ack, `alerts("zone-test", true)` | 200, body 1개, `alertId` -0002, `ackedAt` null, `type` "alert" |
| `listAllIncludesAckedAt` | 전체 목록은 확인 시각을 담아 발급 순으로 준다 | 같은 상태, `alerts("zone-test", false)` | ID `[-0001, -0002]`, `ackedAt` `[ACKED_TS, null]` |
| `listUnknownZoneIs404` | 없는 구역이면 404 | `alerts("zone-nope", false)` | 404 |
| `listEmptyZoneIsEmptyArray` | 알림이 없는 구역은 빈 목록 | `alerts("zone-test", true)` | 200, body `[]` |

### 8.5 `api/AlertControllerIntegrationTest` (추가)
```java
@SpringBootTest(properties = {
        "crowdsight.timeline-dir=src/test/resources/timeline",
        "crowdsight.timeline-files=valid_v02.json",
        "crowdsight.alert-log=build/test-logs/alerts.jsonl"
})
@AutoConfigureMockMvc
class AlertControllerIntegrationTest {

    private static final Path LOG = Path.of("build/test-logs/alerts.jsonl");
    private static final Pattern TS = Pattern.compile("\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}\\.\\d{3}\\+09:00");

    @Autowired private MockMvcTester mvc;
    @Autowired private AlertStore alerts;

    @BeforeEach
    void clearLog() throws IOException {
        Files.deleteIfExists(LOG);
    }

    private Alert issue() {
        return alerts.issue("zone-test", 3, "2026-11-18T14:02:31.512+09:00", new AlertEvent(Grade.ALERT,
                AlertReason.GRADE_UP, "구역 등급이 주의 → 경계로 올랐다", 4.3, List.of("c-0000")));
    }

    private static JsonNode json(MvcTestResult result) throws Exception {
        return MAPPER.readTree(result.getResponse().getContentAsString(StandardCharsets.UTF_8));
    }
```

| 메서드 | `@DisplayName` | 요청 | 기대 |
|---|---|---|---|
| `ackOverHttp` | HTTP로 확인하면 alert_id·acked_at을 돌려주고 기록 파일에 한 줄을 쓴다 | issue → `POST /api/alerts/{id}/ack` | 200, `Content-Type` `application/json` 호환, 키 정확히 `alert_id, acked_at`, `acked_at` ~ `TS`, `LOG` 1줄의 키 정확히 7개(4.5 순서)이고 `alert_id` = id, `acked_at` = 응답 값 |
| `ackUnknownOverHttpIs404` | 없는 알림 확인은 404 | `POST /api/alerts/a-19990101-0001/ack` | 404, `LOG` 없음 |
| `listUnackedOverHttp` | 미확인 목록에서 확인한 알림이 빠지고 원소 키가 정해져 있다 | issue 2, 1번째 ack, `GET /api/zones/zone-test/alerts?unacked=true` | 200, 배열에 2번째 ID 있고 1번째 없음, 원소 키 정확히 `type, alert_id, zone_id, t, frame_ts, level, reason, message, value, cell_ids, acked_at`, `message` = 한국어 문구 그대로, `acked_at` null |
| `invalidUnackedParamIs400` | unacked 값이 불리언이 아니면 400 | `GET .../alerts?unacked=abc` | 400 |
| `listUnknownZoneOverHttpIs404` | 없는 구역 알림 목록은 404 | `GET /api/zones/zone-nope/alerts` | 404 |
| `corsPreflightAllowsLocalOrigin` (`@ValueSource(strings = {"http://localhost:5173", "http://127.0.0.1:5173"})`) | 허용 출처의 사전 요청을 받아 준다 | `OPTIONS /api/alerts/x/ack`, `Origin`, `Access-Control-Request-Method: POST` | 200, `Access-Control-Allow-Origin` = origin |
| `corsRejectsForeignOrigin` | 허용하지 않는 출처는 403 | 같은 사전 요청, `Origin: http://example.com` | 403 |
- 통합 컨텍스트의 `AlertStore`는 같은 클래스 테스트끼리 공유된다. 그래서 단언은 각 테스트가 발급한 ID로 찾는다(S5 `helloCarriesUnackedAlerts`와 같은 방식). fixture 재생은 알림을 만들지 않는다.
- 단언 예:
```java
MvcTestResult result = mvc.post().uri("/api/alerts/{id}/ack", alert.alertId()).exchange();
assertThat(result).hasStatusOk();
JsonNode body = json(result);
assertThat(body.propertyNames()).containsExactly("alert_id", "acked_at");
assertThat(body.get("acked_at").asString()).matches(TS);

assertThat(mvc.options().uri("/api/alerts/x/ack")
        .header(HttpHeaders.ORIGIN, origin)
        .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "POST"))
        .hasStatusOk()
        .hasHeader(HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN, origin);
```

## 9. 문서 정정 (이 PR의 docs 커밋)

### 9.1 `server_impl_plan.md`
1. 1.1 패키지: `alert/` 줄 `AlertLogWriter, AlertController (S6)` → `StoredAlert, AlertAck, AlertLogLine, AlertLogWriter (S6)`. `api/` 줄 → `AlertController, AckResponse, AlertView (S6), ZoneController, HealthController (S7)`.
2. 2장 S5 코드 블록 주석 `// find(alertId)·ack(alertId)는 S6` → `// ack(alertId, ackedAt)·list(zoneId, unackedOnly)는 S6`.
3. 2장 S6 절: GET 응답(원소 = `alert` 키 + `acked_at`, `unacked` 기본 false, 없는 구역 404), 보관 규칙(확인한 것부터 버림), 로그는 처음 확인만, 쓰기 실패 200 + ERROR, 컨트롤러 `api/`. 표에 "두 번째: 로그 **그대로** 1줄"로 뜻을 분명히. "상세는 `docs/plans/server_s6_alert_ack_plan.md` 8장".
4. 4장 yml: `unacked-alert-limit` 주석을 3.1절과 같게.
5. 5장 동시성 "미확인 알림" 행: "쓰기 재생 스레드(issue)·요청 스레드(ack), 읽기 hello·REST. 로그 파일은 저장소 잠금 밖(S6 계획 7.2)".

### 9.2 `docs/api-spec.md` (보충. WS 형식 변경 없음 → v0.2 유지)
1. 문서 상태 표에 한 줄: "S6 보충(11-13): `GET .../alerts` 응답 형식, 확인 세부(4.5)".
2. 2절 표 `GET /api/zones/{zone_id}/alerts` 설명: "알림 목록 (오래된 것부터). `unacked=true`면 미확인만, 빼면 보관 중인 전체".
3. 3.1 `unacked_alerts` 줄: "구역당 최근 100개" → "미확인만, 구역당 최대 100개(`crowdsight.unacked-alert-limit`). 확인한 알림은 남는 자리에만 보관한다".
4. 4.5 아래에 추가:
   - "알림 목록 `GET /api/zones/{zone_id}/alerts?unacked=true|false`: 원소는 3.3 `alert`와 같은 키에 `acked_at`(미확인이면 `null`)을 더한다. `unacked`를 빼면 `false`. 없는 구역은 `404`, `unacked`가 불리언이 아니면 `400`."
   - "기록은 처음 확인할 때만 한 줄이다. 줄은 UTF-8, LF. 기록을 쓰지 못해도 확인은 반영되고 `200`이다(서버 ERROR 로그에 줄을 남긴다)."
   - "확인은 다른 화면에 WebSocket으로 알리지 않는다. 다른 화면은 재접속 `hello`나 이 목록에서 빠진 것을 본다 (가정)."
   - "서버를 재시작하면 알림 번호가 1부터 다시 시작한다. 화면은 `hello`를 받으면 미확인 목록을 `unacked_alerts`로 바꾼다(예전 ID를 버린다)."
   - "`404` 본문은 없다. 오류 본문 형식은 재생 제어(5절)와 함께 정한다 `[토론]`."
5. 10절에 안건 추가: 20 "확인을 다른 화면에 알릴지(`alert_ack` 메시지)" 초안 "알리지 않음", 나예린. 21 "재시작 뒤 같은 알림 번호" 초안 "화면이 hello로 목록 교체", 조영준·나예린.

## 10. 출력 예시 (PR 설명·나예린 님 전달용)

### 10.1 확인
```http
POST /api/alerts/a-20261118-0007/ack HTTP/1.1
Origin: http://localhost:5173

HTTP/1.1 200
Access-Control-Allow-Origin: http://localhost:5173
Content-Type: application/json

{"alert_id":"a-20261118-0007","acked_at":"2026-11-18T14:02:36.910+09:00"}
```
- 같은 요청을 다시 보내면 같은 본문(처음 `acked_at`). 없는 ID면 `HTTP/1.1 404`, 본문 없음.

### 10.2 `logs/alerts.jsonl` (처음 확인 1건 = 1줄)
```json
{"alert_id":"a-20261118-0007","zone_id":"zone-e04-039","t":121,"level":"ALERT","reason":"GRADE_UP","sent_at":"2026-11-18T14:02:32.508+09:00","acked_at":"2026-11-18T14:02:36.910+09:00"}
```

### 10.3 목록
```http
GET /api/zones/zone-e04-039/alerts HTTP/1.1

HTTP/1.1 200
Content-Type: application/json

[
  {"type":"alert","alert_id":"a-20261118-0007","zone_id":"zone-e04-039","t":121,
   "frame_ts":"2026-11-18T14:02:32.508+09:00","level":"ALERT","reason":"GRADE_UP",
   "message":"구역 등급이 주의 → 경계로 올랐다","value":4.3,"cell_ids":["c-0412","c-0413"],
   "acked_at":"2026-11-18T14:02:36.910+09:00"},
  {"type":"alert","alert_id":"a-20261118-0008","zone_id":"zone-e04-039","t":124,
   "frame_ts":"2026-11-18T14:02:35.511+09:00","level":"CRITICAL","reason":"INSTABILITY",
   "message":"…","value":0.031,"cell_ids":["c-0412"],"acked_at":null}
]
```
- `?unacked=true`면 두 번째 원소만. (실제 응답은 한 줄. 위는 읽기 좋게 줄을 나눴다.)

### 10.4 화면(web) 처리 제안 (나예린 님)
- 확인 버튼: `POST /api/alerts/{alert_id}/ack` → 200이면 그 알림을 확인됨으로 표시, 404면 목록에서 지운다(서버가 더 이상 보관하지 않음).
- 재접속: `hello.unacked_alerts`로 미확인 목록을 **교체**한다. 놓친 알림이 걱정되면 hello 직후 `GET .../alerts?unacked=true`를 한 번 불러 `alert_id`로 합친다.
- 다른 화면에서 확인한 것은 실시간으로 오지 않는다(`[토론]` 5).

## 11. 이후 PR이 붙일 곳 (S6에서 만들지 않음)
| PR | 붙는 곳 | 내용 |
|---|---|---|
| S7 | `api/` | `ZoneController`(`/api/zones`, `/meta`, `POST .../playback`), `HealthController`. `CorsConfig`의 `/api/**`·`GET`·`POST`를 그대로 쓴다 |
| S7 | 오류 본문 | seek 400과 함께 오류 형식(본문 없음 / Spring 기본 / `ProblemDetail`)을 정하고 S6 404에도 맞춘다(`[토론]` 2) |
| S7 | `/api/health` | 필요하면 구역별 미확인 수(`AlertStore.unacked(zoneId).size()`) |
| 합의 후 | WS `alert_ack` | 확인을 다른 화면에 방송(`[토론]` 5). `AlertController.ack`의 `firstAck` 뒤 `ZoneSessions.broadcast` 한 줄, api-spec 3절 메시지 추가 |
| 합의 후 | `AlertIdGenerator` | 재시작 구분이 필요하면 ID에 시작 시각(`[토론]` 6) |

## 12. TDD 단계
공통 (Git Bash, `server/`):
```bash
cd /c/Users/Woori/Desktop/project/Triple-Y/server && JAVA_HOME="/c/Program Files/Eclipse Adoptium/jdk-21.0.13.9-hotspot" ./gradlew test --tests '<패턴>' --no-daemon
```
> **에이전트는 `bootRun`을 실행하지 않는다** (포그라운드·백그라운드 모두). 확인은 `test`·`build`로 한다.

각 단계의 Red는 "테스트 먼저 작성 → 컴파일 실패 또는 단언 실패 확인"이다.

| 단계 | 할 일 (Red → Green) | `--tests` | 완료 조건 |
|---|---|---|---|
| 0 | 브랜치 확인: `git switch feat/server-alert-ack`, `git log --oneline -1`이 `755c880` | — | `git status --short`에 `?? CLAUDE.local.md`·`?? docs/plans/server_s6_alert_ack_plan.md`만. 시작 전 전체 `./gradlew test --no-daemon` 통과 |
| 1 | `CrowdsightPropertiesTest`(`defaults`, +3), `bindsDefaultAlertLog`, `TestProperties`(`ALERT_LOG`, `alertLog`, `full`) → `CrowdsightProperties.alertLog`, yml(3.1절) | `'com.tripley.crowdsight.config.*'` 다음 `'com.tripley.crowdsight.CrowdsightServerApplicationIntegrationTest'` | config 기존 + 3메서드 통과, 앱 통합 8메서드 통과 |
| 2 | `AlertStoreTest` +8 → `StoredAlert`, `AlertAck`, `AlertStore`(`ack`, `list`, 보관 규칙, `ArrayList`), `Alert` Javadoc | `'com.tripley.crowdsight.alert.AlertStoreTest'` | 14메서드 통과 (기존 6 포함) |
| 3 | `AlertLogWriterTest` → `AlertLogLine`, `AlertLogWriter` | `'com.tripley.crowdsight.alert.AlertLogWriterTest'` | 4메서드 통과 |
| 4 | `AlertControllerTest` → `api/AckResponse`, `api/AlertView`, `api/AlertController` | `'com.tripley.crowdsight.api.AlertControllerTest'` | 7메서드 통과 |
| 5 | `AlertControllerIntegrationTest` → `config/CorsConfig` | `'com.tripley.crowdsight.api.AlertControllerIntegrationTest'` | 7메서드(CORS 허용 2회) 통과. CORS 2개는 `CorsConfig` 전에 Red(403·헤더 없음) |
| 6 | 회귀: alert·ws 전체 | `'com.tripley.crowdsight.alert.*'` 다음 `'com.tripley.crowdsight.ws.*'` | S5 테스트 모두 통과(hello·방송 동작 보존) |
| 7 | 전체 실행 | 없음 (`./gradlew test --no-daemon`) | 모든 테스트 통과. `server/logs/`가 생기지 않았다 |
| 8 | README 알림 확인 절(아래), S5 절 한 줄, 9장 문서 정정 | — | 문구만 |
| 9 | 전체 검증 (아래 표) | — | 모두 기대대로 |

README 수정:
- `## 알림 (S5)`의 "서버를 재시작하면 사라진다. 확인(ack)은 S6." → "서버를 재시작하면 사라진다. 확인하면 목록에서 빠진다."
- `## 알림 (S5)` 아래에 추가:
````markdown
## 알림 확인 (S6)
- 확인: `POST /api/alerts/{alert_id}/ack` → `200 {"alert_id","acked_at"}`. 다시 보내도 처음 확인 시각을 돌려준다. 보관 중이 아닌 ID는 `404`.
- 목록: `GET /api/zones/{zone_id}/alerts?unacked=true` (미확인만), `unacked`를 빼면 보관 중인 전체(원소에 `acked_at`).
- 처음 확인할 때마다 `logs/alerts.jsonl`(`crowdsight.alert-log`, `server/` 기준, git 제외)에 JSON 한 줄을 덧붙인다. 시작 로그에 절대 경로가 찍힌다.
- 기록 파일을 쓰지 못해도 확인은 반영되고, ERROR 로그에 쓰려던 줄이 남는다.
- 구역당 보관 알림은 100개(`crowdsight.unacked-alert-limit`)까지다. 넘으면 확인한 것부터 버린다.
- REST(`/api/**`)도 WebSocket과 같은 허용 출처(`crowdsight.cors-origin-patterns`)를 쓴다.
- 확인 예 (Git Bash): `curl -X POST http://localhost:8080/api/alerts/a-20261118-0001/ack`
````

9단계 검증:

| # | 명령 (`server/`) | 기대 |
|---|---|---|
| 1 | `JAVA_HOME=… ./gradlew clean build --no-daemon` | `BUILD SUCCESSFUL` |
| 2 | `grep -h -o 'tests="[0-9]*" skipped="[0-9]*" failures="[0-9]*" errors="[0-9]*"' build/test-results/test/*.xml` | 모든 줄 `failures="0" errors="0"` |
| 3 | `ls logs 2>/dev/null` | 출력 없음 (테스트가 `server/logs/`에 쓰지 않음) |
| 4 | `grep -rn 'springframework' src/main/java/com/tripley/crowdsight/grade src/main/java/com/tripley/crowdsight/alert/StoredAlert.java src/main/java/com/tripley/crowdsight/alert/AlertAck.java src/main/java/com/tripley/crowdsight/alert/AlertLogLine.java` | 출력 없음 |
| 5 | `grep -rn 'import com.tripley.crowdsight.\(ws\|api\)' src/main/java/com/tripley/crowdsight/alert` | 출력 없음 (순환 없음) |
| 6 | `grep -rnE 'S6(이\|에서)\|\(S6: alert-log\)' src/main` (표 안 `\|`는 `|`) | 출력 없음 (S6 자리 주석 정리) |
| 7 | `grep -rn 'alerts.jsonl' src/main/java` | 출력 없음 (경로는 yml에만) |
| 8 | `grep -rnE 'Instant\.now\|currentTimeMillis\|LocalDate\.now\(\)' src/main` | 출력 없음 |
| 9 | `grep -rn 'lineSeparator' src/main` | 출력 없음 (LF 고정) |
| 10 | `grep -rnE '@(Data\|Getter\|Setter\|Builder\|Value\|AllArgsConstructor\|NoArgsConstructor)\b' src` | 출력 없음 |
| 11 | `grep -rn 'com.fasterxml.jackson.databind' src` | 출력 없음 |
| 12 | `grep -rnP '\t' src README.md` | 출력 없음 |
| 13 | 바뀐 `.java` 파일에 120자 초과 줄 없음 (문자 수 기준) | 출력 없음 |
| 14 | stage 뒤 `git -C .. ls-files --eol server \| grep -v 'i/lf'` | `gradle-wrapper.jar`, `gradlew.bat`만 |
| 15 | `git -C .. status --short` | `CLAUDE.local.md`가 stage되지 않음, `server/logs/`·`build/test-logs/` 없음 |

커밋 제안 (커밋·푸시·PR은 사용자가 요청할 때만):
1. `feat: 알림 확인 기록 경로 설정 추가` (`CrowdsightProperties`, yml, `TestProperties`, 설정 테스트)
2. `feat: 알림 확인 ack와 알림 로그 (S6)` (`alert/` 4개 추가·`AlertStore`·`Alert`, `api/` 3개, `CorsConfig`, 테스트)
3. `docs: S6 계획 추가, 구현 계획·api-spec 보충, README 알림 확인 설명`

## 13. PR 설명 (초안)
제목: `feat: 알림 확인 ack와 알림 로그 (S6)` / 기준 `feat/server-alert` ← `feat/server-alert-ack` (**쌓인 PR**, #50 위)

> [!WARNING]
> **쌓인 PR 병합 순서 (CLAUDE.md)**
> 1. #50(`feat/server-alert` → `main`)을 먼저 병합하고 `feat/server-alert` 브랜치를 바로 삭제한다. GitHub가 이 PR의 기준을 `main`으로 자동으로 바꾼다.
> 2. 이 PR을 병합하기 전에 화면 위쪽이 `into main`인지 확인한다. `into feat/server-alert`이면 Edit로 `main`으로 바꾼 뒤 병합한다.
> 3. 기준이 남은 채 병합하면 Merged로 보여도 `main`에 반영되지 않는다 (#18, #21·#23).

- 목적: 상황실 화면에서 알림 확인 버튼을 누르면 서버가 처음 확인 시각을 남기고 `logs/alerts.jsonl`에 기록한다(UC-06). 확인한 알림은 미확인 목록·재접속 `hello`에서 빠진다. 놓친 알림을 REST로 다시 받을 수 있다.
- 변경:
  - `POST /api/alerts/{alert_id}/ack`: 200 `{alert_id, acked_at}`, 다시 확인해도 처음 시각(멱등), 보관 중이 아니면 404
  - `GET /api/zones/{zone_id}/alerts?unacked=true|false`: `alert` 키 + `acked_at`, 오래된 것부터, 없는 구역 404
  - `AlertStore`: `ack`·`list`, 확인한 알림 보관(상한 넘으면 확인한 것부터 버림 → 미확인 동작은 S5 그대로)
  - `AlertLogWriter`: 처음 확인마다 JSON 한 줄(UTF-8, LF), 폴더·파일 자동 생성, 실패해도 200 + ERROR
  - `CorsConfig`: REST `/api/**` 허용 출처 = WS와 같은 `crowdsight.cors-origin-patterns`
  - 설정 `crowdsight.alert-log: logs/alerts.jsonl`
- 바뀌지 않은 것: WS 메시지 형식(`hello`·`zone_state`·`alert`·`playback`), `hello.schema_version` `"0.2"`, 재생·판정·알림 판정.
- 출력 예시: 계획 10장.
- 참고: api-spec 2절·4.5(보충), S5 계획 7.3·11장.

> [!IMPORTANT]
> **CS 이슈**
> | **주제** | **내용** |
> |---|---|
> | **멱등성(idempotency)** | 확인은 처음 시각만 남기고 다시 오면 같은 결과를 준다. 화면 재시도·두 화면 동시 확인·네트워크 중복에도 기록이 한 줄이다 |
> | **확인 후 행동(check-then-act)의 원자성** | "찾기 → 이미 확인? → 시각 기록"을 `synchronized` 하나로 묶어 `firstAck`가 알림마다 한 번만 참이다. 기록 줄 수가 이 값으로 정해진다 |
> | **잠금 범위와 I/O** | 파일 쓰기를 저장소 잠금 밖에 둔다. 디스크가 느려도 재생 스레드의 알림 발급이 막히지 않는다. 두 잠금을 겹쳐 쥐지 않아 교착이 없다 |
> | **추가 전용 로그(append-only, JSON Lines)** | 한 줄 = 한 사건, 덧붙이기만 한다. 줄 단위로 `jq`·스프레드시트에서 읽고, 일부가 깨져도 다른 줄은 살아 있다. LF·UTF-8로 OS와 무관하게 같다 |
> | **내구성 수준** | 닫을 때 OS 버퍼로 넘긴다(fsync 없음). 프로세스가 죽어도 남고, 전원이 꺼지면 마지막 줄이 빠질 수 있다. 시연 기록에 맞춘 선택이다 |
> | **실패 격리** | 기록 실패는 그 요청에서 ERROR로 끝난다. 재생 스레드는 기록 파일을 쓰지 않아 디스크 문제가 1초 재생을 멈추지 않는다 |
> | **유한 버퍼와 버리기 우선순위** | 구역당 100개 안에서 확인한 것을 먼저 버린다. 미확인 알림의 보존 규칙은 S5와 같고 메모리 상한도 같다 |
> | **CORS 사전 요청(preflight)** | 브라우저는 다른 출처(5173 → 8080) 요청 전에 `OPTIONS`로 허용을 묻는다. 서버가 `Access-Control-Allow-Origin`으로 답한다. 허용 패턴은 WS와 한 설정을 쓴다 |
> | **스냅샷 + 구독 경쟁의 복구** | hello(스냅샷)와 방송(구독) 사이에 놓친 알림을 `GET ?unacked=true`로 다시 받는다. `alert_id`로 합쳐 중복이 없다 |

| 선택 | 대안 | 고른 이유 |
|---|---|---|
| 목록 하나 + 확인한 것부터 버림 | 확인하면 지우고 ID→시각 맵 / 미확인·확인 목록 따로 | 미확인 동작이 S5 그대로, 메모리 상한 그대로, 발급 순서 공짜, 두 번째 확인·전체 목록 가능 |
| 처음 확인만 기록 | 확인 요청마다 기록 | api-spec 4.5·계획 S6 표. 기록 = 사건 1건 |
| 기록 실패 시 200 + ERROR | 500 반환 / 기록 성공 뒤에 확인 반영 | 화면과 서버 상태가 어긋나지 않는다. 기록 먼저면 저장소 잠금 안에서 디스크를 써야 한다 |
| 컨트롤러 `api/` | 계획 1.1의 `alert/` | `acked_at` 형식(`FrameTimestamps`, `ws`) 때문에 `alert`에 두면 순환 |
| `acked_at`을 컨트롤러가 만듦 | 저장소가 `Clock`으로 형식화 | 저장소가 `ws`를 모른다. 고정 `Clock`으로 정확히 시험된다 |
| ID 선형 탐색 | ID 색인 맵 | 100개라 비용이 없고, 버릴 때 색인을 같이 지울 필요가 없다 |
| 확인 WS 방송 없음 | `alert_ack` 메시지 | api-spec에 없다. 합의 후 한 줄로 붙는다(11장) |
| `MockMvcTester` | `MockMvc` + Hamcrest, `RestTestClient` | AssertJ 단언(CLAUDE.md). 의존성 추가 없음 |

리뷰 요청:
- 보관 규칙(확인한 것부터 버림)과 `unacked-alert-limit` 이름 유지(7.4절)
- `GET` 응답 원소에 `type: "alert"`와 `acked_at`을 넣은 것, `unacked` 기본 false (`[토론]` 1)
- 기록 실패 시 200(`[토론]` 4), 확인을 방송하지 않는 것(`[토론]` 5)
- 재시작 뒤 같은 번호 위험과 화면의 hello 목록 교체(7.1절, `[토론]` 6)

남은 일:
- S7(재생 제어 REST, `/api/zones`, `/meta`, `/health`, 오류 본문 형식)
- 화면: 확인 버튼 → POST, hello로 미확인 목록 교체, 필요 시 GET 보충(10.4절, 나예린 님)

## 14. 위험·가정·`[토론]`
| 위험 | 대응 |
|---|---|
| 서버 재시작 뒤 화면이 예전 ID를 확인하면 번호가 같은 새 알림이 확인된다 | 화면이 hello로 목록을 교체(10.4절, api-spec 보충). 서버 쪽 해결은 ID 형식 변경이라 `[토론]` 6 |
| 인증이 없어 같은 네트워크의 누구나 확인할 수 있다 | 시연은 같은 PC·내부망(가정). CORS는 브라우저만 막는다. 운영 전 인증은 MVP 밖 |
| 기록 파일을 다른 프로그램이 잠그면(Windows에서 엑셀로 열기 등) 쓰기가 실패한다 | 200 + ERROR에 줄 내용. README에 "실행 중에는 메모장으로 열기" 안내는 필요하면 추가 |
| 통합 테스트가 `server/logs/`에 쓰면 작업 트리가 더러워진다 | 통합은 `build/test-logs/`, 단위는 `@TempDir`. 9단계 검증 #3·#15 |
| `ArrayDeque` → `ArrayList`로 S5 동작이 바뀔 수 있다 | S5 `AlertStoreTest` 6개·ws 테스트를 그대로 통과시킨다(12장 6단계) |
| MockMvc 응답 문자열이 ISO-8859-1로 읽혀 한국어 단언이 깨진다 | `getContentAsString(StandardCharsets.UTF_8)` |
| 컨트롤러 테스트에서 `ZoneRegistry`가 fixture를 읽는다 | 기존 `ZoneRegistryTest`와 같은 구성(`TimelineLoader(MAPPER, props)`), 작업 폴더 `server/` 기준 상대 경로 |

가정:
- (가정) 확인은 판정에 영향이 없다. 반복 재생의 같은 사건은 새 ID로 따로 확인한다.
- (가정) 서버 하나가 기록 파일 하나를 쓴다(다중 프로세스 없음). 파일은 지우거나 돌리지 않는다.
- (가정) 상황실 화면은 1~2개라 확인 방송 없이도 된다.
- (가정) `unacked`를 빼면 보관 중인 전체를 준다.

`[토론]`:

| # | 안건 | 초안 | 누구와 |
|---|---|---|---|
| 1 | `GET .../alerts` 원소 형식(`alert` 키 + `acked_at`, `type` 포함)과 `unacked` 기본값 false | 1장 #6·#7 | 나예린 |
| 2 | REST 오류 본문(404 본문 없음, 400 Spring 기본) | S7에서 seek 400과 함께 정하고 맞춤 | 조영준, 나예린 |
| 3 | `alerts.jsonl`에 발급 줄도 남길지(지금은 확인만, 미확인으로 끝난 알림은 파일에 없음). 기획 상세의 `alert` 표는 `created_at`·`acked_at`을 둘 다 둔다 | api-spec 4.5대로 확인만. 필요하면 `"event":"issued"` 줄 추가(형식 변경) | 이유노(G2 기록), 조영준 |
| 4 | 기록 쓰기 실패 때 200 vs 500 | 200 + ERROR(1장 #12) | 조영준 |
| 5 | 확인을 다른 화면에 알릴지(WS `alert_ack`) | 알리지 않음. 화면이 여러 개면 추가(11장) | 나예린 |
| 6 | 재시작 뒤 알림 번호가 1부터라 예전 ID 확인이 새 알림을 확인할 수 있음 (S5 `[토론]` 5) | 형식 유지, 화면이 hello로 목록 교체. 막으려면 `a-yyyyMMdd-HHmmss-NNNN` | 조영준, 나예린 |
| 7 | 접속 경쟁 놓침(S5 `[토론]` 4)을 화면이 hello 직후 `GET ?unacked=true`로 메울지 | 선택 사항으로 안내(10.4절) | 나예린 |
| 8 | 보관 상한 100과 "확인한 것부터 버림", 설정 이름 `unacked-alert-limit` 유지 (S5 `[토론]` 6) | 7.4절대로 | 조영준 |

---

### Critical Files for Implementation
- C:\Users\Woori\Desktop\project\Triple-Y\server\src\main\java\com\tripley\crowdsight\alert\AlertStore.java
- C:\Users\Woori\Desktop\project\Triple-Y\server\src\main\java\com\tripley\crowdsight\config\CrowdsightProperties.java
- C:\Users\Woori\Desktop\project\Triple-Y\server\src\main\java\com\tripley\crowdsight\ws\FrameTimestamps.java
- C:\Users\Woori\Desktop\project\Triple-Y\server\src\main\java\com\tripley\crowdsight\replay\ZoneRegistry.java
- C:\Users\Woori\Desktop\project\Triple-Y\server\src\test\java\com\tripley\crowdsight\config\TestProperties.java
