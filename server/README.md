# CrowdSight 서버 (Spring Boot)

타임라인 재생·등급 판정·알림을 WebSocket·REST로 제공한다. 설계는 `docs/plans/server_impl_plan.md`, 규칙은 `CLAUDE.md` "코드 컨벤션"을 따른다.

## 준비
- JDK 21 (Eclipse Temurin). Gradle은 wrapper(9.8.2)를 쓰므로 설치하지 않는다.
- `JAVA_HOME`을 JDK 21로 지정해야 `gradlew`가 실행된다 (toolchain 자동 내려받기 없음).

## 실행 (작업 폴더: `server/`)
Git Bash
```bash
export JAVA_HOME="/c/Program Files/Eclipse Adoptium/jdk-21.0.13.9-hotspot"
cd server
./gradlew build      # 컴파일 + 테스트
./gradlew bootRun    # http://localhost:8080
```

PowerShell
```powershell
$env:JAVA_HOME = 'C:\Program Files\Eclipse Adoptium\jdk-21.0.13.9-hotspot'
cd server
.\gradlew.bat build
.\gradlew.bat bootRun
```

- 8080을 이미 쓰고 있으면 `netstat -ano | findstr :8080`로 확인하고, `--args='--server.port=8081'` 또는 환경변수 `SERVER_PORT=8081`로 바꾼다.

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

## 판정 기준 (S4)
- 기준값은 `application.yml`의 `crowdsight.grade.*`(밀도), `crowdsight.instability.*`(군중 압력), `crowdsight.inflow.*`(유입)에 있다. 화면은 `hello.thresholds`로 같은 값을 받는다.
- 불안정: 셀 `pressure`가 0.02를 3초 연속 넘으면 그 셀은 심각 조건이다. `null`이거나 기준 이하면 연속이 끊긴다. 심각은 조건이 풀려도 10초에 한 단계씩 내려간다.
- 유입 경보(`zone.inflow_alert`): `inflow_ratio` 최근 5초 평균(값 3개 이상일 때)이 0.6을 넘고 `count`가 3명 이상이면 켜진다. 10초 연속 조건이 거짓이면 꺼진다. 반복·이동 뒤 처음 4초는 평균이 없다.
- DEBUG 로그 `재생 zone=… inflow_avg=… inflow_alert=…`로 5초 평균을 확인한다 (평균은 메시지로 보내지 않는다).
- 가짜 타임라인은 `inflow_ratio`가 0.6을 넘지 않아 유입 경보가 켜지지 않는다. 판정은 단위 테스트로 확인한다.

## 알림 (S5)
- 서버가 `alert`를 보낸다: 구역 등급이 경계·심각으로 오를 때(`GRADE_UP`), 판정 대상 셀이 불안정이 될 때(`INSTABILITY`), 유입 경보가 켜질 때(`INFLOW`). 같은 사건은 한 번만 보낸다.
- 한 초 안에서는 `zone_state` 다음에 `alert`가 오고, 둘의 `t`·`frame_ts`가 같다.
- 확인하지 않은 알림은 구역당 최근 100개(`crowdsight.unacked-alert-limit`)까지 메모리에 두고, 접속할 때 `hello.unacked_alerts`로 다시 보낸다. 서버를 재시작하면 사라진다. 확인하면 목록에서 빠진다.
- 반복 재생으로 처음에 돌아오면 알림 판정이 초기화되어 같은 알림이 새 ID로 다시 온다.
- 알림마다 INFO 로그 `알림 zone=… t=… alert_id=… reason=… level=… value=…`가 남는다.
- fixture와 가짜 타임라인 대부분은 경계에 닿지 않아 알림이 없을 수 있다. 판정은 단위 테스트로 확인한다.

## 알림 확인 (S6)
- 확인: `POST /api/alerts/{alert_id}/ack` → `200 {"alert_id","acked_at"}`. 다시 보내도 처음 확인 시각을 돌려준다. 보관 중이 아닌 ID는 `404`.
- 목록: `GET /api/zones/{zone_id}/alerts?unacked=true` (미확인만), `unacked`를 빼면 보관 중인 전체(원소에 `acked_at`).
- 처음 확인할 때마다 `logs/alerts.jsonl`(`crowdsight.alert-log`, `server/` 기준, git 제외)에 JSON 한 줄을 덧붙인다. 시작 로그에 절대 경로가 찍힌다.
- 기록 파일을 쓰지 못해도 확인은 반영되고, ERROR 로그에 쓰려던 줄이 남는다.
- 구역당 보관 알림은 100개(`crowdsight.unacked-alert-limit`)까지다. 넘으면 확인한 것부터 버린다.
- REST(`/api/**`)도 WebSocket과 같은 허용 출처(`crowdsight.cors-origin-patterns`)를 쓴다.
- 확인 예 (Git Bash): `curl -X POST http://localhost:8080/api/alerts/a-20261118-0001/ack`

## 타임라인 파일
- 서버는 시작할 때 `crowdsight.timeline-dir` 폴더의 `crowdsight.timeline-files`를 모두 읽고 검증한다 (`docs/timeline-spec.md` v0.2). 파일이 없거나 규격에 맞지 않으면 시작하지 않는다. 오류 메시지에 파일의 절대 경로가 있다.
- 기본값은 `../data/processed/timeline/E04_039.json`이다 (작업 폴더 `server/` 기준). 시작 로그 `타임라인 폴더: ...`에서 실제 절대 경로를 확인한다.
- 바꾸는 법: 실행 인자 `--crowdsight.timeline-files=a.json,b.json`, `--crowdsight.timeline-dir=D:/timeline`. 환경변수는 `CROWDSIGHT_TIMELINEDIR`, `CROWDSIGHT_TIMELINEFILES` (점은 `_`, `-`는 지우고 대문자).

### 가짜 타임라인으로 실행 (실제 `E04_039.json`이 없을 때)
PowerShell, 저장소 루트에서:
```powershell
# cv2와 PyYAML이 둘 다 있는 환경은 py311뿐이다 (crowdsight 환경은 PyYAML 없음)
conda activate py311
python -m src.counting.fake_timeline --homography infra/homography/E04_039.json `
    --out data/processed/timeline/fake_E04_039.json --duration 180
# 예측까지 보려면
python -m src.predict.run --input data/processed/timeline/fake_E04_039.json `
    --output data/processed/timeline/fake_E04_039.pred.json
```
- 이름을 `fake_`로 시작하게 한다. 실제 `E04_039.json`과 섞이지 않게 하기 위해서다.
- 가짜 데이터의 `inflow_ratio`는 최대 약 0.54라 유입 경보가 켜지지 않는다.

서버 실행 (`server/`):
```powershell
.\gradlew.bat bootRun --args='--crowdsight.timeline-files=fake_E04_039.json'
```
```bash
./gradlew bootRun --args='--crowdsight.timeline-files=fake_E04_039.json --logging.level.com.tripley.crowdsight.replay=DEBUG'
```
- 예측 파일은 `--crowdsight.timeline-files=fake_E04_039.pred.json`으로 지정한다.
- DEBUG를 켜면 `재생 zone=zone-e04-039 t=… grade=… max_density=…`가 1초마다 찍힌다. 시작 로그 `판정 대상 셀=n/m`으로 2㎡ 기준에 빠진 셀 수를 확인한다.
- 끝낼 때는 Ctrl+C. 8080이 남아 있으면 `netstat -ano | findstr :8080`으로 PID를 찾아 `taskkill /PID <pid> /F`.
- 테스트(`gradlew build`)는 `src/test/resources/timeline/valid_v02.json`을 쓰므로 실제 데이터가 필요 없다.

## IDE
- Lombok을 쓴다 (`@RequiredArgsConstructor`, `@Slf4j`). IntelliJ는 annotation processing을 켠다. VS Code는 Java 확장팩이 지원한다.
- 들여쓰기·줄바꿈은 `server/.editorconfig`를 따른다.
