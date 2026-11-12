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
- 타임라인 파일 지정과 가짜 타임라인 만드는 법은 S1에서 추가한다.

## IDE
- Lombok을 쓴다 (`@RequiredArgsConstructor`, `@Slf4j`). IntelliJ는 annotation processing을 켠다. VS Code는 Java 확장팩이 지원한다.
- 들여쓰기·줄바꿈은 `server/.editorconfig`를 따른다.
