# 서버(Spring Boot) 구현 전 조사

| 항목 | 내용 |
|---|---|
| 작성일 | 2026-11-11 |
| 작성 | Researcher 서브에이전트 (조영준 요청) |
| 범위 | `server/` 구현 전에 알아야 할 내부 코드(웹·타임라인 생산자·기획서)와 외부 API(Spring Framework 7.0.10, Spring Boot 4.1.2, Jackson 3.1.7, Tomcat 11.0.27) |
| 검증 대상 | `docs/plans/server_impl_plan.md` (이하 "계획") |
| 기준 | `docs/api-spec.md` v0.1(origin/main), `docs/timeline-spec.md` v0.2, `docs/decisions-2026-11-11.md`, `docs/proposal.md` v3.1, `docs/proposal-detail.md` |

- 표기는 `docs/proposal-guide.md`를 따른다. `(확인 필요)` 미검증, `(가정)` 설계값, `[토론]` 팀 합의 필요.
- 11-11 재점검: main #32~#40 병합분과 비교한 결과는 `docs/research/server_recheck_2026-11-11.md`에 있다. 이 문서에서 #35·#36·#37·#33으로 바뀐 행은 "해결(#35)"·"갱신"으로 표시했다.
- "jar 확인"은 `~/.gradle/caches`의 jar를 `javap`로 본 것이다. "실측"은 jshell·Python으로 직접 돌려 본 결과다. 실험 파일은 임시 폴더에만 만들었고 저장소에는 이 문서만 추가했다.

---

## 0. 요약 (핵심 발견)

1. **느린 화면 보호가 계획대로 동작하지 않는다.** `ConcurrentWebSocketSessionDecorator`는 다른 스레드가 잠금을 못 얻을 때만 한도를 검사한다. 재생 스레드 혼자 보내면 Tomcat 차단 전송 제한(기본 20초)까지 재생 스레드가 멈춘다.
2. 한도 초과 예외는 `IOException`이 아니라 `SessionLimitExceededException`(unchecked)이다. 데코레이터는 세션을 스스로 닫지 않는다. 방송 코드가 잡고 직접 닫아야 한다.
3. Jackson 3.1.7 기본값(실측): 모르는 키 무시, null→`int` 실패, **실수→정수 자동 변환 허용**(`t: 1.5`가 `1`이 된다), `NaN` 거부. 정수 검사는 `JsonNode` 단계에서 직접 해야 한다.
4. 전역 `SNAKE_CASE`는 `densityPred60s`를 `density_pred60s`로 바꾼다(실측). 계획의 `@JsonProperty` 지정은 맞다.
5. 테스트 엔진은 JUnit 5가 아니라 **JUnit Jupiter 6.0.3**이다. `webmvc-test` 스타터가 `spring-boot-starter-test`를 끌어온다.
6. 웹은 아직 `hello`·`zone_state`를 이해하지 못한다. 지금 연결하면 모든 메시지를 "알 수 없는 type"으로 버리고 화면이 비어 있다.
7. 가짜 E04_039 타임라인(실측): 셀 9개 중 3개가 2㎡ 미만이다. 결정 4로 빼면 **가장 붐비는 왼쪽 열이 구역 등급에서 빠진다**. 구역 최대 밀도가 5.76에서 4.68로 바뀌어 밀도로는 심각이 나오지 않는다.
8. ~~예측 모듈(`src.predict.run`)을 거친 파일은 `count`·`counterflow`가 사라진다(실측). 그러면 유입 경보가 켜지지 않는다.~~ **해결(#35)**: `schema.py` v0.2가 두 필드를 읽고 쓰고, `fill_predictions`가 `count`를 넘긴다.
9. E8 "판정→알림 p95"를 `frame_ts`(서버가 보낸 시각)로만 재면 히스테리시스 확인 지연(1~3초)이 빠져 거의 0초가 나온다. 측정 시작점을 정해야 한다 `[토론]`.
10. 이 PC에는 `JAVA_HOME`이 비어 있고 `java`가 PATH에 없다. `gradlew` 전에 `JAVA_HOME`을 지정해야 한다. 가짜 타임라인은 conda `py311` 환경에서만 만들어진다(`crowdsight` 환경은 PyYAML이 없다).

---

## 1. 내부 코드 분석

### 1.1 화면(web)이 지금 기대하는 메시지

조사 기준: 작업 트리의 `web/` (origin/main과 같음). 로컬 `main`은 origin/main보다 22커밋 뒤라 `docs/api-spec.md`가 없다. 브랜치를 만들기 전에 `git pull`이 필요하다.

| 파일 | 지금 동작 |
|---|---|
| `web/src/config/app.ts` | `WS_URL = VITE_WS_URL` (기본 빈 값 → 연결 안 함). 주석 예시는 `ws://localhost:8080/ws/zones`(구역 ID 없음). 재접속 `reconnectMinMs` 1000, `reconnectMaxMs` 15000, `maxFrames` 120 |
| `web/src/lib/useLiveFeed.ts` | `new WebSocket(url)` 하나. 끊기면 1초부터 2배씩, 최대 15초. **닫힘 코드를 보지 않는다** → 4404를 받아도 계속 재접속한다. 메시지 파싱 오류는 `console.warn` 후 무시 |
| `web/src/lib/liveFeed.ts` | `type`이 `timeline`·`frames`·`frame`·없음만 받는다. 그 밖의 type은 `Error`를 던진다(호출자가 잡아 무시). `timeline`이 오면 전체 교체, `frames`는 `t`로 합치고 정렬 |
| `web/src/lib/validate.ts` | `validateFrame(fr, meta, requireV02 = false)`: `t` 0 이상 정수, `cells` 개수·순서가 `meta.cells`와 같아야 함, `density` 숫자 필수, `vx`·`vy`·`speed_var`·`pressure`·`density_pred_60s` **키가 없으면 실패**(null은 허용), `t < history_s−1`이면 예측 null. `inflow_ratio`는 키 없음도 허용. `interval_s`는 검사하지 않는다. **갱신(#35)**: v0.2. 파일은 `schemaMinor ≥ 2`이면 `count`·`counterflow` 키 필수, 실시간 프레임은 `requireV02=false`로 검사(키 없어도 통과, 있으면 범위 검사). `count` ≥ 0, `counterflow` 0~1. 반환에 `count` 포함, 빠진 `counterflow`는 null로 채움 |
| `web/src/types/timeline.ts` | **갱신(#35)**: v0.2. `SCHEMA_VERSION` `'0.2'`, `SCHEMA_V02_MINOR` 2, `Frame.count`, `CellState.counterflow` |
| `web/src/config/density.ts` | `DENSITY_LEVELS` 3/4/5, 표기 "정상·주의·**경고**·심각". `levelOf`는 `density < max` → 3.0은 주의 (서버 규칙 `≥`와 같다) |
| `web/src/lib/alerts.ts` | `deriveAlerts`: 프레임마다 최대 밀도로 즉시 등급(히스테리시스 없음). `raise`(경고 이상으로 오름), `clear`(경고 미만으로 내림), `forecast`(마지막 프레임 예측이 경고 이상이고 현재보다 높음). 불안정·유입 알림 없음 |
| `web/src/lib/dashboard.ts`, `region.ts`, `views/*` | 모두 `levelOf(density)`로 화면에서 등급 계산. 서버 `grade`를 읽는 곳 없음 |
| `web/src/lib/timeline.ts` | `VITE_TIMELINE_URL`(기본 `/timeline.json`)을 fetch해 전체 검증. 실패하면 mock |
| `web/vite.config.ts` | 개발 프록시 없음 → 화면(5173)에서 서버(8080)로 가는 요청은 교차 출처다. PWA workbox가 `/api/` GET을 `NetworkFirst`로 캐시(빌드본에서만) |
| `web/scripts/mock-ws-server.mjs` | 포트 8787. 접속 시 `{type:"timeline", timeline:{schema_version:"0.1", meta, frames:[]}}`, 1초마다 `{type:"frame", frame}`. 150초 끝나면 `timeline`을 다시 보내 초기화. 셀 60개(6×10), `zone_id` `zone-mock-ws` |

### 1.2 타임라인 생산자와 서버가 받아야 할 규칙

| 생산자 | 출력 | 서버 관련 사실 |
|---|---|---|
| `src/counting/run_density.py` | G1 타임라인. `inflow_ratio` null, `count` 숫자, 흐름·예측 null, `counterflow` null | `schema_version`은 `schema.py`의 `SCHEMA_VERSION` → **이제 `"0.2"`(#35)**, `count`·`counterflow` 키를 모두 쓴다. `json.dumps` 기본값(`allow_nan=True`)이라 영상 읽기가 중간에 끊기면 `NaN`이 들어갈 수 있다 → Jackson이 거부(실측). 낮은 위험 |
| `src/counting/fake_timeline.py` | 모든 필드 합성. `inflow_ratio = 0.1 + 0.5·walking` (< 0.6), `count` 있음, 예측 null | 실측(E04_039, 180초): 셀 9개, 면적 1.0·1.06·1.2㎡ 3개, 최대 밀도 5.76(t=114에 5 이상), 최대 `inflow_ratio` 0.5373, `pressure`는 t=79에 0.02 초과, 최대 0.24 |
| `src/predict/run.py` + `schema.py` | `density_pred_60s` 채움 (t ≥ 29) | ~~`timeline_to_dict`가 v0.1 필드만 쓴다 → `count`·`counterflow` 키가 사라진다(실측).~~ **해결(#35)**: v0.2 필드를 읽고 쓰며 `fill_predictions`가 `count`를 넘긴다. v0.1 파일은 두 필드를 None으로 채우고 버전을 `"0.2"`로 올린다 |
| `src/flow/run_flow.py` (**병합됨, #36·#37**) | 함수 API. 기존 프레임에 `vx`·`vy`·`speed_var`·`pressure`·`inflow_ratio`를 채움. 머리 높이 평면으로 m/s | `allow_nan=False`로 저장. `inflow_ratio`를 **소수 2자리**로 반올림(규격은 4자리). `counterflow`는 쓰지 않음(기존 값 복사). `interval_s`가 1이 아니면 거부. 경계에 움직이는 머리가 `inflow_min_heads`보다 적으면 `inflow_ratio` null, 셀 머리가 `min_heads`보다 적으면 `vx`·`vy`·`speed_var`·`pressure` null(사람 없는 셀은 `pressure` 0) → 서버 영향은 계획 결정 기록 8, 6장 `pressure` 행 |

`schema.py validate_timeline`이 실제로 검사하는 것 (서버가 맞출 최소 규칙):

| 검사 | `schema.py` | `validate.ts` | 계획 |
|---|---|---|---|
| `schema_version` 앞자리 `"0"` | 예 | 예 | 예 |
| `meta` 9개 키 존재 | 예 | 예 | 예 |
| `duration_s == len(frames)` | 예 | 예 (partial 아닐 때) | 예 |
| `frames[i].t == i` | 예 (`0.0`도 통과) | 정수 검사 | 예. **정수 검사 추가 필요** (1.5절) |
| `interval_s == 1` | 아니오 | 아니오 | 예 (서버만의 추가 규칙) |
| `history_s` 1 이상 정수 | 예 | 예 | 암묵적 |
| `cell_id` 형식·row/col 일치·면적 > 0·다각형 0~1 4점·중복 없음 | 예 | 예 | 예 |
| `cells` 순서·전체 일치 | 예 | 예 | 예 |
| `density` 숫자 필수 (음수 검사 없음) | 예 | 예 | 예. 음수 거부는 선택 |
| 측정·예측 5개 키 필수, 값 숫자 또는 null | 예 | 예 | 예 |
| `counterflow`, `count` | **갱신(#35)**: v0.2 이상이면 키 필수(값 null 가능), v0.1은 생략 허용. `count` ≥ 0, `counterflow` 0~1 | 같음 (실시간 프레임은 `requireV02=false`) | 같게 (계획 결정 기록 7) |
| `inflow_ratio` 0~1 또는 null | 예 | 예 | 예 |
| `t < history_s − 1`이면 예측 null | 예 | 예 | 예 |

### 1.3 bootRun용 가짜 타임라인 만들기 (실측 확인)

```powershell
# 저장소 루트에서. cv2와 PyYAML이 둘 다 있는 환경은 py311뿐이다 (crowdsight 환경은 PyYAML 없음)
conda activate py311
python -m src.counting.fake_timeline --homography infra/homography/E04_039.json `
    --out data/processed/timeline/fake_E04_039.json --duration 180
# 예측까지 보려면
python -m src.predict.run --input data/processed/timeline/fake_E04_039.json `
    --output data/processed/timeline/fake_E04_039.pred.json
```

- 이름을 `fake_`로 시작하게 한다. 이유노의 실제 `E04_039.json`과 섞이지 않게 하기 위해서다 (가정).
- 서버 실행: 4.4절 명령에서 `--crowdsight.timeline-files=fake_E04_039.json`을 넘긴다.
- 유입 경보는 가짜 데이터로 켜지지 않는다(최대 0.5373). 경보 시험은 손으로 만든 fixture로 한다 (계획과 같음).

### 1.4 기획서의 등급·알림 규칙과 근거

| 규칙 | 값 | 출처 | 상태 |
|---|---|---|---|
| 등급 경계 | 3·4·5명/㎡ | `proposal.md` 3.2, 근거 [37] 서울경찰청 골목 등급, [35][71] 서울시·광진구 훈련 | 확정 |
| 올림 | 2초(2회) 연속 충족 | `proposal.md` 3.2 | (가정) |
| 내림 | 10초 연속 해제 시 한 단계 | `proposal.md` 3.2 | (가정) |
| 불안정 | P = ρ × Var(v) > 0.02/s², 3초 지속 | `proposal.md` 3.3, [1] Helbing 2007 | (가정). `crowd_turbulence_research.md`: 원 저자도 "보정 필요"라고 씀, 계획의 공간 분산은 원 정의(시간 분산)와 다름 |
| 불안정 유지 | "사라져도 10초 유지" | `proposal-detail.md` 3.3 | 계획에 별도 규칙 없음. 셀 관측 등급이 심각 → 히스테리시스 내림 10초로 사실상 같다. 다만 내려가면 경계로 한 단계만 내려간다 |
| 유입 경보 | 5초 평균 > 0.6, `count` < 3명이면 끔. 창(5초)이 다 찬 뒤 non-null 3개 이상이면 평균 | `api-spec.md` 4.4, 결정 6, 계획 결정 기록 8 | (가정) |
| 구역 등급 | 보행 면적 2㎡ 이상 셀 등급의 최댓값 | 결정 4 | 확정. 단 1.6절 위험 참고 |
| 밀도 평활 | 5장 평균 (`timeline-spec.md` 4절) | `proposal-detail.md` 3.4 (**갱신(#33)**: 5장 평균으로 고쳐짐) | 서버는 추가 평활 안 함 |
| 지연 예산 | 2회 확인 ≤ 1.0 + 판정 ≤ 0.2 + 표시 ≤ 0.5 = ≤ 1.7초, 불안정 ≤ 3.7초 | `proposal.md` 5.4 | (가정) |
| E8 | 판정→알림 p95 ≤ 5초, 30분 반복 무중단. 처리 속도는 기록만 | 결정 9, `proposal.md` v3.1 1.2·7.2 | 확정 (**해결(#33)**: 기획서 v3.1에 반영) |
| 알림 기록 | 로그 파일, DB 없음 | `proposal.md` 5.1 | 확정 |
| 미확인 알림 재전송 | 재접속 때 | `proposal-detail.md` 4.6 UC-07, `api-spec.md` 3.1 | `hello.unacked_alerts`로 반영 |

### 1.5 E8 측정 정의의 빈틈

- `api-spec.md` 7절: 화면 수신 시각 − `frame_ts`. `frame_ts`는 "서버가 그 초를 보낸 시각"이다.
- 이렇게 재면 같은 PC에서 수 ms가 나온다. 히스테리시스 확인 시간(밀도 +1초, 불안정 +2~3초)은 들어가지 않는다.
- 기획서 1.2는 "타임라인 재생 시각과 화면 수신 시각 차이", 5.4는 확인 지연까지 예산에 넣었다.
- 제안 `[토론]` (이유노): `alert`에 `onset_t`(조건이 처음 충족된 `t`)와 `onset_ts`(그 초를 재생한 시각)를 넣는다. 화면 수신 시각 − `onset_ts`를 E8 값으로 쓴다.
- 표본 수: 180초 영상 30분 반복이면 10회 × 알림 2~3개 = 20~30개다. 이 크기에서 p95는 사실상 최댓값 근처다. `zone_state` 지연(약 1,800개)도 함께 기록한다 (가정).
- p95 계산은 최근접 순위(nearest-rank) 방식으로 고정한다 (가정).

---

## 2. 외부 API 분석

모든 버전은 `./gradlew dependencies --configuration testRuntimeClasspath`(오프라인)로 확인했다.

| 구성 | 버전 |
|---|---|
| Spring Boot | 4.1.2 |
| Spring Framework | 7.0.10 |
| Tomcat embed (+websocket) | 11.0.27 |
| Jackson databind/core | 3.1.7 (`tools.jackson.core`) |
| jackson-annotations | 2.21 (`com.fasterxml.jackson.annotation`) |
| JUnit Jupiter / Platform | **6.0.3** |
| AssertJ / Mockito / Awaitility | 3.27.7 / 5.23.0 / 4.3.0 |
| json-path / JSONassert | 2.10.0 / 1.5.3 |
| 추가로 들어온 모듈 | `spring-boot-resttestclient` 4.1.2 (`webmvc-test` 스타터 경유), `spring-messaging` 7.0.10 (websocket 스타터 경유) |

### 2.1 Spring Framework 7 순수 WebSocket

| 주제 | 확인 결과 | 근거 |
|---|---|---|
| 등록 | `@EnableWebSocket` + `WebSocketConfigurer.registerWebSocketHandlers` + `registry.addHandler(h, path)` | [S1] |
| 경로 변수 | 핸들러로 전달되지 않는다. `session.getUri()`를 `UriTemplate("/ws/zones/{zoneId}").match(path)`로 푼다. 실측: `/ws/zones/zone-e04-039` → `{zoneId=zone-e04-039}`, `/ws/zones/` → `matches` true(빈 값) → 없는 구역으로 처리 | jar 확인, 실측 |
| 허용 출처 | 기본은 **같은 출처만**. `setAllowedOrigins("http://localhost:5173")` 또는 `setAllowedOriginPatterns("http://localhost:*", "http://127.0.0.1:*")` 둘 다 있음 | [S1], jar 확인 |
| `HandshakeInterceptor` | 핸드셰이크 전후에 끼어 거절하거나 속성을 넣는다. 거절하면 브라우저는 HTTP 응답만 받고 `onclose` 코드 1006을 본다 → 화면이 이유를 모른다. 그래서 4404 닫기가 낫다 | [S1] |
| 닫기 코드 | `CloseStatus`는 1000~4999만 허용(실측: 5000 → `Invalid status code`). `new CloseStatus(4404, "unknown zone")` 가능. 4000~4999는 응용 전용 [S6] | 실측, [S6] |
| `ConcurrentWebSocketSessionDecorator` | 한 번에 한 스레드만 보낸다. 다른 스레드는 버퍼에 넣고, **잠금을 못 얻은 스레드만** 한도를 검사한다 | [S2] 소스 |
| 한도 초과 | `SessionLimitExceededException`(RuntimeException), 상태 `SESSION_NOT_RELIABLE`(4500, 실측). **세션을 닫지 않는다** → 호출자가 `close`. 그 뒤 `close`는 상태를 4500으로 바꾼다 | [S2] 소스, jar |
| `OverflowStrategy` | `TERMINATE`: 버퍼 한도 넘으면 위 예외. `DROP`: 오래된 메시지부터 버림. `sendTimeLimit` 초과는 전략과 상관없이 예외 | [S2] |
| 단일 송신 스레드 | 재생 스레드 혼자 보내면 늘 잠금을 얻어 `delegate.sendMessage`에서 **막힌다**. 막히는 최대 시간은 Tomcat `org.apache.tomcat.websocket.BLOCKING_SEND_TIMEOUT`(기본 20000 ms). ping 스레드가 동시에 보낼 때만 한도 예외가 난다 | [S2], [S3] |
| ping | `session.sendMessage(new PingMessage())`. 브라우저가 pong을 자동으로 보낸다 (RFC 6455 5.5.2) | [S6] |
| 유휴 시간 | Tomcat 세션 `maxIdleTimeout` 기본값은 문서에 없음 (확인 필요). `ServletServerContainerFactoryBean.setMaxSessionIdleTimeout`·`setAsyncSendTimeout` 있음(jar 확인) | [S3], jar |
| 서버 쪽 받는 버퍼 | 텍스트 기본 8192바이트. 서버가 화면 메시지를 무시하므로 영향 없음 | [S3] |
| SockJS 스케줄러 | 7.0에서는 `DefaultSockJsSchedulerContainer`로 감싸져 `TaskScheduler` 빈으로 드러나지 않는다(jar 확인) → 계획의 `ThreadPoolTaskScheduler` 빈 주입이 모호해지지 않는다. 그래도 `@Qualifier`를 권한다 | jar |
| 클라이언트 | `StandardWebSocketClient.execute(handler, uriTemplate, vars...)` → `CompletableFuture<WebSocketSession>` | jar |

### 2.2 Spring Boot 4 변경점

| 주제 | 확인 결과 | 근거 |
|---|---|---|
| 스타터 이름 | `spring-boot-starter-web` → `spring-boot-starter-webmvc`. 기술별 테스트 스타터(`-webmvc-test`, `-websocket-test`)가 `spring-boot-starter-test`를 끌어온다 | [S4] |
| MockMvc | `@SpringBootTest`만으로는 MockMvc가 없다. `@AutoConfigureMockMvc` 필요. 패키지 `org.springframework.boot.webmvc.test.autoconfigure` | [S4], jar |
| TestRestTemplate | `@AutoConfigureTestRestTemplate` 필요, 패키지 `org.springframework.boot.resttestclient`. `RestTestClient` 권장 | [S4], jar |
| `@MockBean` | 삭제됨. `@MockitoBean` 사용 | [S4] |
| `@LocalServerPort` | `org.springframework.boot.test.web.server.LocalServerPort` | jar |
| Jackson 3 | `JsonMapper` 빈 자동 생성. `ObjectMapper` 빈을 정의해도 대체되지 않는다. 사용자 설정은 `JsonMapperBuilderCustomizer` | [S4], [S5] |
| `spring.jackson.*` | `property-naming-strategy`, `default-property-inclusion`, `deserialization.*`, `serialization.*`, `mapper.*`, `json.read.*`, `json.write.*`, `use-jackson2-defaults` 있음 (`JacksonProperties` jar 확인). 옛 `spring.jackson.read.*`·`parser.*`는 `json.read.*`로 옮겨짐 | [S4], [S5], jar |
| JSpecify | Boot 4는 JSpecify null 주석을 붙였다. Java만 쓰면 컴파일 영향 없음 | [S4] |
| `@ConfigurationProperties` + record | 마이그레이션 가이드에 변경 언급 없음. 생성자 바인딩·compact constructor 검사는 Boot 3과 같다고 본다 (확인 필요: 첫 테스트로 확인) | [S4] |

### 2.3 Jackson 3.1.7 동작 (실측, jshell)

| 항목 | 기본값·결과 | 서버 영향 |
|---|---|---|
| `FAIL_ON_UNKNOWN_PROPERTIES` | false | `@JsonIgnoreProperties(ignoreUnknown = true)`는 없어도 된다(있어도 무해) |
| `FAIL_ON_NULL_FOR_PRIMITIVES` | true | `int row`에 null·키 없음 → `MismatchedInputException` |
| `ACCEPT_FLOAT_AS_INT` | **true** | `"row": 1.5` → `1`로 조용히 잘림. `"t": 1.0` → `isInt()` false, `canConvertToExactIntegral()` true. 검증기는 `isIntegralNumber()` 또는 `canConvertToExactIntegral()`로 직접 검사 |
| `FAIL_ON_TRAILING_TOKENS` | true | 파일 끝 쓰레기 거부 |
| `NaN` | 거부 (`ALLOW_NON_NUMERIC_NUMBERS` 꺼짐) | `run_density.py` NaN 파일은 읽기 실패. 파일명 붙여 감싼다 |
| `SORT_PROPERTIES_ALPHABETICALLY` | true, 단 `SORT_CREATOR_PROPERTIES_FIRST` true | record는 선언 순서대로 출력(실측) |
| `SNAKE_CASE` | `walkableAreaM2`→`walkable_area_m2`, `durationS`→`duration_s`, `frameTs`→`frame_ts`, `cellIds`→`cell_ids`, **`densityPred60s`→`density_pred60s`**, `gradePred60s`→`grade_pred60s` | 60s 두 필드만 `@JsonProperty` (계획과 같음) |
| record에 `@JsonProperty` | 직렬화·역직렬화 모두 반영 | 계획과 같음 |
| enum | 이름 그대로 (`"ALERT"`) | 계획과 같음 |
| `Double` 키 없음 | null | 키 없음 검사는 `JsonNode` 단계에서 (계획과 같음) |
| `JsonNode` | `path("b").isMissingNode()` true, `get("b")` null, `get("a").isNull()` true | 키 없음과 null 구분 가능 |
| `JacksonException` | unchecked | 계획과 같음 |
| `readTree(Path)` | 동작 | 계획과 같음 |

### 2.4 테스트 (Boot 4 + 순수 WebSocket)

- `@SpringBootTest(webEnvironment = RANDOM_PORT, properties = {...})` + `@LocalServerPort int port`.
- 클라이언트: `new StandardWebSocketClient().execute(handler, "ws://localhost:{port}/ws/zones/{zone}", port, zone).get(2, SECONDS)`. 받은 메시지는 `LinkedBlockingQueue`에 넣고 `poll(timeout)`이나 Awaitility로 기다린다.
- 교차 출처 시험: `execute(handler, WebSocketHttpHeaders, URI)`로 `Origin` 헤더를 넣는다. 허용 목록 밖이면 핸드셰이크 403 (확인 필요: 첫 통합 테스트로 확인).
- JUnit 6.0.3: `@Test`, `@DisplayName`, `@TempDir` 패키지는 그대로 `org.junit.jupiter.api.*`다.

### 2.5 알림·등급 판정 관행 (간단)

| 관행 | 내용 | 이 프로젝트 대응 |
|---|---|---|
| 대기 시간 (`for`) | 조건이 일정 시간 계속돼야 발화. 그 전은 pending [S7] | 올림 2초, 불안정 3초 |
| 유지 시간 (`keep_firing_for`) | 조건이 사라져도 일정 시간 발화 유지. 깜빡임·데이터 누락으로 인한 거짓 해제 방지 [S7] | 내림 10초, 유입 끄기 10초 |
| 중복 억제 | 같은 사건은 해제 전까지 한 번 | `api-spec.md` 3.3 "같은 reason은 해제 전 재전송 안 함" |
| 단계 상승 | 더 높은 단계로 오르면 새 알림 | 계획 GRADE_UP "이번 사건 최고 단계보다 높을 때" |

### 2.6 Windows 개발 환경

| 항목 | 내용 |
|---|---|
| `JAVA_HOME` | 현재 비어 있고 `java`도 PATH에 없다(실측). 지정하면 `gradlew`가 동작한다(실측: dependencies 성공) |
| Git Bash | `export JAVA_HOME="/c/Program Files/Eclipse Adoptium/jdk-21.0.13.9-hotspot"; cd server; ./gradlew bootRun` |
| PowerShell | `$env:JAVA_HOME = 'C:\Program Files\Eclipse Adoptium\jdk-21.0.13.9-hotspot'; cd server; .\gradlew.bat bootRun --args='--crowdsight.timeline-files=fake_E04_039.json'` |
| 작업 폴더 | `bootRun`·`test`의 작업 폴더는 `server/`다 (Gradle 기본, 확인 필요) → `../data/processed/timeline`, `logs/`는 `server/logs/` |
| 포트 충돌 | `netstat -ano | findstr :8080`로 PID 확인. 다른 포트는 `--server.port=8081` 또는 환경변수 `SERVER_PORT`. 조사 시점 8080·5173·8787 모두 비어 있음 |
| CORS | 화면은 5173, 서버는 8080 → REST는 `addCorsMappings("/api/**")`, WS는 `setAllowedOrigins`. 대안: Vite `server.proxy`에 `/api`, `/ws`(`ws: true`)를 두면 같은 출처라 CORS가 필요 없다 `[토론]` (나예린) |
| 줄바꿈 | `server/.gitattributes`가 `gradlew`는 LF, `*.bat`은 CRLF로 고정. Initializr 파일은 탭 들여쓰기 |

---

## 3. `server_impl_plan.md` 검증표

| # | 계획의 주장 | 확인 결과 | 근거 | 조치 |
|---|---|---|---|---|
| 1 | 버전: Framework 7.0.10, Tomcat 11.0.27, Jackson 3.1.7, annotations 2.21 | 맞음 | dependencies 출력 | 없음 |
| 2 | `spring-boot-starter-test`에 **JUnit 5** | **틀림**. JUnit Jupiter 6.0.3. 스타터도 `webmvc-test`·`websocket-test` 경유 | dependencies | 0절·3장 표기 수정 |
| 3 | Boot 4가 `JsonMapper` 빈 자동 생성, `JacksonException` unchecked, `readTree(Path)`, `treeToValue` | 맞음 | [S5], 실측 | 없음 |
| 4 | MockMvc 패키지 `org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc` | 맞음. `@SpringBootTest`만으로는 안 생김 | jar, [S4] | S6 테스트에 `@AutoConfigureMockMvc` 명시 |
| 5 | `docs/api-spec.md`는 main에 있다 | origin/main에는 있음(04c2731). **로컬 `main`은 22커밋 뒤라 없음** | git | D1 전 `git switch main; git pull` |
| 6 | 가짜 `inflow_ratio` 최대 0.6이라 경보 안 켜짐 | 맞음. 실측 최대 0.5373 | 실측 | 없음 |
| 7 | 로컬에 `data/processed/timeline/` 없음 | 맞음 | `ls` | 1.3절 명령 추가 |
| 8 | `@JsonIgnoreProperties(ignoreUnknown = true)` | 동작하지만 Jackson 3 기본이 이미 무시 | 실측 | 그대로 두거나 지움 (선택) |
| 9 | 전역 `SNAKE_CASE` + 60s 필드만 `@JsonProperty` | 맞음. `spring.jackson.property-naming-strategy` 키 유효 | jar, 실측 | 없음 |
| 10 | 검증 규칙 `frames[i].t == i`, 셀 `row`·`col` 정수 | 의도는 맞음. Jackson이 실수를 정수로 잘라 주므로 **record 변환만으로는 못 잡는다** | 실측 | `TimelineValidator`에서 `isIntegralNumber()` 검사, 테스트 `rejectsFractionalT` 추가 |
| 11 | 검증 규칙이 `schema.py` "기준 + 추가" | `interval_s == 1`은 `schema.py`·`validate.ts`에 없는 서버만의 규칙 | 코드 | 계획에 "서버 추가 규칙"으로 표시 |
| 12 | `ZoneSessions.broadcast` "실패 세션은 닫고 뺀다", 테스트는 IOException 1개 | 한도 초과는 `SessionLimitExceededException`(RuntimeException)이고 데코레이터가 닫지 않음 | [S2] | `IOException | RuntimeException` 모두 잡아 `close(SESSION_NOT_RELIABLE)`. 테스트 케이스 추가 |
| 13 | 데코레이터 `sendTimeLimit` 2000 + TERMINATE로 느린 화면 처리 | **재생 스레드 혼자 보내면 한도 검사가 안 일어난다.** 막힘은 Tomcat 20초까지 | [S2], [S3] | 택1 `[결정 필요]`: (가) 세션 생성 때 네이티브 세션 사용자 속성 `org.apache.tomcat.websocket.BLOCKING_SEND_TIMEOUT`=2000L 지정, (나) 세션마다 단일 스레드 실행기로 비동기 전송. 같은 PC 시연이면 (가)로 충분 (가정) |
| 14 | `setAllowedOrigins(corsOrigins)` | 동작. 단 `127.0.0.1:5173`으로 열면 거절 | [S1] | `setAllowedOriginPatterns` 고려 `[토론]` |
| 15 | 없는 구역은 `close(4404)` | 가능 (1000~4999) | 실측, [S6] | 웹이 4404에서 재접속을 멈추도록 요청 (5절) |
| 16 | `ThreadPoolTaskScheduler replayTaskScheduler` 주입 | 7.0의 SockJS 스케줄러는 빈으로 안 드러나 충돌 없음 | jar | `@Qualifier` 권장 (선택) |
| 17 | 판정 대상 `walkable_area_m2 ≥ 2.0` (결정 4) | 결정과 일치. 단 가짜 E04_039에서 가장 붐비는 왼쪽 열(1.0~1.2㎡)이 빠진다 | 실측 | 결정 유지, 이유노에게 실제 E04_039 셀 면적 확인 `[토론]` |
| 18 | `ZoneGraderTest.smallCellExcluded` 등 히스테리시스 표 | 표의 기대값을 손으로 따라가 봤다. `upAfterTwoSeconds`, `downOneStepPer10s`, `downInterrupted`, `criticalStepsDownOnly1`, `gradeUpRules` 모두 서술한 규칙과 일치 | 계산 | 없음 |
| 19 | 불안정 "사라져도 10초 유지"(상세 3.3) | 계획에 명시 없음. 셀 등급 내림 10초로 비슷하게 됨 | `proposal-detail.md` 3.3 | 계획 6장 또는 S4에 "히스테리시스로 대체" 한 줄 |
| 20 | `frame_ts`로 E8 p95 측정 | 확인 지연이 빠진다 | 1.5절 | `onset_t`·`onset_ts` 추가 `[토론]` |
| 21 | 화면 `validateFrame`은 키 없으면 실패 → null 출력 | 맞음. 모르는 type에 throw. ~~`count`를 버림~~ **해결(#35)**: `count` 유지, 빠진 `counterflow`는 null로 채움 | 코드 | 5절 |
| 22 | 재접속 지금 1 s ×2 최대 15 s | 맞음 | `config/app.ts` | 없음 |
| 23 | `timeline-dir: ../data/processed/timeline` (작업 폴더 `server/`) | Gradle 기본 작업 폴더는 프로젝트 폴더 (확인 필요: 시작 로그의 절대 경로로 확인) | — | 계획대로 절대 경로 INFO 로그 |
| 24 | `timeline-files: [E04_039.json]` 기본값 | 실제 파일이 아직 없음. 가짜를 같은 이름으로 만들면 섞일 위험 | — | 가짜는 `fake_E04_039.json`, 실행 인자로 지정 |
| 25 | 30분 반복에서 커지는 곳은 `AlertStore`뿐 | 화면 쪽 `maxFrames` 120도 상한이 있다. 서버 쪽은 계획대로 | 코드 | 없음 |
| 26 | `@ConfigurationProperties` record + compact constructor, validation 스타터 없음 | Boot 4 가이드에 변경 없음 | [S4] | `CrowdsightPropertiesTest`로 확인 (계획에 있음) |
| 27 | bootRun 준비 | `JAVA_HOME` 미설정, Python 환경 지정 필요 | 실측 | S0 PR 설명·README에 2.6절 명령 |

---

## 4. 웹(화면)과의 불일치

담당: 나예린. 서버는 명세대로 만들고, 아래는 화면 쪽 변경 요청이다 `[토론]`.

| # | 지금 웹 | API 명세·서버 | 영향 | 제안 |
|---|---|---|---|---|
| 1 | `type` `timeline`·`frames`·`frame`만 앎 | `hello`·`zone_state`·`alert`·`playback` | 연결해도 화면이 빈다 | `parseLiveMessage`에 4종 추가 |
| 2 | 모르는 type은 throw (경고 로그) | 무시 | 동작은 같으나 콘솔 잡음 | null 반환 |
| 3 | 프레임 = `{t, inflow_ratio, cells}` | `zone_state.zone.{grade, max_density, inflow_ratio, inflow_alert, count}` + `cells[].grade`·`grade_pred_60s` | 형태가 다름 | 어댑터 |
| 4 | ~~`validateFrame`이 `count`를 버림, 타입이 v0.1~~ | `count`·`counterflow` 있음 | — | **해결(#35)**: v0.2 반영 |
| 5 | `VITE_WS_URL` 그대로 연결, 예시에 구역 ID 없음 | `/ws/zones/{zone_id}` | 구역 없음 → 4404 | `.env.local`에 `ws://localhost:8080/ws/zones/zone-e04-039` |
| 6 | 닫힘 코드 무시, 무한 재접속 | 4404 = 없는 구역 | 1~15초마다 헛접속 | 4404면 멈추고 오류 표시 |
| 7 | 재접속 1→2→4→8→15초 | 1, 2, 5, 이후 5초 | 끊김 뒤 복구가 최대 15초 | 최대 5초 |
| 8 | 등급을 `levelOf`로 즉시 판정, "경고" | 서버 `grade`, "경계" | 히스테리시스 없는 등급이 보임 | 서버 `grade` 사용, 표기 통일 |
| 9 | `deriveAlerts`가 raise·clear·forecast를 만듦 | 서버 `alert` + ack REST | 알림 두 벌 | 서버 알림으로 교체. forecast 유지 여부 `[토론]` |
| 10 | 반복 재생은 `timeline` 재수신으로 초기화 | `playback{state:"playing", t:0}` 뒤 `zone_state` | 프레임이 섞임 | `playback` t=0이면 프레임 비움 |
| 11 | `frame_ts` 지연 기록 없음 | E8용 기록 | E8 측정 불가 | 수신 시각 기록 + CSV `[토론]` |
| 12 | `thresholds`·`unacked_alerts`·`playback` 없음 | `hello`에 있음 | 범례·미확인 알림 복구 불가 | 반영 |
| 13 | mock 8787이 옛 형식 | | 서버 없을 때 개발용 | mock 갱신 담당 `[토론]` |
| 14 | Vite 프록시 없음 | 서버 8080 | CORS 필요 | 서버 CORS 또는 Vite 프록시 `[토론]` |
| 15 | 셀 60개 mock 기준 화면 | 가짜 E04_039는 셀 9개 | 레이아웃 확인 필요 | 실제 파일로 확인 |

---

## 5. 위험·미결

### 위험

| 위험 | 정도 | 대응 |
|---|---|---|
| 느린 세션이 재생 스레드를 최대 20초 막음 (3절 #13) | 중 | `BLOCKING_SEND_TIMEOUT` 지정 또는 비동기 전송 |
| `SessionLimitExceededException`을 안 잡으면 재생 tick이 예외로 끝남 | 중 | 방송에서 모든 예외를 잡고 세션 닫기 |
| Jackson이 실수 `t`를 정수로 자름 | 낮음 | `JsonNode` 정수 검사 |
| 결정 4가 붐비는 작은 셀을 뺌 (가짜 데이터 기준) | 중 | 실제 E04_039·E05_035 셀 면적 확인 `[토론]` |
| ~~예측 모듈을 거치면 `count`가 사라져 유입 경보가 영영 꺼짐~~ | — | **해결(#35)**: `schema.py` v0.2. 서버는 `count` null을 "경보 안 켬"으로 처리 (계획대로) |
| 가짜 데이터는 불안정(t≈80)이 밀도 경계(t≈113)보다 훨씬 먼저 → 시연 순서가 정상→심각 | 낮음 | 가짜 데이터 한정. 실제 E5 기준값으로 조정 |
| E8 측정에 확인 지연이 빠짐 | 중 | 1.5절 `[토론]` |
| 로컬 `main`이 22커밋 뒤 | 낮음 | 브랜치 전 pull |
| `JAVA_HOME`·Python 환경 미설정 | 낮음 | 2.6절, 1.3절 명령 |
| `crowdsight` conda 환경에 PyYAML 없음 (requirements.txt에는 있음) | 낮음 | 팀에 알림, 설치는 승인 후 |

### 미결 (조영준이 정할 것)

1. 느린 화면 처리: `BLOCKING_SEND_TIMEOUT` 지정 vs 세션별 비동기 전송 vs 그대로(같은 PC 시연).
2. 허용 출처: `setAllowedOrigins` 고정 vs `setAllowedOriginPatterns`(localhost·127.0.0.1 모든 포트).
3. `@JsonIgnoreProperties` 유지 여부 (기능상 불필요).

### `[토론]`

| # | 안건 | 누구와 |
|---|---|---|
| 1 | E8 시작점: `onset_ts`를 `alert`에 넣을지 | 이유노 |
| 2 | 결정 4(2㎡)가 실제 영상에서 밀집 셀을 빼는지 확인 | 이유노 |
| 3 | 4404 수신 시 재접속 중단, 재접속 최대 5초 | 나예린 |
| 4 | Vite 프록시 vs 서버 CORS | 나예린 |
| 5 | 4절 1~15 화면 변경 범위와 11-13 연결 범위 | 나예린 |
| 6 | 흐름 `inflow_ratio` 소수 2자리 → 규격 4자리 | 조영준(흐름) |

---

## 6. 출처

| 번호 | 출처 | 확인한 버전 |
|---|---|---|
| [S1] | Spring Framework Reference, WebSocket API (server). <https://docs.spring.io/spring-framework/reference/web/websocket/server.html> | 7.0.10 |
| [S2] | `ConcurrentWebSocketSessionDecorator` Javadoc <https://docs.spring.io/spring-framework/docs/7.0.x/javadoc-api/org/springframework/web/socket/handler/ConcurrentWebSocketSessionDecorator.html> 및 소스 <https://github.com/spring-projects/spring-framework/blob/v7.0.10/spring-websocket/src/main/java/org/springframework/web/socket/handler/ConcurrentWebSocketSessionDecorator.java> | 7.0.10 |
| [S3] | Apache Tomcat 11 WebSocket How-To. <https://tomcat.apache.org/tomcat-11.0-doc/web-socket-howto.html> | 11.0.27 |
| [S4] | Spring Boot 4.0 Migration Guide. <https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Migration-Guide> | 2026-11-11 열람 |
| [S5] | Spring Boot Reference, JSON / How-to: Customize the Jackson JsonMapper. <https://docs.spring.io/spring-boot/reference/features/json.html>, <https://docs.spring.io/spring-boot/how-to/spring-mvc.html> | 4.1.2 |
| [S6] | RFC 6455 The WebSocket Protocol, 5.5.2 Ping·5.5.3 Pong, 7.4.2 예약 상태 코드. <https://www.rfc-editor.org/rfc/rfc6455> | RFC (확인 필요: 본문 직접 열람 안 함, 일반 지식 기반) |
| [S7] | Prometheus, Alerting rules (`for`, `keep_firing_for`). <https://prometheus.io/docs/prometheus/latest/configuration/alerting_rules/> | latest (2026-11-11 열람) |
| jar | `~/.gradle/caches/modules-2/files-2.1`의 jar를 JDK 21.0.13 `javap`·`jshell`로 확인 | 위 2절 표의 버전 |
| 내부 | `web/src/**`, `web/scripts/mock-ws-server.mjs`, `src/counting/{fake_timeline,run_density,cells}.py`, `src/predict/{schema,io}.py`, `src/flow/{run_flow,timeline_flow}.py`, `docs/*.md` | 작업 트리 (feat/flow-head-plane, web은 origin/main과 같음) |
