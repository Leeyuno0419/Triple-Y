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
