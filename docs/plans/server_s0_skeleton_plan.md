# 서버 S0 뼈대 구현 계획 (`feat/server-skeleton`)

| 항목 | 내용 |
|---|---|
| 작성일 | 2026-11-11 |
| 기준 | `docs/plans/server_impl_plan.md`(결정 기록, 2장 S0, 3장, 4장), `docs/research/server_research.md`(2.2, 2.6, 검증표 2·23·24·27) |
| 대상 | `server/`, 루트 `.gitignore`, `CLAUDE.md`, `docs/plans/server_*`, `docs/research/server_research.md` |
| 범위 | 빌드되는 빈 서버, 설정 파일 형식, 코드 규칙. 기능 코드 없음 |
| 상태 | 사용자 점검 완료(11-12), 구현 완료, 리뷰 통과 |

## 0. 확인한 사실
- Boot 4.1.2 BOM(`spring-boot-dependencies-4.1.2.pom`)이 Lombok을 관리한다: 130행 `<lombok.version>1.18.48</lombok.version>`, 1245행 `org.projectlombok:lombok`. Lombok 1.18.48은 JDK 21을 지원한다. 같은 BOM의 `jackson-bom.version` 3.1.7, `junit-jupiter.version` 6.0.3.
- `core.autocrlf=true`이고 루트 `.gitattributes`가 없다. `server/.gitattributes`는 `/gradlew`(LF), `*.bat`(CRLF), `*.jar`(binary)만 고정한다. 나머지는 Windows checkout 때 CRLF가 되어 `.editorconfig`의 LF와 어긋난다.
- 작업 트리에 S0 일부가 이미 있다 (커밋 안 됨, untracked). 11-11 17:10 수동 편집으로 들어간 것이다 (작업 규칙 위반, 사용자에게 보고함).
  - `build.gradle`: 공백 들여쓰기, Lombok 4줄
  - `application.yml` 생성, `application.properties` 삭제
  - `.editorconfig`
  - Java 파일: 탭 → 공백
  - `server/.gitkeep` 삭제
- 11-12: 위 S0 편집분은 `server/`를 Initializr 원본으로 되돌린 뒤 TDD 서브에이전트가 3·4장대로 다시 적용했다.
- 11-12 TDD 구현 뒤 `./gradlew clean build` 통과 (`contextLoads` tests=1, 실패 0), 7장 검증 1~11 통과.
- `settings.gradle`에 toolchain 자동 내려받기(foojay)가 없다. 로컬 JDK 21이 필요하고, `JAVA_HOME`이 비면 `gradlew`가 실행되지 않는다 (조사 2.6).
- `CLAUDE.local.md`(untracked)는 개인 파일이라 stage하지 않는다.

## 1. S0 / S1 경계
| 항목 | S0 | 이유 |
|---|---|---|
| `spring.application.name`, `server.port` | 넣음 | Boot 기본 키 |
| `spring.jackson.property-naming-strategy: SNAKE_CASE` | 넣음 | 전역 JSON 규칙(3장). CLAUDE.md 규칙과 같은 PR |
| `crowdsight.*` 전체 | **S1부터 각 PR** | 읽는 클래스가 없으면 검사되지 않는다. 키는 쓰는 PR에서 테스트와 함께 |
| `crowdsight.cors-origin-patterns` | **S3** | 결정 2 값은 계획 4장에 기록돼 있다 |
| `@ConfigurationPropertiesScan` | **S1** | 스캔할 클래스가 S1에 생긴다 |
| 가짜 타임라인 만드는 법 | **S1** (README) | S0 서버는 타임라인을 읽지 않는다 |
| `server/README.md` | 넣음 | 검증표 27: `JAVA_HOME` 없이는 팀원이 실행 못 함 |

## 2. 브랜치 절차
전제: D1(`feat/api-spec-v02`)의 `docs/api-spec.md` 수정이 그 브랜치에 커밋된 뒤.
```bash
cd /c/Users/Woori/Desktop/project/Triple-Y
git status --short          # 기대: tracked 수정은 "D server/.gitkeep" 하나, 나머지 ??
git switch main
git pull --ff-only
git switch -c feat/server-skeleton
```
- untracked 파일과 `.gitkeep` 삭제는 브랜치를 따라온다.
- `src/flow/` 등 다른 수정이 보이면 멈춘다.
- S0은 D1에 의존하지 않는다 → 기준은 `main` (쌓인 PR 아님).

계획·조사 문서는 이 PR에 별도 `docs:` 커밋으로 넣는다. CLAUDE.md 규칙과 PR 설명의 근거가 `server_impl_plan.md`라 리뷰어가 볼 수 있어야 한다.

## 3. 파일별 최종 내용
모든 파일 UTF-8, LF, 끝 줄바꿈. 예외 `gradlew.bat`(CRLF).

### 3.1 `server/build.gradle`
```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '4.1.2'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.tripley'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

configurations {
    compileOnly {
        extendsFrom annotationProcessor
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webmvc'
    implementation 'org.springframework.boot:spring-boot-starter-websocket'
    testImplementation 'org.springframework.boot:spring-boot-starter-webmvc-test'
    testImplementation 'org.springframework.boot:spring-boot-starter-websocket-test'
    compileOnly 'org.projectlombok:lombok'
    annotationProcessor 'org.projectlombok:lombok'
    testCompileOnly 'org.projectlombok:lombok'
    testAnnotationProcessor 'org.projectlombok:lombok'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}
```
- Lombok 버전은 적지 않는다 (BOM 1.18.48, 결정 3). `compileOnly`라 실행 jar에 없다.

### 3.2 `server/settings.gradle` (그대로)
```groovy
rootProject.name = 'crowdsight-server'
```

### 3.3 `server/src/main/resources/application.yml`
```yaml
spring:
  application:
    name: crowdsight-server
  jackson:
    property-naming-strategy: SNAKE_CASE

server:
  port: 8080

# crowdsight.* 설정은 그 값을 읽는 클래스와 같은 PR에서 추가한다 (S1: timeline·replay, S3: ws·cors ...)
```

### 3.4 `server/.editorconfig`
```ini
root = true

[*]
charset = utf-8
end_of_line = lf
insert_final_newline = true

[*.java]
indent_style = space
indent_size = 4
max_line_length = 120

[*.gradle]
indent_style = space
indent_size = 4

[*.{yml,yaml}]
indent_style = space
indent_size = 2

[*.bat]
end_of_line = crlf
```

### 3.5 `server/.gitattributes` (첫 줄 추가)
```gitattributes
* text=auto eol=lf
/gradlew text eol=lf
*.bat text eol=crlf
*.jar binary
```
- 첫 줄이 없으면 `core.autocrlf=true` PC에서 `.java`·`.yml`이 CRLF가 된다. 뒤 줄이 우선이라 `.bat`·`.jar` 예외는 유지된다.

### 3.6 `server/.gitignore` — Initializr 그대로. `logs/`는 루트에서 관리.

### 3.7 `CrowdsightServerApplication.java`
```java
package com.tripley.crowdsight;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

/**
 * CrowdSight 서버 시작점.
 * 타임라인을 1초씩 재생해 등급을 판정하고, WebSocket·REST로 화면에 보낸다.
 */
@SpringBootApplication
public class CrowdsightServerApplication {

    public static void main(String[] args) {
        SpringApplication.run(CrowdsightServerApplication.class, args);
    }

}
```

### 3.8 테스트 이름 변경 `CrowdsightServerApplicationTests` → `CrowdsightServerApplicationIntegrationTest`
```java
package com.tripley.crowdsight;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class CrowdsightServerApplicationIntegrationTest {

    @Test
    @DisplayName("스프링 컨텍스트가 오류 없이 뜬다")
    void contextLoads() {
    }

}
```
- 3장 규칙("통합은 `XxxIntegrationTest`")을 첫 테스트부터 지킨다. 옛 파일은 삭제.

### 3.9 `server/README.md` (새 파일)
````markdown
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
````

### 3.10 루트 `.gitignore` 서버 절
```gitignore
# 서버 (Spring Boot)
server/build/
server/.gradle/
server/out/
server/logs/
```
- S6의 `logs/alerts.jsonl`은 `*.log`에 걸리지 않아 폴더로 제외한다.

### 3.11 `CLAUDE.md` "코드 컨벤션"
73행을 아래로 바꾼다. 위 Python 규칙은 그대로.
```markdown
- `web/`(JavaScript) 규칙은 담당자가 개발을 시작할 때 정해 이 절에 추가한다.

### `server/` (Java)
| 항목 | 규칙 |
|---|---|
| 버전 | Java 21, Spring Boot 4.1.2, Gradle 9.8.2 wrapper (Groovy). 라이브러리 버전은 Boot 의존성 관리에 맡기고 직접 적지 않는다 |
| 형식 | 공백 4칸(yml 2칸), 줄 120자, LF. `server/.editorconfig`를 따른다 |
| 이름 | 클래스 `PascalCase`, 메서드·필드 `camelCase`, 상수 `UPPER_SNAKE`, 패키지 소문자 한 단어 |
| 주석 | 공개 클래스·메서드에 한국어 Javadoc. 식별자는 영어 |
| 주입 | 생성자 주입만. Lombok은 `@RequiredArgsConstructor`, `@Slf4j`만 쓴다 |
| DTO | `record`. 상태가 있는 클래스는 `final`로 두고 스레드 규칙을 Javadoc에 적는다 |
| null | 없을 수 있는 숫자는 `Double`. `Optional`은 반환형에만 쓴다 |
| JSON | 키는 `snake_case` (전역 `SNAKE_CASE`). Jackson 3: `tools.jackson.databind.*`, 어노테이션은 `com.fasterxml.jackson.annotation.*` |
| 설정 | 기준값·시간·경로는 `application.yml`의 `crowdsight.*`와 `CrowdsightProperties` 한 곳에만 둔다 |
| 시간 | `Clock`을 주입한다. `Instant.now()`, `System.currentTimeMillis()` 금지. 경과 시간만 `System.nanoTime()` |
| 예외·로그 | unchecked 예외 + 한국어 메시지. SLF4J, 한국어 메시지, `zone=`·`t=` 키 |
| 테스트 | JUnit Jupiter 6 + AssertJ. 단위 `XxxTest`, 통합 `XxxIntegrationTest`. 메서드는 영어 camelCase + `@DisplayName("한국어")` |
```

## 4. 탭 → 공백, 줄바꿈
```bash
cd /c/Users/Woori/Desktop/project/Triple-Y/server
grep -rnP '\t' --include='*.java' --include='*.gradle' --include='*.yml' --include='*.properties' --include='.editorconfig' . \
  --exclude-dir=build --exclude-dir=.gradle      # 기대: 출력 없음
```
- `gradlew.bat`은 CRLF 유지.

## 5. Stage와 커밋
```bash
cd /c/Users/Woori/Desktop/project/Triple-Y
git add server/ .gitignore
git update-index --chmod=+x server/gradlew   # Windows에서 추가하면 100644
git status --short
```
기대 (이 목록 밖이면 unstage):
```text
M  .gitignore
D  server/.gitkeep
A  server/.editorconfig
A  server/.gitattributes
A  server/.gitignore
A  server/README.md
A  server/build.gradle
A  server/gradle/wrapper/gradle-wrapper.jar
A  server/gradle/wrapper/gradle-wrapper.properties
A  server/gradlew
A  server/gradlew.bat
A  server/settings.gradle
A  server/src/main/java/com/tripley/crowdsight/CrowdsightServerApplication.java
A  server/src/main/resources/application.yml
A  server/src/test/java/com/tripley/crowdsight/CrowdsightServerApplicationIntegrationTest.java
```
커밋 3개:
1. `chore: 서버 뼈대 추가 (Spring Boot 4.1.2, Java 21, Lombok)` — server/, .gitignore
2. `docs: CLAUDE.md에 server Java 코드 규칙 추가` — CLAUDE.md
3. `docs: 서버 구현 계획·조사·S0 계획 추가` — docs/plans/server_impl_plan.md, docs/plans/server_s0_skeleton_plan.md, docs/research/server_research.md

`CLAUDE.local.md`와 `src/flow/` 수정분은 stage하지 않는다.

## 6. `server_impl_plan.md` 정정 (커밋 3에 포함)
2장 S0 목록을 아래로 바꾼다.
```markdown
- `application.properties` 삭제, `application.yml` 생성. S0에는 `spring.*`·`server.port`만, `crowdsight.*`는 쓰는 PR에서 추가.
- `@ConfigurationPropertiesScan`은 S1에서 `CrowdsightProperties`와 함께.
- 루트 `.gitignore` 서버 절에 `server/logs/`.
- `server/.editorconfig`(공백 4칸, yml 2칸, LF), `server/.gitattributes`에 `* text=auto eol=lf`. Spotless 안 씀.
- CLAUDE.md "코드 컨벤션"에 `server/` 규칙 (3장 + 결정 3).
- `server/README.md`: JAVA_HOME·실행 명령 (Git Bash, PowerShell).
- 테스트: `CrowdsightServerApplicationIntegrationTest.contextLoads` 통과.
```
결정 기록에 추가: `| 6 | S0 범위 | crowdsight.* 설정과 @ConfigurationPropertiesScan은 S1부터 쓰는 PR에서 |`

## 7. 검증 (Git Bash, `server/`)
```bash
export JAVA_HOME="/c/Program Files/Eclipse Adoptium/jdk-21.0.13.9-hotspot"
cd /c/Users/Woori/Desktop/project/Triple-Y/server
```
| # | 명령 | 기대 |
|---|---|---|
| 1 | `./gradlew clean build` | `BUILD SUCCESSFUL` |
| 2 | `head -2 build/test-results/test/TEST-com.tripley.crowdsight.CrowdsightServerApplicationIntegrationTest.xml` | `tests="1" skipped="0" failures="0" errors="0"` |
| 3 | `./gradlew dependencies --configuration compileClasspath \| grep lombok` | `org.projectlombok:lombok -> 1.18.48` |
| 4 | 같은 방법으로 `annotationProcessor`, `testCompileClasspath`, `testAnnotationProcessor` | `1.18.48` |
| 5 | `unzip -l build/libs/crowdsight-server-0.0.1-SNAPSHOT.jar \| grep -c lombok` | `0` |
| 6 | `./gradlew dependencies --configuration testRuntimeClasspath \| grep -E "junit-jupiter-api\|jackson-databind" \| sort -u` | `6.0.3`, `3.1.7` |
| 7 | `git -C .. grep --cached -n "$(printf '\t')" -- server` | 출력 없음 |
| 8 | `git -C .. ls-files --eol server \| grep -v "i/lf"` | 출력 없음 (`gradle-wrapper.jar`는 `i/-text`) |
| 9 | `git -C .. ls-files -s server/gradlew` | `100755` |
| 10 | `./gradlew bootRun` 후 `curl -s -o /dev/null -w "%{http_code}" localhost:8080/` | `Tomcat started on port 8080`, `404` |
| 11 | PowerShell `.\gradlew.bat build` | `BUILD SUCCESSFUL` |
- Lombok 실사용은 S1(`@Slf4j`)이 첫 확인이다.

## 8. PR 설명 (초안)
제목: `chore: 서버 뼈대 추가 (Spring Boot 4.1.2, Java 21)` / 기준 `main` ← `feat/server-skeleton`

- 목적: S1~S7을 시작할 수 있게 빌드되는 빈 Spring Boot 프로젝트와 코드 규칙. 기능 코드 없음.
- 변경: Initializr 뼈대, Lombok(compileOnly, 1.18.48), yml(`SNAKE_CASE`), `.editorconfig`·`.gitattributes`·`gradlew` 실행 권한, 테스트 이름, README, 루트 `.gitignore`, CLAUDE.md 규칙, 계획·조사 문서.
- 참고 결정: 결정 기록 2(허용 출처 → S3), 3(Java 규칙 + Lombok), 6(S0 범위). 조사 검증표 2·23·24·27.

> [!IMPORTANT]
> **CS 이슈**
> | **주제** | **내용** |
> |---|---|
> | **줄바꿈 (autocrlf)** | `core.autocrlf=true`면 checkout 시 CRLF. `.gitattributes` `eol=lf`로 고정, `.bat`만 CRLF |
> | **실행 권한 비트** | Windows는 권한을 기록하지 않아 `gradlew`가 644. `update-index --chmod=+x`로 755 |
> | **애노테이션 처리** | Lombok은 javac 애노테이션 프로세서. `compileOnly`+`annotationProcessor`라 실행 jar에 없음 |
> | **BOM 의존성 관리** | 버전을 적지 않으면 Boot BOM이 정함 (Lombok 1.18.48, Jackson 3.1.7, Jupiter 6.0.3) |
> | **toolchain과 JAVA_HOME** | Gradle 실행 JVM과 컴파일 JDK(toolchain 21)는 별개. 자동 내려받기가 없어 JDK 21 필요 |

| 선택 | 대안 | 고른 이유 |
|---|---|---|
| `application.yml` | `.properties` | 중첩 설정이 S1~S6에 많다 |
| Lombok (`@RequiredArgsConstructor`, `@Slf4j`만) | 직접 작성 | 반복 감소. DTO는 record라 `@Data`·`@Builder` 안 씀 |
| `.editorconfig` | Spotless | 담당 1명, 일정 짧음. 팀원이 늘면 재검토 |
| `crowdsight.*`는 쓰는 PR에서 | S0에 전체 | 읽는 클래스 없으면 검사 안 됨 |

남은 일: S1 `CrowdsightProperties`·`@ConfigurationPropertiesScan`·타임라인 설정·README 가짜 타임라인 명령. `[토론]` Vite proxy를 쓰면 CORS 불필요 (나예린).

## 9. 위험·가정
| 위험 | 대응 |
|---|---|
| D1 수정분이 S0 브랜치로 따라옴 | D1 커밋 뒤 브랜치 변경, `git status` 확인 |
| `.gitattributes` 변경 뒤에도 기존 파일이 CRLF | 지금은 새 파일뿐. 필요하면 `git add --renormalize server` |
| IDE가 Lombok을 인식 못 함 | README IDE 절 |
| 테스트 이름 변경을 팀원이 모름 | PR 변경 목록 |
| JDK 경로가 PC마다 다름 | README 경로는 예시 |
- (가정) Lombok은 `@RequiredArgsConstructor`, `@Slf4j`만 (결정 3을 좁게 읽음). 다른 것이 필요하면 CLAUDE.md를 먼저 고친다.
- (가정) `bootRun` 작업 폴더는 `server/`. S1 절대 경로 INFO 로그로 확인.
- (가정) S0은 D1과 독립. 계획 순서(D1 → S0)는 PR 여는 순서로만 따른다.
- `[토론]` Vite `server.proxy`를 쓰면 CORS(결정 2)가 필요 없다. S3 전에 나예린과 정한다.
- `[토론]` 서버 규칙을 CLAUDE.md에 둘지 `server/README.md`로 옮길지. 지금은 CLAUDE.md 73행 지시대로 CLAUDE.md.
