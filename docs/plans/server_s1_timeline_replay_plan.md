# 서버 S1 타임라인 읽기·검증과 재생 구현 계획 (`feat/server-timeline-replay`)

| 항목 | 내용 |
|---|---|
| 작성일 | 2026-11-12 |
| 기준 | `docs/plans/server_impl_plan.md`(결정 기록 1~8, 1장, 2장 S1, 4~6장), `docs/plans/server_s0_skeleton_plan.md`(1장 S0/S1 경계), `docs/research/server_research.md`(1.2, 1.3, 2.2~2.4, 검증표 8·10·11·16·23·24·26), `docs/research/server_recheck_2026-11-11.md`(2절 #1~#3, #10), `docs/timeline-spec.md` v0.2, `origin/feat/api-spec-v02:docs/api-spec.md`, `main:src/predict/schema.py`, `main:web/src/lib/validate.ts` |
| 대상 | `server/` (S0 #42 위에 쌓음), `docs/plans/` |
| 범위 | `crowdsight.*` 설정 중 S1이 읽는 키, 타임라인 record·읽기·검증, 구역별 재생기, 1초 스케줄러, README 가짜 타임라인. 등급·WS·REST 없음 |
| 상태 | 계획. 사용자 점검 전 |
| 점검 | 사용자 점검 완료(11-12) |

## 0. 확인한 사실 (이번에 jar·코드로 확인)
- 작업 트리: 브랜치 `feat/server-skeleton`, 커밋 `2d9b008`. untracked는 `CLAUDE.local.md` 하나뿐이다. 이 파일은 stage하지 않는다.
- `server/` 현재 상태: `CrowdsightServerApplication`(`@SpringBootApplication`만 있음), `application.yml`(`spring.*`·`server.port`), `CrowdsightServerApplicationIntegrationTest.contextLoads` 하나.
- `data/processed/timeline/` 폴더가 로컬에 없다. 그래서 기본 설정(`E04_039.json`)으로 `bootRun`하면 S1부터는 시작이 실패한다. 이것은 의도한 동작이다 (6.3절).
- Jackson 3.1.7 jar로 확인한 것:
  - `JsonNode`는 `Iterable<JsonNode>`이다. `isIntegralNumber()`, `canConvertToInt()`, `isString()`, `has()`, `path()`, `isMissingNode()`가 있다.
  - `ObjectMapper`에 `readTree(Path)`, `treeToValue(JsonNode, TypeReference)`가 있다. `JsonMapper.builder().propertyNamingStrategy(...)`도 있다.
  - `JacksonException`은 `RuntimeException`이다. `TypeReference`는 `tools.jackson.core.type`에 있다.
- `ThreadPoolTaskScheduler.scheduleAtFixedRate(Runnable, Duration)`(spring-context 7.0.10)는 `errorHandlingTask(task, true)`를 거친다. 반복 작업에는 `TaskUtils.getDefaultErrorHandler(true)`(로그 후 계속)가 붙는다. 그래서 순수 JDK와 달리 예외 한 번으로 주기 작업이 멈추지 않는다.
  - 계획 5장 "예외" 행을 정정한다 (8장).
  - 구역마다 try/catch는 그래도 둔다. 목적은 같은 tick 안에서 다른 구역을 지키는 것이다.
- `ExecutorConfigurationSupport`(`ThreadPoolTaskScheduler`의 부모)는 `SmartLifecycle`이고 `DEFAULT_PHASE = 1073741823`이다. `SmartLifecycle.DEFAULT_PHASE`는 `Integer.MAX_VALUE`이다.
  - 그래서 `ReplayScheduler`(기본 phase)는 스케줄러보다 늦게 시작하고 먼저 멈춘다.
- Boot 4.1.2 `TaskExecutorConfigurations$OnExecutorCondition`은 두 경우에만 `applicationTaskExecutor`를 만든다: `@ConditionalOnMissingBean(Executor)`이거나 `spring.task.execution.mode`가 force일 때.
  - `ThreadPoolTaskScheduler`는 `Executor`이다. 그래서 이것을 빈으로 두면 Boot가 `applicationTaskExecutor`를 만들지 않는다 (CS 이슈, 9장).
- Boot 4.1.2 jar에 `org.springframework.boot.context.properties.ConfigurationPropertiesScan`, `bind.DefaultValue`, `bind.Binder`, `source.MapConfigurationPropertySource`가 있다.
- `SystemEnvironmentPropertyMapper.map(ConfigurationPropertyName)`은 환경변수 이름 후보를 여러 개 돌려준다. 기본형 `CROWDSIGHT_TIMELINEDIR`은 `-`를 지운 이름이고, 그 밖에 옛 형식이 있다.
  - 계획 4장 주석 `CROWDSIGHT_TIMELINE_DIR`가 옛 형식으로 동작하는지는 실행해 확인해야 한다 (확인 필요).
  - README에는 기본형 `CROWDSIGHT_TIMELINEDIR`를 적는다.
- `fake_timeline.py`(main)의 출력: `zone_id` `zone-e04-039`, `schema_version` `SCHEMA_VERSION`(`"0.2"`), `interval_s` 1, `cell_size_m` 2.0, `history_s` 30, `horizon_s` 60. `t`·`row`·`col`은 정수이고, 모든 프레임에 `count`, 모든 셀에 `counterflow` 키가 있다. 출력은 `validate_timeline`을 통과한 뒤 저장된다.
- `schema.py`와 `validate.ts`의 차이 (서버 판단에 영향이 있는 것):
  - 버전 둘째 자리 해석: `schema.py`는 `split(".")[1].isdigit()`라서 `"0.2a"`를 0으로 읽는다. `validate.ts`는 정규식 `^\d+\.(\d+)`라서 2로 읽는다. 결정 기록 7대로 서버는 `schema.py`를 따른다.
  - `t`·`row`·`col`·`duration_s`: `schema.py`는 `1.0 == 1`이라 `1.0`도 통과시킨다. 서버는 정수만 받는다 (조사 검증표 10).

## 1. 이번 계획에서 정한 것 (계획 대비)
| # | 항목 | 결정 | 이유 |
|---|---|---|---|
| 1 | S1 설정 키 | `timeline-dir`, `timeline-files`, `replay.interval-ms`, `replay.loop` 4개만 | S0 경계 원칙: 읽는 클래스가 있는 키만 넣는다 (2.1절) |
| 2 | `time-zone`·`Clock` | **S3로 미룸** | S1은 벽시계를 읽지 않는다. 재생은 tick 수로만 진행하고 간격은 스케줄러 `Duration`이다. `Clock`을 처음 쓰는 곳은 `FrameTimestamps`(S3)이다 |
| 3 | `timeline-dir` 형식 | `String` (`Path` 아님) | Spring `PathEditor`는 상대 경로를 먼저 classpath 리소스로 찾아본다. 이름이 겹치면 다른 폴더로 풀릴 수 있다 (확인 필요, 기억 기반). `Path.of(...)`는 코드에서 직접 부른다 |
| 4 | 스케줄러 스레드 수 | `poolSize` 1 | S1에는 재생 작업 하나뿐이다. S3에서 ping을 더할 때 2로 바꾼다 |
| 5 | `ENDED` 전환 시점 | 마지막 프레임을 준 **다음** tick | 마지막 초도 1초 동안 보인다. `playback(ended)`가 마지막 `zone_state`보다 먼저 가지 않는다 |
| 6 | 서버 추가 검증 규칙 | 4.3절 표 (9개) | 서버가 의존하는 값(`zone_id` 키, 정수 `t`, 1초 간격, 프레임 1개 이상)만 넣었다 |
| 7 | `@JsonIgnoreProperties(ignoreUnknown = true)` | 유지 | Jackson 3 기본값으로 이미 무시하지만, "모르는 키 무시"(규격 계약)를 코드에 드러낸다. 나중에 전역 설정이 바뀌어도 유지된다 |
| 8 | 테스트 분리 | 검증 거부 → `TimelineValidatorTest`, 읽기 결과 → `TimelineLoaderTest` | 거부 테스트는 파일 I/O 없이 트리만 고친다 |
| 9 | `CrowdsightProperties` 생성 | 테스트용 `TestProperties` 한 곳에서만 만든다 | S2~S6이 record 성분을 늘릴 때 고칠 곳을 하나로 둔다 |
| 10 | 로그 | tick은 DEBUG. 상태 변화(반복·끝)는 INFO. 오류는 ERROR | 30분 반복 동안 INFO는 약 10줄뿐이다 |
| 11 | `ZoneRegistry` 공개 API | `all()`만 | `find(zoneId)`는 WS(S3)가 처음 쓴다 |

## 2. 구조와 파일

### 2.1 추가·수정 파일
```text
server/
├─ README.md                                                     수정 (타임라인 절)
├─ src/main/resources/application.yml                            수정 (crowdsight.* 4키)
├─ src/main/java/com/tripley/crowdsight/
│  ├─ CrowdsightServerApplication.java                           수정 (@ConfigurationPropertiesScan)
│  ├─ config/  CrowdsightProperties.java, ReplaySchedulerConfig.java
│  ├─ timeline/ Meta, CellMeta, Models, Prediction, Frame, CellState, ZoneTimeline,
│  │            TimelineLoader, TimelineValidator, InvalidTimelineException
│  └─ replay/  PlaybackState, PlaybackSnapshot, Tick, ZonePlayer, ZoneRegistry, ReplayScheduler
└─ src/test/
   ├─ resources/timeline/valid_v02.json
   └─ java/com/tripley/crowdsight/
      ├─ CrowdsightServerApplicationIntegrationTest.java         수정 (properties)
      ├─ TimelineStartupIntegrationTest.java
      ├─ config/  CrowdsightPropertiesTest, TestProperties
      ├─ timeline/ TimelineFixtures, TimelineValidatorTest, TimelineLoaderTest
      └─ replay/  ZonePlayerTest, ReplaySchedulerTest, ReplaySchedulerIntegrationTest
docs/plans/server_s1_timeline_replay_plan.md                    (이 문서)
docs/plans/server_impl_plan.md                                   정정 (8장)
```
- `ZoneRuntime`(S2), `ZoneBroadcaster`(S3), `ClockConfig`(S3)는 만들지 않는다. 연결 지점은 7장에 적는다.

### 2.2 1초 흐름 (S1)
```text
ReplayScheduler (SmartLifecycle, phase MAX)
  start() → replayTaskScheduler.scheduleAtFixedRate(tickAll, interval-ms)
  tickAll():  for ZonePlayer p : registry.all()   (구역마다 try/catch)
                p.tick()            → Optional<Tick>          DEBUG zone= t=
                p.pollStateChange() → Optional<PlaybackSnapshot>  INFO (반복·끝)
ZoneRegistry (생성 시) ← TimelineLoader.loadAll() ← TimelineValidator (JsonNode) → record
```

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

# crowdsight.* 설정은 그 값을 읽는 클래스와 같은 PR에서 추가한다 (S2: grade, S3: time-zone·ws·cors ...)
crowdsight:
  timeline-dir: ../data/processed/timeline   # 작업 폴더(bootRun·test는 server/) 기준. 시작 로그에 절대 경로가 찍힌다
  timeline-files: [E04_039.json]             # 파일당 구역 1개. 가짜는 --crowdsight.timeline-files=fake_E04_039.json
  replay:
    interval-ms: 1000                        # 1초 = 타임라인 1칸 (interval_s 1)
    loop: true                               # 끝에서 처음으로 (E8 30분 반복)
```

| 키 | 읽는 곳 | 왜 S1에 |
|---|---|---|
| `timeline-dir` | `TimelineLoader.loadAll` | 파일 위치. 상대 경로라 절대 경로 INFO와 실패 메시지가 필요하다 (검증표 23) |
| `timeline-files` | `TimelineLoader.loadAll` | 실제 `E04_039.json`과 가짜 `fake_E04_039.json`을 실행 인자로 고른다 (검증표 24) |
| `replay.interval-ms` | `ReplayScheduler.start` | 1초 재생. 테스트는 20~50 ms로 줄인다 |
| `replay.loop` | `ZoneRegistry` → `ZonePlayer` | E8 30분 반복. S7에서 REST로 바꾼다 |
| ~~`time-zone`~~ | — | S3 (`ClockConfig`, `FrameTimestamps`). S1에서 읽는 곳이 없다 |

### 3.2 `config/CrowdsightProperties.java`
```java
package com.tripley.crowdsight.config;

import java.util.List;

import org.springframework.boot.context.properties.ConfigurationProperties;

/**
 * crowdsight.* 설정 (application.yml). 기준값·시간·경로는 이 record 한 곳에만 둔다.
 * 값 검사는 compact constructor에서 한다 (validation 스타터 안 씀). 틀리면 서버가 시작하지 않는다.
 * grade·instability·inflow·ws·alert-log·cors-origin-patterns·time-zone은 그 값을 쓰는 PR(S2~S6)에서 추가한다.
 *
 * @param timelineDir   타임라인 폴더. 상대 경로면 작업 폴더(bootRun·test는 server/) 기준
 * @param timelineFiles timelineDir 안의 파일 이름. 1개 이상, 파일당 구역 1개
 * @param replay        재생 설정
 */
@ConfigurationProperties("crowdsight")
public record CrowdsightProperties(String timelineDir, List<String> timelineFiles, Replay replay) {

    public CrowdsightProperties {
        if (timelineDir == null || timelineDir.isBlank()) {
            throw new IllegalArgumentException("crowdsight.timeline-dir 가 없습니다.");
        }
        if (timelineFiles == null || timelineFiles.isEmpty()) {
            throw new IllegalArgumentException("crowdsight.timeline-files 에 파일이 1개 이상 필요합니다.");
        }
        if (timelineFiles.stream().anyMatch(name -> name == null || name.isBlank())) {
            throw new IllegalArgumentException("crowdsight.timeline-files 에 빈 이름이 있습니다.");
        }
        if (replay == null) {
            throw new IllegalArgumentException("crowdsight.replay 가 없습니다.");
        }
        timelineFiles = List.copyOf(timelineFiles);
    }

    /**
     * 재생 설정.
     *
     * @param intervalMs 타임라인 1칸을 재생하는 간격(ms). 운영 1000, 테스트만 짧게
     * @param loop       끝에서 처음으로 돌아갈지
     */
    public record Replay(long intervalMs, boolean loop) {

        public Replay {
            if (intervalMs <= 0) {
                throw new IllegalArgumentException("crowdsight.replay.interval-ms 는 0보다 커야 합니다: " + intervalMs);
            }
        }
    }
}
```
- `@DefaultValue`는 쓰지 않는다. 기본값은 yml 한 곳에만 둔다 (CLAUDE.md "설정").

### 3.3 `CrowdsightServerApplication.java` 수정
```java
@SpringBootApplication
@ConfigurationPropertiesScan
public class CrowdsightServerApplication {
```
- import `org.springframework.boot.context.properties.ConfigurationPropertiesScan`.

### 3.4 `config/ReplaySchedulerConfig.java`
```java
package com.tripley.crowdsight.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskScheduler;

/** 재생 스케줄러 빈. 시작(initialize)과 종료(shutdown)는 Spring이 맡는다. */
@Configuration(proxyBeanMethods = false)
public class ReplaySchedulerConfig {

    /**
     * 재생 전용 스레드 1개. 주기 작업은 자기와 겹치지 않으므로 판정 상태는 이 스레드만 만진다.
     * S3에서 ping 작업을 더하면 poolSize를 2로 올린다.
     */
    @Bean
    public ThreadPoolTaskScheduler replayTaskScheduler() {
        ThreadPoolTaskScheduler scheduler = new ThreadPoolTaskScheduler();
        scheduler.setPoolSize(1);
        scheduler.setThreadNamePrefix("replay-");
        scheduler.setRemoveOnCancelPolicy(true);
        return scheduler;
    }
}
```
- `@Qualifier`는 쓰지 않는다.
  - 이 앱에서 `ThreadPoolTaskScheduler` 빈은 이것 하나뿐이다 (조사 2.1: SockJS 스케줄러는 빈으로 드러나지 않음).
  - 후보가 둘이 되면 Spring은 생성자 인자 이름 `replayTaskScheduler`를 빈 이름과 맞춰 고른다. Boot Gradle 플러그인이 `-parameters`를 켜므로 이 방식이 동작한다.
  - 그래서 Lombok `@RequiredArgsConstructor`(CLAUDE.md)를 그대로 쓸 수 있다.

## 4. 타임라인

### 4.1 record (`timeline/`)
```java
/** 타임라인 meta (파일당 1번). 이름 변환은 전역 SNAKE_CASE. */
@JsonIgnoreProperties(ignoreUnknown = true)
public record Meta(String zoneId, String cameraId, String videoId, int durationS, int intervalS,
                   double cellSizeM, Models models, Prediction prediction, List<CellMeta> cells) {}

/** 셀 고정 정보. imagePolygon은 0~1 좌표 4개. */
@JsonIgnoreProperties(ignoreUnknown = true)
public record CellMeta(String cellId, int row, int col, double walkableAreaM2, List<List<Double>> imagePolygon) {}

/** 사용한 모델·방법 이름. 판정에 쓰지 않고 hello.meta로 전달만 한다. */
@JsonIgnoreProperties(ignoreUnknown = true)
public record Models(String counter, String flow, String predictor) {}

/** 예측 입력 기간과 예측 시점(초). */
@JsonIgnoreProperties(ignoreUnknown = true)
public record Prediction(int historyS, int horizonS) {}

/** 1초 프레임. v0.1 파일이면 count는 null로 읽는다. */
@JsonIgnoreProperties(ignoreUnknown = true)
public record Frame(int t, Double inflowRatio, Double count, List<CellState> cells) {}

/** 초별 셀 상태. density 외의 측정·예측 값은 null(관측 없음)일 수 있다. */
@JsonIgnoreProperties(ignoreUnknown = true)
public record CellState(String cellId, Double density, Double vx, Double vy, Double speedVar,
                        Double pressure, Double counterflow,
                        @JsonProperty("density_pred_60s") Double densityPred60s) {}
```
- 어노테이션은 `com.fasterxml.jackson.annotation.JsonIgnoreProperties`, `JsonProperty`이다.
- `density`는 검증기가 숫자를 강제하지만 `Double`로 둔다. 계획 2장 S1과 S2 `nullSkipped`(방어용)를 따른 것이다.

```java
package com.tripley.crowdsight.timeline;

/**
 * 구역 1개의 검증된 타임라인. 만든 뒤 바꾸지 않는다 (metaJson도 읽기만 한다).
 *
 * @param schemaVersion 파일의 schema_version. "0.1"이면 count·counterflow는 null로 읽었다
 * @param meta          고정 정보
 * @param frames        t=0부터 1초마다 1개. 개수 = duration_s
 * @param metaJson      원본 meta 트리. S3에서 hello.meta로 그대로 보낸다 (모르는 키 포함, api-spec 3.1)
 * @param source        읽은 파일의 절대 경로
 */
public record ZoneTimeline(String schemaVersion, Meta meta, List<Frame> frames, JsonNode metaJson, Path source) {

    public ZoneTimeline {
        frames = List.copyOf(frames);
    }

    public String zoneId() {
        return meta.zoneId();
    }

    public int durationS() {
        return frames.size();
    }
}
```

### 4.2 `InvalidTimelineException`
```java
/** 타임라인 파일이 없거나 규격에 맞지 않을 때. 서버 시작을 멈춘다. 메시지에 파일 절대 경로가 들어간다. */
public final class InvalidTimelineException extends RuntimeException {

    private final Path file;

    public InvalidTimelineException(Path file, String reason) {
        this(file, reason, null);
    }

    public InvalidTimelineException(Path file, String reason, Throwable cause) {
        super("타임라인 파일 오류 [" + file + "]: " + reason, cause);
        this.file = file;
    }

    /** 문제가 된 파일의 절대 경로. */
    public Path file() {
        return file;
    }
}
```

### 4.3 검증 규칙 표 (결정 기록 7)
| # | 규칙 | `schema.py` | `validate.ts` | 서버 | 메시지 (서버, `schema.py` 문구 기준) |
|---|---|---|---|---|---|
| 1 | 루트 객체, `meta` 객체, `frames` 배열 | 예 | 예 | 예 | `timeline 형식 오류: meta(객체)와 frames(배열)가 필요합니다.` |
| 2 | `schema_version` 앞자리 `"0"` | 예 (`str()`) | 예 | 예 + **문자열만** | `지원하지 않는 schema_version: …` |
| 3 | 둘째 자리 해석 | `isdigit`, 아니면 0 | 정규식 | `schema.py`와 같게 | — |
| 4 | `meta` 9개 키 | 예 | 예 | 예 | `meta.{key} 가 없습니다.` |
| 5 | `zone_id`·`camera_id`·`video_id` 비지 않은 문자열 | 아니오 | 아니오 | **추가** | `meta.zone_id 는 비어 있지 않은 문자열이어야 합니다.` |
| 6 | `interval_s` == 1 (정수) | 아니오 | 아니오 | **추가** (검증표 11) | `meta.interval_s 는 1 이어야 합니다 (서버는 1초 간격만 재생합니다): 2` |
| 7 | `cell_size_m` > 0 숫자 | 변환 때 `float()` | 아니오 | **추가** | `meta.cell_size_m 는 0보다 큰 숫자여야 합니다.` |
| 8 | `models` 객체 | 변환 때 `**` | 아니오 | **추가** | `meta.models 는 객체여야 합니다.` |
| 9 | `meta.cells` 배열 | 예 | 예 | 예 | `meta.cells 는 배열이어야 합니다.` |
| 10 | `duration_s` 정수 | 아니오 (`5.0` 통과) | 예 | **정수만** | `meta.duration_s 는 정수여야 합니다.` |
| 11 | `duration_s` == `frames` 개수 | 예 | 예 | 예 | `meta.duration_s(6) 와 frames 개수(5) 가 다릅니다.` |
| 12 | `frames` 1개 이상 | 아니오 | 아니오 | **추가** | `frames 가 비어 있습니다 (재생할 프레임이 1개 이상 필요합니다).` |
| 13 | `history_s` 1 이상 정수 | 예 | 예 | 예 | `meta.prediction.history_s 는 1 이상의 정수여야 합니다.` |
| 14 | `horizon_s` 정수 | 변환 때 | 숫자 | **정수만** | `meta.prediction.horizon_s 는 정수여야 합니다.` |
| 15 | `cell_id` `^c-(\d{2})(\d{2})$` | 예 | 예 | 예 | `cell_id 형식 오류: "c-12" (c-행2자리열2자리)` |
| 16 | `row`·`col` 정수이고 `cell_id`와 일치 | 예 (`1.0` 통과) | 예 | **정수만** | `cell_id c-0102 와 row/col 이 다릅니다.` |
| 17 | `walkable_area_m2` > 0 | 예 | 예 | 예 | `c-0102: walkable_area_m2 는 0보다 커야 합니다 (0인 셀은 목록에서 뺌).` |
| 18 | `image_polygon` 0~1 좌표 4개 | 예 | 예 | 예 | `c-0000: image_polygon 은 0~1 좌표 4개여야 합니다.` |
| 19 | `cell_id` 중복 없음 | 예 | 예 | 예 | `meta.cells 에 중복 cell_id 가 있습니다.` |
| 20 | `frames[i].t` == i | 예 (`1.0` 통과) | 정수 | **정수만** (검증표 10) | `frames[3].t 는 3 이어야 합니다 (0부터 빠짐없이 증가하는 정수).` |
| 21 | `inflow_ratio` 없음·null·0~1 | 예 | 예 | 예 | `t=1: inflow_ratio 는 0~1 또는 null 입니다.` |
| 22 | v0.2 이상이면 `count` 키 필수 | 예 | 예 | 예 | `t=1: count 필드가 없습니다 (v0.2 부터 필수, 아직 없으면 null).` |
| 23 | `count` 있으면 0 이상 숫자 또는 null | 예 | 예 | 예 | `t=1: count 는 0 이상의 숫자 또는 null 입니다.` |
| 24 | `cells` 순서·전체가 `meta.cells`와 같음 | 예 | 예 | 예 | `t=2: cells 는 meta.cells 와 같은 순서로 모든 셀을 담아야 합니다.` |
| 25 | 셀 키 7개 존재 | 예 | 예 | 예 | `t=1 c-0000: vx 필드가 없습니다 (아직 없으면 null).` |
| 26 | `density` 숫자 (null 거부) | 예 | 예 | 예 | `t=1 c-0000: density 는 숫자여야 합니다.` |
| 27 | `vx`~`density_pred_60s` 숫자 또는 null | 예 | 예 | 예 | `t=1 c-0001: pressure 는 숫자 또는 null 입니다.` |
| 28 | v0.2 이상이면 `counterflow` 키 필수 | 예 | 예 | 예 | `t=1 c-0000: counterflow 필드가 없습니다 (v0.2 부터 필수, 아직 없으면 null).` |
| 29 | `counterflow` 있으면 0~1 또는 null | 예 | 예 | 예 | `t=1 c-0000: counterflow 는 0~1 또는 null 입니다.` |
| 30 | `t < history_s − 1`이면 `density_pred_60s` null | 예 | 예 | 예 | `t=0 c-0000: t < 1 이면 density_pred_60s 는 null 입니다.` |
| 31 | 모르는 키 무시 | 예 | 예 | 예 | — |
| 32 | `NaN`, 뒤에 붙은 쓰레기 | 파서 | 파서 | Jackson 거부 → 감쌈 | `JSON을 읽을 수 없습니다: …` |

- `density` 음수는 거부하지 않는다 (`schema.py`와 같다, 조사 1.2 표).
- 서버가 더 엄격한 규칙(2, 5~8, 10, 12, 14, 16, 20) 때문에 생산자 파일이 거부될 위험은 낮다. `fake_timeline.py`·`run_density.py` 출력은 모두 정수·문자열로 쓴다 (0장). 6단계에서 가짜 파일로 확인한다.

### 4.4 `timeline/TimelineValidator.java`
```java
package com.tripley.crowdsight.timeline;

import java.nio.file.Path;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

import tools.jackson.databind.JsonNode;

/**
 * 타임라인 JSON 트리가 규격 v0.2(v0.1 파일 허용)를 지키는지 검사한다.
 * 규칙은 src/predict/schema.py validate_timeline·web/src/lib/validate.ts와 같고 (결정 기록 7),
 * 서버 추가 규칙은 interval_s == 1, 정수 필드는 JSON 정수만(1.0·1.5 거부), frames 1개 이상,
 * schema_version·zone_id·camera_id·video_id 문자열, cell_size_m > 0, models 객체, horizon_s 정수다.
 * '키 없음'과 'null'을 구분해야 하므로 record로 바꾸기 전 JsonNode 단계에서 검사한다.
 * 상태가 없어 여러 스레드에서 불러도 된다.
 */
final class TimelineValidator {

    static final String SUPPORTED_MAJOR = "0";
    /** count·counterflow가 필수가 된 버전의 둘째 자리 (schema.py _V02_MINOR). */
    static final int V02_MINOR = 2;

    private static final Pattern CELL_ID = Pattern.compile("^c-(\\d{2})(\\d{2})$");
    private static final List<String> META_KEYS = List.of("zone_id", "camera_id", "video_id", "duration_s",
            "interval_s", "cell_size_m", "models", "prediction", "cells");
    private static final List<String> CELL_KEYS = List.of("cell_id", "density", "vx", "vy", "speed_var",
            "pressure", "density_pred_60s");
    private static final List<String> NULLABLE_CELL_KEYS = CELL_KEYS.subList(2, CELL_KEYS.size());

    private TimelineValidator() {
    }

    /**
     * 규격에 어긋나면 InvalidTimelineException을 던진다. 검사 순서는 schema.py와 같다.
     *
     * @param root 파일 전체 트리
     * @param file 메시지에 넣을 파일 절대 경로
     */
    static void validate(JsonNode root, Path file) {
        if (root == null || !root.isObject() || !root.path("meta").isObject() || !root.path("frames").isArray()) {
            throw fail(file, "timeline 형식 오류: meta(객체)와 frames(배열)가 필요합니다.");
        }
        JsonNode version = root.path("schema_version");
        if (!version.isString() || !version.asString().split("\\.", -1)[0].equals(SUPPORTED_MAJOR)) {
            throw fail(file, "지원하지 않는 schema_version: " + (version.isMissingNode() ? "(없음)" : version));
        }
        boolean requireV02 = schemaMinor(version.asString()) >= V02_MINOR;

        JsonNode meta = root.get("meta");
        for (String key : META_KEYS) {
            if (!meta.has(key)) {
                throw fail(file, "meta." + key + " 가 없습니다.");
            }
        }
        for (String key : List.of("zone_id", "camera_id", "video_id")) {
            JsonNode value = meta.get(key);
            if (!value.isString() || value.asString().isBlank()) {
                throw fail(file, "meta." + key + " 는 비어 있지 않은 문자열이어야 합니다.");
            }
        }
        JsonNode interval = meta.get("interval_s");
        if (!isInt(interval) || interval.intValue() != 1) {
            throw fail(file, "meta.interval_s 는 1 이어야 합니다 (서버는 1초 간격만 재생합니다): " + interval);
        }
        JsonNode cellSize = meta.get("cell_size_m");
        if (!cellSize.isNumber() || cellSize.doubleValue() <= 0) {
            throw fail(file, "meta.cell_size_m 는 0보다 큰 숫자여야 합니다.");
        }
        if (!meta.get("models").isObject()) {
            throw fail(file, "meta.models 는 객체여야 합니다.");
        }
        if (!meta.get("cells").isArray()) {
            throw fail(file, "meta.cells 는 배열이어야 합니다.");
        }
        JsonNode duration = meta.get("duration_s");
        int frameCount = root.get("frames").size();
        if (!isInt(duration)) {
            throw fail(file, "meta.duration_s 는 정수여야 합니다.");
        }
        if (duration.intValue() != frameCount) {
            throw fail(file, "meta.duration_s(" + duration + ") 와 frames 개수(" + frameCount + ") 가 다릅니다.");
        }
        if (frameCount < 1) {
            throw fail(file, "frames 가 비어 있습니다 (재생할 프레임이 1개 이상 필요합니다).");
        }
        JsonNode prediction = meta.get("prediction");
        JsonNode history = prediction.path("history_s");
        if (!prediction.isObject() || !isInt(history) || history.intValue() < 1) {
            throw fail(file, "meta.prediction.history_s 는 1 이상의 정수여야 합니다.");
        }
        if (!isInt(prediction.path("horizon_s"))) {
            throw fail(file, "meta.prediction.horizon_s 는 정수여야 합니다.");
        }
        int predMinT = history.intValue() - 1;

        List<String> ids = validateMetaCells(meta.get("cells"), file);

        JsonNode frames = root.get("frames");
        for (int i = 0; i < frames.size(); i++) {
            validateFrame(frames.get(i), i, ids, requireV02, predMinT, file);
        }
    }

    /** "0.2"의 둘째 자리(2). schema.py _schema_minor와 같게 없거나 숫자가 아니면 0. */
    static int schemaMinor(String version) {
        String[] parts = version.split("\\.", -1);
        if (parts.length < 2 || !parts[1].matches("\\d+")) {
            return 0;
        }
        return parts[1].length() > 9 ? Integer.MAX_VALUE : Integer.parseInt(parts[1]);
    }

    private static List<String> validateMetaCells(JsonNode cells, Path file) {
        List<String> ids = new ArrayList<>();
        for (JsonNode cell : cells) {
            JsonNode idNode = cell.path("cell_id");
            Matcher m = idNode.isString() ? CELL_ID.matcher(idNode.asString()) : null;
            if (m == null || !m.matches()) {
                throw fail(file, "cell_id 형식 오류: " + idNode + " (c-행2자리열2자리)");
            }
            String id = idNode.asString();
            JsonNode row = cell.path("row");
            JsonNode col = cell.path("col");
            if (!isInt(row) || !isInt(col) || row.intValue() != Integer.parseInt(m.group(1))
                    || col.intValue() != Integer.parseInt(m.group(2))) {
                throw fail(file, "cell_id " + id + " 와 row/col 이 다릅니다.");
            }
            JsonNode area = cell.path("walkable_area_m2");
            if (!area.isNumber() || area.doubleValue() <= 0) {
                throw fail(file, id + ": walkable_area_m2 는 0보다 커야 합니다 (0인 셀은 목록에서 뺌).");
            }
            if (!isPolygon(cell.path("image_polygon"))) {
                throw fail(file, id + ": image_polygon 은 0~1 좌표 4개여야 합니다.");
            }
            ids.add(id);
        }
        if (new HashSet<>(ids).size() != ids.size()) {
            throw fail(file, "meta.cells 에 중복 cell_id 가 있습니다.");
        }
        return ids;
    }

    private static void validateFrame(JsonNode frame, int i, List<String> ids, boolean requireV02,
                                      int predMinT, Path file) {
        JsonNode t = frame.path("t");
        if (!isInt(t) || t.intValue() != i) {
            throw fail(file, "frames[" + i + "].t 는 " + i + " 이어야 합니다 (0부터 빠짐없이 증가하는 정수).");
        }
        JsonNode ratio = frame.path("inflow_ratio");
        if (!isAbsent(ratio) && !(ratio.isNumber() && isUnit(ratio))) {
            throw fail(file, "t=" + i + ": inflow_ratio 는 0~1 또는 null 입니다.");
        }
        if (requireV02 && !frame.has("count")) {
            throw fail(file, "t=" + i + ": count 필드가 없습니다 (v0.2 부터 필수, 아직 없으면 null).");
        }
        JsonNode count = frame.path("count");
        if (!isAbsent(count) && !(count.isNumber() && count.doubleValue() >= 0)) {
            throw fail(file, "t=" + i + ": count 는 0 이상의 숫자 또는 null 입니다.");
        }
        JsonNode cells = frame.path("cells");
        if (!cells.isArray() || !idsOf(cells).equals(ids)) {
            throw fail(file, "t=" + i + ": cells 는 meta.cells 와 같은 순서로 모든 셀을 담아야 합니다.");
        }
        for (JsonNode cell : cells) {
            validateCell(cell, i, requireV02, predMinT, file);
        }
    }

    private static void validateCell(JsonNode cell, int t, boolean requireV02, int predMinT, Path file) {
        String where = "t=" + t + " " + cell.get("cell_id").asString() + ": ";
        for (String key : CELL_KEYS) {
            if (!cell.has(key)) {
                throw fail(file, where + key + " 필드가 없습니다 (아직 없으면 null).");
            }
        }
        if (!cell.get("density").isNumber()) {
            throw fail(file, where + "density 는 숫자여야 합니다.");
        }
        for (String key : NULLABLE_CELL_KEYS) {
            JsonNode value = cell.get(key);
            if (!value.isNull() && !value.isNumber()) {
                throw fail(file, where + key + " 는 숫자 또는 null 입니다.");
            }
        }
        if (requireV02 && !cell.has("counterflow")) {
            throw fail(file, where + "counterflow 필드가 없습니다 (v0.2 부터 필수, 아직 없으면 null).");
        }
        JsonNode counterflow = cell.path("counterflow");
        if (!isAbsent(counterflow) && !(counterflow.isNumber() && isUnit(counterflow))) {
            throw fail(file, where + "counterflow 는 0~1 또는 null 입니다.");
        }
        if (t < predMinT && !cell.get("density_pred_60s").isNull()) {
            throw fail(file, where + "t < " + predMinT + " 이면 density_pred_60s 는 null 입니다.");
        }
    }

    private static List<String> idsOf(JsonNode cells) {
        List<String> ids = new ArrayList<>();
        for (JsonNode cell : cells) {
            JsonNode id = cell.path("cell_id");
            ids.add(id.isString() ? id.asString() : null);
        }
        return ids;
    }

    private static boolean isPolygon(JsonNode polygon) {
        if (!polygon.isArray() || polygon.size() != 4) {
            return false;
        }
        for (JsonNode point : polygon) {
            if (!point.isArray() || point.size() != 2) {
                return false;
            }
            for (JsonNode xy : point) {
                if (!xy.isNumber() || !isUnit(xy)) {
                    return false;
                }
            }
        }
        return true;
    }

    /** JSON 정수이고 int 범위 (Jackson이 1.5를 1로 자르므로 record 변환 전에 본다). */
    private static boolean isInt(JsonNode node) {
        return node.isIntegralNumber() && node.canConvertToInt();
    }

    private static boolean isAbsent(JsonNode node) {
        return node.isMissingNode() || node.isNull();
    }

    private static boolean isUnit(JsonNode number) {
        double v = number.doubleValue();
        return v >= 0 && v <= 1;
    }

    private static InvalidTimelineException fail(Path file, String reason) {
        return new InvalidTimelineException(file, reason);
    }
}
```
- `has(key)`는 값이 `null`이어도 참이다 (`get`이 `NullNode`를 줌). Python `key in dict`와 같다.
- `frame`이 객체가 아니면 `path("t")`가 MissingNode를 준다. 그래서 `frames[i].t` 메시지로 거부된다.

### 4.5 `timeline/TimelineLoader.java`
```java
package com.tripley.crowdsight.timeline;

/**
 * 설정한 타임라인 파일을 읽고 검증해 record로 바꾼다. 하나라도 틀리면 예외를 던져 서버 시작을 멈춘다.
 * 상태가 없어 여러 스레드에서 불러도 된다 (서버 시작 때 한 번 쓴다).
 */
@Slf4j
@Component
@RequiredArgsConstructor
public class TimelineLoader {

    private static final TypeReference<List<Frame>> FRAME_LIST = new TypeReference<>() {
    };

    private final JsonMapper jsonMapper;
    private final CrowdsightProperties props;

    /** timeline-dir 안의 timeline-files를 설정 순서대로 읽는다. 같은 zone_id가 두 번 나오면 예외. */
    public List<ZoneTimeline> loadAll() {
        Path dir = Path.of(props.timelineDir()).toAbsolutePath().normalize();
        log.info("타임라인 폴더: {} (crowdsight.timeline-dir={})", dir, props.timelineDir());
        Map<String, ZoneTimeline> byZone = new LinkedHashMap<>();
        for (String name : props.timelineFiles()) {
            ZoneTimeline timeline = load(dir.resolve(name));
            ZoneTimeline previous = byZone.putIfAbsent(timeline.zoneId(), timeline);
            if (previous != null) {
                throw new InvalidTimelineException(timeline.source(),
                        "zone_id 중복: " + timeline.zoneId() + " (먼저 읽은 파일 " + previous.source() + ")");
            }
            log.info("타임라인 읽음 zone={} 길이={}초 셀={}개 버전={} 파일={}", timeline.zoneId(),
                    timeline.durationS(), timeline.meta().cells().size(), timeline.schemaVersion(), timeline.source());
        }
        return List.copyOf(byZone.values());
    }

    /** 파일 하나: 존재 확인 → readTree → 검증 → record. */
    ZoneTimeline load(Path file) {
        Path abs = file.toAbsolutePath().normalize();
        if (!Files.isRegularFile(abs)) {
            throw new InvalidTimelineException(abs, "파일이 없습니다. crowdsight.timeline-dir·timeline-files 설정과 "
                    + "작업 폴더(" + Path.of("").toAbsolutePath() + ")를 확인하세요.");
        }
        JsonNode root;
        try {
            root = jsonMapper.readTree(abs);
        } catch (JacksonException e) {
            throw new InvalidTimelineException(abs, "JSON을 읽을 수 없습니다: " + e.getOriginalMessage(), e);
        }
        return fromTree(root, abs);
    }

    /** 이미 읽은 트리를 검증해 record로 바꾼다. 테스트는 고친 트리로 이것을 부른다. */
    ZoneTimeline fromTree(JsonNode root, Path source) {
        TimelineValidator.validate(root, source);
        try {
            Meta meta = jsonMapper.treeToValue(root.get("meta"), Meta.class);
            List<Frame> frames = jsonMapper.treeToValue(root.get("frames"), FRAME_LIST);
            return new ZoneTimeline(root.get("schema_version").asString(), meta, frames, root.get("meta"), source);
        } catch (JacksonException e) {
            throw new InvalidTimelineException(source, "record 변환 실패: " + e.getOriginalMessage(), e);
        }
    }
}
```
- import: `tools.jackson.core.JacksonException`, `tools.jackson.core.type.TypeReference`, `tools.jackson.databind.JsonNode`, `tools.jackson.databind.json.JsonMapper`, `java.nio.file.Files`, `java.nio.file.Path`, `java.util.*`, `lombok.*`, `org.springframework.stereotype.Component`.
- 실행에서 쓰는 `JsonMapper`는 Boot가 만든 빈이다 (`SNAKE_CASE` 적용). 단위 테스트는 같은 설정으로 직접 만든다 (5.2절).
- 빈 파일은 `readTree`가 MissingNode를 준다(가정). 그러면 검증기 규칙 1로 거부된다.

## 5. 재생

### 5.1 `replay/` 값 타입
```java
/** 구역 재생 상태. playback 메시지에서는 소문자로 보낸다 (S3). */
public enum PlaybackState { PLAYING, PAUSED, ENDED }

/** 재생 상태 한 시점. hello.playback·playback 메시지용 (S3). t는 마지막으로 준 프레임(시작 전 0). */
public record PlaybackSnapshot(PlaybackState state, int t, boolean loop, int durationS) {}

/**
 * tick 한 번의 결과.
 *
 * @param discontinuity 첫 프레임·반복·이동(S7) 직후. 판정 상태를 초기화한다 (S2)
 * @param wrapped       반복으로 0으로 돌아옴. playback(playing, 0)을 먼저 보낸다 (S3)
 */
public record Tick(Frame frame, boolean discontinuity, boolean wrapped) {}
```
- `PAUSED`는 S7에서 처음 쓴다. 지금 넣는 이유는 api-spec 3.4의 세 상태를 enum에 한 번에 두기 위해서다.

### 5.2 `replay/ZonePlayer.java`
```java
package com.tripley.crowdsight.replay;

/**
 * 구역 1개의 재생 위치와 상태. tick마다 다음 프레임을 준다. Spring에 의존하지 않는다.
 * 스레드 규칙: tick()은 재생 스레드만 부른다. snapshot()·pollStateChange()와 S7의 제어 메서드는
 * 다른 스레드(WS·REST)에서도 부르므로 모든 공개 메서드를 synchronized로 둔다. 잠그는 시간은 짧다.
 */
public final class ZonePlayer {

    private final ZoneTimeline timeline;
    private final boolean loop;                 // S7 setLoop가 생기면 final을 뗀다
    private PlaybackState state = PlaybackState.PLAYING;
    private int nextT;
    private int currentT;
    private boolean pendingDiscontinuity = true;
    private PlaybackSnapshot pendingChange;     // 아직 가져가지 않은 상태 변화 (없으면 null)

    public ZonePlayer(ZoneTimeline timeline, boolean loop) {
        this.timeline = Objects.requireNonNull(timeline, "timeline");
        if (timeline.frames().isEmpty()) {
            throw new IllegalArgumentException("프레임이 없는 타임라인은 재생할 수 없습니다: zone=" + timeline.zoneId());
        }
        this.loop = loop;
    }

    /** 구역 ID. */
    public String zoneId() {
        return timeline.zoneId();
    }

    /** 재생 중인 타임라인. */
    public ZoneTimeline timeline() {
        return timeline;
    }

    /**
     * PLAYING이면 다음 프레임을 주고 한 칸 나아간다. 끝을 지나면 loop일 때 0으로 돌아가고(wrapped),
     * 아니면 ENDED가 되며 빈 값을 준다. PAUSED·ENDED이면 빈 값.
     */
    public synchronized Optional<Tick> tick() {
        if (state != PlaybackState.PLAYING) {
            return Optional.empty();
        }
        List<Frame> frames = timeline.frames();
        boolean wrapped = false;
        if (nextT >= frames.size()) {
            if (!loop) {
                state = PlaybackState.ENDED;
                pendingChange = snapshotLocked();
                return Optional.empty();
            }
            nextT = 0;
            wrapped = true;
            pendingDiscontinuity = true;
        }
        currentT = nextT;
        nextT++;
        boolean discontinuity = pendingDiscontinuity;
        pendingDiscontinuity = false;
        if (wrapped) {
            pendingChange = snapshotLocked();
        }
        return Optional.of(new Tick(frames.get(currentT), discontinuity, wrapped));
    }

    /** 지금 재생 상태. */
    public synchronized PlaybackSnapshot snapshot() {
        return snapshotLocked();
    }

    /** 마지막 tick에서 상태가 바뀌었으면(반복, 끝) 그 상태를 한 번만 준다. playback 메시지용. */
    public synchronized Optional<PlaybackSnapshot> pollStateChange() {
        PlaybackSnapshot change = pendingChange;
        pendingChange = null;
        return Optional.ofNullable(change);
    }

    private PlaybackSnapshot snapshotLocked() {
        return new PlaybackSnapshot(state, currentT, loop, timeline.durationS());
    }
}
```

### 5.3 `replay/ZoneRegistry.java`
```java
/**
 * 서버가 재생하는 구역 목록. 생성할 때 타임라인을 모두 읽고, 하나라도 틀리면 예외로 서버 시작을 멈춘다.
 * 목록은 만든 뒤 바뀌지 않으므로 여러 스레드에서 읽어도 된다. S2에서 ZonePlayer 대신 ZoneRuntime을 담는다.
 */
@Slf4j
@Component
public class ZoneRegistry {

    private final List<ZonePlayer> players;

    public ZoneRegistry(TimelineLoader loader, CrowdsightProperties props) {
        this.players = loader.loadAll().stream()
                .map(timeline -> new ZonePlayer(timeline, props.replay().loop()))
                .toList();
        players.forEach(p -> log.info("구역 등록 zone={} 길이={}초 반복={}",
                p.zoneId(), p.timeline().durationS(), props.replay().loop()));
    }

    /** 설정 순서의 모든 구역. */
    public List<ZonePlayer> all() {
        return players;
    }
}
```

### 5.4 `replay/ReplayScheduler.java`
```java
package com.tripley.crowdsight.replay;

/**
 * 모든 구역을 interval-ms마다 한 칸씩 재생한다.
 * 스레드 규칙: tickAll은 replayTaskScheduler의 스레드 하나에서만 돈다 (주기 작업은 자기와 겹치지 않음).
 * 구역 하나가 예외를 던져도 로그만 남기고 다른 구역과 다음 tick은 계속한다.
 * SmartLifecycle 기본 phase(MAX)라 다른 빈(웹 서버 포함)이 다 뜬 뒤 시작하고, 닫을 때 가장 먼저 멈춘다.
 * S1은 로그만 남긴다. S2에서 판정, S3에서 방송(ZoneBroadcaster)을 붙인다.
 */
@Slf4j
@Component
@RequiredArgsConstructor
public class ReplayScheduler implements SmartLifecycle {

    private final ZoneRegistry zones;
    private final ThreadPoolTaskScheduler replayTaskScheduler;
    private final CrowdsightProperties props;
    private volatile ScheduledFuture<?> future;

    @Override
    public void start() {
        if (future != null) {
            return;
        }
        Duration interval = Duration.ofMillis(props.replay().intervalMs());
        future = replayTaskScheduler.scheduleAtFixedRate(this::tickAll, interval);
        log.info("재생 시작: 구역 {}개, 간격 {} ms", zones.all().size(), interval.toMillis());
    }

    @Override
    public void stop() {
        ScheduledFuture<?> running = future;
        if (running != null) {
            running.cancel(false);
            future = null;
            log.info("재생 멈춤");
        }
    }

    @Override
    public boolean isRunning() {
        return future != null;
    }

    /** 모든 구역을 한 칸씩 진행한다. 재생 스레드에서만 부른다 (테스트는 직접 부른다). */
    void tickAll() {
        for (ZonePlayer player : zones.all()) {
            try {
                Optional<Tick> tick = player.tick();
                player.pollStateChange().ifPresent(s -> log.info("재생 상태 zone={} state={} t={} loop={}",
                        player.zoneId(), s.state(), s.t(), s.loop()));
                tick.ifPresent(k -> log.debug("재생 zone={} t={} discontinuity={} wrapped={}",
                        player.zoneId(), k.frame().t(), k.discontinuity(), k.wrapped()));
                // S2: discontinuity면 판정 초기화 후 evaluate. S3: [playback?] → zone_state 방송
            } catch (RuntimeException e) {
                log.error("구역 재생 중 오류, 다음 구역으로 계속 zone={}", player.zoneId(), e);
            }
        }
    }
}
```
- 첫 실행은 `start()` 직후이다 (`scheduleAtFixedRate(Runnable, Duration)`의 시작 시각 = 지금).
- `Error`(OOM 등)는 잡지 않는다.

## 6. 테스트

### 6.1 fixture `server/src/test/resources/timeline/valid_v02.json`
`count` = Σ(`density` × `walkable_area_m2`). `pressure` = `density` × `speed_var`. `history_s` 2이므로 `t < 1`(t0)만 예측 null이다.
```json
{
  "schema_version": "0.2",
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
  "frames": [
    { "t": 0, "inflow_ratio": null, "count": 6.5, "cells": [
      { "cell_id": "c-0000", "density": 1.25, "vx": 0.1, "vy": 0.0, "speed_var": 0.004, "pressure": 0.005,
        "counterflow": null, "density_pred_60s": null },
      { "cell_id": "c-0001", "density": 0, "vx": null, "vy": null, "speed_var": null, "pressure": 0,
        "counterflow": null, "density_pred_60s": null },
      { "cell_id": "c-0102", "density": 1.0, "vx": 0.05, "vy": -0.02, "speed_var": 0.002, "pressure": 0.002,
        "counterflow": null, "density_pred_60s": null }
    ] },
    { "t": 1, "inflow_ratio": 0.3, "count": 11.0, "cells": [
      { "cell_id": "c-0000", "density": 1.5, "vx": 0.2, "vy": 0.0, "speed_var": 0.006, "pressure": 0.009,
        "counterflow": 0.12, "density_pred_60s": 1.8 },
      { "cell_id": "c-0001", "density": 0.5, "vx": 0.1, "vy": 0.1, "speed_var": 0.003, "pressure": 0.0015,
        "counterflow": null, "density_pred_60s": 0.6 },
      { "cell_id": "c-0102", "density": 2.0, "vx": null, "vy": null, "speed_var": null, "pressure": null,
        "counterflow": null, "density_pred_60s": 2.1 }
    ] },
    { "t": 2, "inflow_ratio": 0.45, "count": 15.0, "cells": [
      { "cell_id": "c-0000", "density": 2.0, "vx": 0.25, "vy": -0.05, "speed_var": 0.008, "pressure": 0.016,
        "counterflow": 0.1, "density_pred_60s": 2.5 },
      { "cell_id": "c-0001", "density": 1.0, "vx": null, "vy": null, "speed_var": null, "pressure": null,
        "counterflow": null, "density_pred_60s": 1.1 },
      { "cell_id": "c-0102", "density": 2.0, "vx": 0.1, "vy": 0.0, "speed_var": 0.004, "pressure": 0.008,
        "counterflow": null, "density_pred_60s": 2.2 }
    ] },
    { "t": 3, "inflow_ratio": 0.7, "count": 22.8, "cells": [
      { "cell_id": "c-0000", "density": 3.2, "vx": 0.3, "vy": -0.1, "speed_var": 0.01, "pressure": 0.032,
        "counterflow": 0.2, "density_pred_60s": 3.6 },
      { "cell_id": "c-0001", "density": 1.0, "vx": 0.15, "vy": 0.05, "speed_var": 0.005, "pressure": 0.005,
        "counterflow": null, "density_pred_60s": 1.2 },
      { "cell_id": "c-0102", "density": 4.0, "vx": 0.2, "vy": 0.1, "speed_var": 0.006, "pressure": 0.024,
        "counterflow": null, "density_pred_60s": 4.4 }
    ] },
    { "t": 4, "inflow_ratio": 0.65, "count": null, "cells": [
      { "cell_id": "c-0000", "density": 4.2, "vx": 0.3, "vy": -0.1, "speed_var": 0.012, "pressure": 0.0504,
        "counterflow": 0.25, "density_pred_60s": 4.6 },
      { "cell_id": "c-0001", "density": 1.5, "vx": 0.2, "vy": 0.0, "speed_var": 0.006, "pressure": 0.009,
        "counterflow": null, "density_pred_60s": 1.6 },
      { "cell_id": "c-0102", "density": 5.5, "vx": 0.2, "vy": 0.1, "speed_var": 0.006, "pressure": 0.033,
        "counterflow": null, "density_pred_60s": 5.9 }
    ] }
  ]
}
```
손 계산 (`count`):

| t | 계산 | 값 |
|---|---|---|
| 0 | 1.25×4 + 0×4 + 1.0×1.5 = 5 + 0 + 1.5 | 6.5 |
| 1 | 1.5×4 + 0.5×4 + 2.0×1.5 = 6 + 2 + 3 | 11.0 |
| 2 | 2.0×4 + 1.0×4 + 2.0×1.5 = 8 + 4 + 3 | 15.0 |
| 3 | 3.2×4 + 1.0×4 + 4.0×1.5 = 12.8 + 4 + 6 | 22.8 |
| 4 | — | null (G1처럼 값 없음, 키는 있음) |

- 정수 `0`(t0 `c-0001`의 `density`·`pressure`)도 들어 있다. `Double` 0.0으로 읽히는지 확인하는 용도이다.
- t4 `c-0102`(1.5㎡) 5.5는 S2 `smallCellExcluded` 류 시험에도 쓸 수 있다.

### 6.2 테스트 도우미
`src/test/java/com/tripley/crowdsight/timeline/TimelineFixtures.java`
```java
/** 테스트용 타임라인. validTree()는 부를 때마다 새로 읽으므로 고쳐도 다른 테스트에 영향이 없다. */
public final class TimelineFixtures {

    public static final JsonMapper MAPPER = JsonMapper.builder()
            .propertyNamingStrategy(PropertyNamingStrategies.SNAKE_CASE)   // application.yml과 같게
            .build();

    private TimelineFixtures() {
    }

    /** classpath의 valid_v02.json 절대 경로 (build/resources/test/timeline/...). */
    public static Path fixturePath() {
        try {
            return Path.of(TimelineFixtures.class.getResource("/timeline/valid_v02.json").toURI());
        } catch (URISyntaxException e) {
            throw new IllegalStateException(e);
        }
    }

    public static ObjectNode validTree() {
        return (ObjectNode) MAPPER.readTree(fixturePath());
    }

    public static ObjectNode meta(ObjectNode root) {
        return (ObjectNode) root.get("meta");
    }

    public static ObjectNode metaCell(ObjectNode root, int index) {
        return (ObjectNode) root.get("meta").get("cells").get(index);
    }

    public static ObjectNode frame(ObjectNode root, int t) {
        return (ObjectNode) root.get("frames").get(t);
    }

    public static ObjectNode cell(ObjectNode root, int t, int index) {
        return (ObjectNode) frame(root, t).get("cells").get(index);
    }

    /** 재생 시험용 최소 타임라인 (셀 없음, t=0..duration-1). 검증기를 거치지 않는다. */
    public static ZoneTimeline timelineOf(int duration) {
        Meta meta = new Meta("zone-test", "cam-test", "TEST_001", duration, 1, 2.0,
                new Models("fixture", "fixture", "fixture"), new Prediction(2, 60), List.of());
        List<Frame> frames = IntStream.range(0, duration)
                .mapToObj(t -> new Frame(t, null, null, List.of()))
                .toList();
        return new ZoneTimeline("0.2", meta, frames, MAPPER.createObjectNode(), Path.of("synthetic.json"));
    }
}
```
`src/test/java/com/tripley/crowdsight/config/TestProperties.java`
```java
/** 테스트용 CrowdsightProperties. S2~S6이 성분을 늘리면 여기만 고친다. */
public final class TestProperties {

    private TestProperties() {
    }

    public static CrowdsightProperties of(String timelineDir, List<String> files, long intervalMs, boolean loop) {
        return new CrowdsightProperties(timelineDir, files, new CrowdsightProperties.Replay(intervalMs, loop));
    }

    public static CrowdsightProperties replay(long intervalMs, boolean loop) {
        return of("src/test/resources/timeline", List.of("valid_v02.json"), intervalMs, loop);
    }
}
```

### 6.3 `config/CrowdsightPropertiesTest` (단위, `Binder`)
`new Binder(new MapConfigurationPropertySource(map)).bind("crowdsight", CrowdsightProperties.class).get()`. 기본 맵은 `timeline-dir`=`../data/processed/timeline`, `timeline-files[0]`=`a.json`, `timeline-files[1]`=`b.json`, `replay.interval-ms`=`1000`, `replay.loop`=`true`.

| 메서드 | `@DisplayName` | 입력 | 기대 |
|---|---|---|---|
| `bindsTimelineAndReplayKeys` | "timeline·replay 키를 record로 묶는다" | 기본 맵 | `timelineDir` "../data/processed/timeline", files [a.json, b.json], `intervalMs` 1000, `loop` true |
| `rejectsNonPositiveInterval` (`@ParameterizedTest @ValueSource(longs = {0, -1})`) | "재생 간격이 0 이하이면 바인딩에서 거부한다" | `replay.interval-ms` 0, −1 | `BindException`, `rootCause()` 메시지에 `crowdsight.replay.interval-ms` |
| `rejectsEmptyTimelineFiles` | "타임라인 파일이 없으면 거부한다" | `timeline-files` 키 제거 | `BindException`, 원인 메시지 `crowdsight.timeline-files` |
| `rejectsMissingTimelineDir` | "타임라인 폴더가 없으면 거부한다" | `timeline-dir` 제거 | 원인 메시지 `crowdsight.timeline-dir` |

### 6.4 `timeline/TimelineValidatorTest` (단위)
- `FILE = Path.of("fixture.json").toAbsolutePath()`, `tree = TimelineFixtures.validTree()`.
- 거부 테스트는 모두 `assertThatThrownBy(() -> TimelineValidator.validate(tree, FILE)).isInstanceOf(InvalidTimelineException.class).hasMessageContaining(…)` 형식이다.

| 메서드 | `@DisplayName` | 입력 (fixture에서 고칠 곳) | 기대 메시지 일부 |
|---|---|---|---|
| `acceptsFixture` | "fixture는 통과한다" | 그대로 | 예외 없음 |
| `messageHasAbsolutePath` | "오류 메시지에 파일 절대 경로가 들어간다" | `interval_s` 2 | `FILE.toString()`, `e.file()` == FILE |
| `rejectsNonObjectRoot` | "루트가 객체가 아니면 거부한다" | 루트 `MAPPER.createArrayNode()` | `meta(객체)와 frames(배열)` |
| `rejectsMajorVersion` | "앞자리가 0이 아닌 버전은 거부한다" | `schema_version` "1.0" | `지원하지 않는 schema_version` |
| `rejectsMissingSchemaVersion` | "schema_version이 없으면 거부한다" | 키 삭제 | `schema_version: (없음)` |
| `rejectsNumericSchemaVersion` | "schema_version이 숫자면 거부한다 (서버 추가)" | `put("schema_version", 0.2)` | `schema_version` |
| `rejectsMissingMetaKey` | "meta 필수 키가 빠지면 거부한다" | `meta.camera_id` 삭제 | `meta.camera_id 가 없습니다` |
| `rejectsBlankZoneId` | "zone_id가 빈 문자열이면 거부한다 (서버 추가)" | `zone_id` "" | `meta.zone_id 는 비어 있지 않은 문자열` |
| `rejectsInterval2` | "interval_s가 1이 아니면 거부한다 (서버 추가)" | `interval_s` 2 | `meta.interval_s 는 1 이어야 합니다` |
| `rejectsFractionalInterval` | "interval_s 1.0도 거부한다 (서버 추가)" | `interval_s` 1.0 | `meta.interval_s 는 1 이어야 합니다` |
| `rejectsZeroCellSize` | "cell_size_m가 0이면 거부한다 (서버 추가)" | `cell_size_m` 0 | `meta.cell_size_m` |
| `rejectsNonObjectModels` | "models가 객체가 아니면 거부한다 (서버 추가)" | `models` "x" | `meta.models 는 객체` |
| `rejectsDurationMismatch` | "duration_s와 프레임 수가 다르면 거부한다" | `duration_s` 6 | `meta.duration_s(6) 와 frames 개수(5) 가 다릅니다` |
| `rejectsFractionalDuration` | "duration_s 5.0은 거부한다 (서버 추가)" | `duration_s` 5.0 | `meta.duration_s 는 정수여야` |
| `rejectsEmptyFrames` | "프레임이 없으면 거부한다 (서버 추가)" | `duration_s` 0, `frames` [] | `frames 가 비어 있습니다` |
| `rejectsHistoryZero` | "history_s가 0이면 거부한다" | `prediction.history_s` 0 | `history_s 는 1 이상의 정수` |
| `rejectsFractionalHorizon` | "horizon_s가 정수가 아니면 거부한다 (서버 추가)" | `prediction.horizon_s` 60.5 | `horizon_s 는 정수` |
| `rejectsCellIdFormat` | "cell_id 형식이 틀리면 거부한다" | meta 셀 2 `cell_id` "c-12" | `cell_id 형식 오류` |
| `rejectsCellIdRowMismatch` | "cell_id와 row/col이 다르면 거부한다" | meta 셀 2(`c-0102`) `col` 3 | `cell_id c-0102 와 row/col 이 다릅니다` |
| `rejectsFractionalRow` | "row 1.0은 거부한다 (서버 추가)" | meta 셀 2 `row` 1.0 | `row/col` |
| `rejectsZeroArea` | "보행 면적 0인 셀은 거부한다" | meta 셀 2 `walkable_area_m2` 0 | `c-0102: walkable_area_m2 는 0보다 커야` |
| `rejectsPolygonOutOfRange` | "다각형 좌표가 0~1 밖이면 거부한다" | meta 셀 0 `image_polygon[1][0]` 1.2 | `c-0000: image_polygon` |
| `rejectsDuplicateCellId` | "cell_id가 중복이면 거부한다" | meta `cells[1]` = `cells[0].deepCopy()` | `중복 cell_id` |
| `rejectsGapInT` | "t가 빠지면 거부한다" | `frames[3].t` 4 | `frames[3].t 는 3 이어야` |
| `rejectsFractionalT` | "t 1.5는 거부한다" | `frames[1].t` 1.5 | `frames[1].t` |
| `rejectsIntegralFloatT` | "t 1.0도 거부한다 (서버 추가, Jackson 정수 변환 방지)" | `frames[1].t` 1.0 | `frames[1].t` |
| `rejectsInflowOutOfRange` | "inflow_ratio가 1을 넘으면 거부한다" | `frames[1].inflow_ratio` 1.2 | `t=1: inflow_ratio 는 0~1 또는 null` |
| `acceptsMissingInflowKey` | "inflow_ratio 키가 없어도 통과한다" | `frames[1]`에서 `inflow_ratio` 삭제 | 예외 없음 |
| `rejectsMissingCountV02` | "v0.2에서 count 키가 없으면 거부한다" | `frames[1]` `count` 삭제 | `t=1: count 필드가 없습니다` |
| `acceptsZeroCount` | "count가 0이면 통과한다" | `frames[1].count` 0 | 예외 없음 |
| `rejectsNegativeCount` | "count가 음수면 거부한다" | `frames[1].count` −1 | `t=1: count 는 0 이상의 숫자 또는 null` |
| `rejectsStringCount` | "count가 문자열이면 거부한다" | `frames[1].count` "6.5" | `t=1: count 는 0 이상` |
| `rejectsNegativeCountInV01` | "v0.1이어도 count가 있으면 범위를 검사한다" | 버전 "0.1", `frames[1].count` −1 | `t=1: count` |
| `rejectsCellOrder` | "셀 순서가 다르면 거부한다" | t2 `cells[0]`↔`cells[1]` 교환 | `t=2: cells 는 meta.cells 와 같은 순서` |
| `rejectsMissingCell` | "셀이 빠지면 거부한다" | t2 `cells`에서 2번 삭제 | `t=2: cells` |
| `rejectsNullDensity` | "density가 null이면 거부한다" | t1 `c-0000` `density` null | `t=1 c-0000: density 는 숫자여야` |
| `rejectsMissingVxKey` | "vx 키가 없으면 거부한다" | t1 `c-0000` `vx` 삭제 | `t=1 c-0000: vx 필드가 없습니다` |
| `rejectsStringPressure` | "pressure가 문자열이면 거부한다" | t1 `c-0001` `pressure` "0.1" | `t=1 c-0001: pressure 는 숫자 또는 null` |
| `rejectsMissingCounterflowV02` | "v0.2에서 counterflow 키가 없으면 거부한다" | t1 `c-0000` `counterflow` 삭제 | `t=1 c-0000: counterflow 필드가 없습니다` |
| `rejectsCounterflowOutOfRange` | "counterflow가 1을 넘으면 거부한다" | t1 `c-0000` `counterflow` 1.2 | `t=1 c-0000: counterflow 는 0~1 또는 null` |
| `rejectsNegativeCounterflow` | "counterflow가 음수면 거부한다" | t1 `c-0000` `counterflow` −0.1 | `t=1 c-0000: counterflow 는 0~1 또는 null` |
| `rejectsEarlyPrediction` | "history_s−1 이전 초에 예측값이 있으면 거부한다" | t0 `c-0000` `density_pred_60s` 1.0 | `t=0 c-0000: t < 1 이면 density_pred_60s 는 null` |
| `acceptsV01WithoutNewKeys` | "v0.1은 count·counterflow 키가 없어도 통과한다" | 버전 "0.1", 모든 프레임 `count`·모든 셀 `counterflow` 삭제 | 예외 없음 |
| `acceptsFutureMinor` | "v0.3도 앞자리가 0이면 통과한다" | 버전 "0.3" | 예외 없음 |
| `parsesMinorLikeSchemaPy` (`@ParameterizedTest @CsvSource`) | "버전 둘째 자리는 schema.py와 같게 읽는다" | `"0.2"`→2, `"0.1"`→1, `"0"`→0, `"0.x"`→0, `"0.10"`→10, `"0.2.1"`→2, `"0."`→0, `"0.2a"`→0 | `schemaMinor` 값 |

### 6.5 `timeline/TimelineLoaderTest` (단위, `new TimelineLoader(TimelineFixtures.MAPPER, TestProperties.of(…))`)
| 메서드 | `@DisplayName` | 입력 | 기대 |
|---|---|---|---|
| `loadsValidV02` | "v0.2 fixture를 record로 읽는다" | `load(fixturePath())` | `zoneId` "zone-test", `schemaVersion` "0.2", `meta().cells()` 3, `frames()` 5, `meta().cells().get(2).walkableAreaM2()` 1.5, `frames[0].count()` 6.5, `frames[3].count()` 22.8, `frames[4].count()` null, `frames[0].inflowRatio()` null, `frames[1].inflowRatio()` 0.3, `frames[2].cells[1].vx()` null, `frames[0].cells[1].density()`·`pressure()` 0.0, `frames[1].cells[0].counterflow()` 0.12, `frames[3].cells[0].densityPred60s()` 3.6, `prediction().historyS()` 2, `metaJson().get("zone_id").asString()` "zone-test", `source()` 절대 경로이고 `valid_v02.json`으로 끝남 |
| `loadsV01WithoutCountAndCounterflow` | "v0.1 파일은 count·counterflow를 null로 읽는다" | 트리 버전 "0.1", 두 키 모두 삭제, `fromTree` | 통과, 모든 프레임 `count()` null, 모든 셀 `counterflow()` null, `schemaVersion` "0.1" |
| `loadsV02WithNullCountAndCounterflow` | "v0.2의 null count·counterflow는 null로 읽는다" | `frames[1].count` null, t1 `c-0000` `counterflow` null | `frames[1].count()` null, `frames[1].cells[0].counterflow()` null |
| `ignoresUnknownKeys` | "모르는 키는 무시하고 metaJson에는 남긴다" | `meta.foo`=1, `frames[0].bar`="x", t0 `c-0000` `baz`=true | 통과, `metaJson().get("foo").intValue()` 1 |
| `rejectsMissingFileWithAbsolutePath` | "파일이 없으면 절대 경로를 넣어 거부한다" | `@TempDir dir`, `load(dir.resolve("nope.json"))` | `InvalidTimelineException`, 메시지에 `dir.resolve("nope.json").toAbsolutePath().normalize()`와 `파일이 없습니다` |
| `rejectsUnreadableJson` (`@ParameterizedTest @ValueSource(strings = {"{", "{\"a\": NaN}", "{} {}"})`) | "JSON으로 읽을 수 없으면 거부한다" | `@TempDir`에 내용 그대로 쓴 `bad.json` | `JSON을 읽을 수 없습니다`, 메시지에 파일 절대 경로 |
| `loadAllReadsConfiguredFiles` | "설정한 폴더의 파일을 읽는다" | dir=`fixturePath().getParent().toString()`, files [valid_v02.json] | 1개, `zoneId` "zone-test" |
| `rejectsDuplicateZone` | "같은 zone_id가 두 번이면 거부한다" | files [valid_v02.json, valid_v02.json] | `zone_id 중복: zone-test` |

### 6.6 `replay/ZonePlayerTest` (단위, `TimelineFixtures.timelineOf(n)`)
| 메서드 | `@DisplayName` | 입력 | 기대 |
|---|---|---|---|
| `snapshotBeforeFirstTick` | "시작 전 상태는 재생 중 t=0이다" | duration 3, loop | `(PLAYING, 0, true, 3)`, `pollStateChange()` 빈 값 |
| `firstTickIsDiscontinuity` | "첫 tick은 t=0이고 불연속이다" | duration 5, loop, tick 1 | t 0, discontinuity true, wrapped false, `frame()`이 `timeline.frames().get(0)`과 같은 객체 |
| `loops` | "끝에서 처음으로 돌아가며 불연속·반복을 표시한다" | duration 3, loop, tick 7 | t [0,1,2,0,1,2,0], discontinuity [T,F,F,T,F,F,T], wrapped [F,F,F,T,F,F,T] |
| `wrapReportsPlaybackOnce` | "반복 상태 변화는 한 번만 준다" | duration 3, loop, tick 4 (각 tick 뒤 poll) | tick 1~3 뒤 빈 값, tick 4 뒤 `(PLAYING, 0, true, 3)`, 바로 다시 poll하면 빈 값 |
| `loopsSingleFrame` | "프레임 1개도 반복한다" | duration 1, loop, tick 3 | t [0,0,0], wrapped [F,T,T] |
| `endsWithoutLoop` | "반복이 꺼져 있으면 마지막 프레임 다음 tick에 끝난다" | duration 3, loop false, tick 5 | 결과 있음 [T,T,T,F,F]. tick 3 뒤 snapshot `(PLAYING, 2, false, 3)`. tick 4 뒤 `(ENDED, 2, false, 3)`, poll `(ENDED, 2, false, 3)`. tick 5 뒤 poll 빈 값 |
| `rejectsEmptyTimeline` | "프레임이 없는 타임라인은 만들 수 없다" | `timelineOf(0)` | `IllegalArgumentException`, `프레임이 없는` |

### 6.7 `replay/ReplaySchedulerTest` (단위, Mockito 5 inline으로 `final` 클래스 mock 가능)
- `@BeforeEach`: `scheduler = new ThreadPoolTaskScheduler(); setPoolSize(1); setThreadNamePrefix("replay-test-"); initialize();`
- `@AfterEach`: `replay.stop(); scheduler.shutdown();`

| 메서드 | `@DisplayName` | 입력 | 기대 |
|---|---|---|---|
| `survivesZoneException` | "구역 하나가 예외를 던져도 다른 구역은 진행한다" | A = `mock(ZonePlayer)`: `tick()`이 `IllegalStateException("시험")`을 던지고 `zoneId()`는 "zone-a". B = `new ZonePlayer(timelineOf(5), true)`. `registry.all()` = [A, B], `tickAll()` 2번 | `assertThatCode`로 예외 없음, `B.snapshot().t()` 1, `verify(A, times(2)).tick()` |
| `ticksOnSchedule` | "설정 간격마다 tick을 반복하고 stop하면 멈춘다" | `TestProperties.replay(20, true)`. mock 플레이어의 `tick()`이 `AtomicInteger` 증가 후 `Optional.empty()`. `start()` | `await().atMost(2s).until(count ≥ 5)`, `isRunning()` true. `stop()` 뒤 `isRunning()` false, `n = count`. `await().pollDelay(200ms).atMost(1s).untilAsserted(count ≤ n + 1)` |

### 6.8 통합 테스트 (실제 데이터 불필요)
- 모든 `@SpringBootTest`는 `properties`로 타임라인을 test 리소스에 돌린다: `crowdsight.timeline-dir=src/test/resources/timeline`, `crowdsight.timeline-files=valid_v02.json`.
- 상대 경로의 기준은 Gradle test 작업 폴더 `server/`이다. `src/test/resources/application.yml`은 만들지 않는다 (계획 4장).
- 웹 환경은 기본 MOCK이라 8080을 열지 않는다. `bootRun`이 떠 있어도 충돌하지 않는다.

| 클래스.메서드 | `@DisplayName` | 설정 | 기대 |
|---|---|---|---|
| `CrowdsightServerApplicationIntegrationTest.contextLoads` (수정) | "스프링 컨텍스트가 오류 없이 뜬다" | 위 2개 properties | 컨텍스트 시작 |
| `CrowdsightServerApplicationIntegrationTest.bindsDefaultReplaySettings` | "application.yml의 재생 기본값을 읽는다" | 같음 | `props.replay().intervalMs()` 1000, `loop()` true |
| `ReplaySchedulerIntegrationTest.loadsFixtureZone` | "설정한 fixture 구역을 등록한다" | + `crowdsight.replay.interval-ms=50` | `registry.all()` 1개, `zoneId` "zone-test", `timeline().source()`가 절대 경로이고 `valid_v02.json`으로 끝남 |
| `ReplaySchedulerIntegrationTest.advancesOnSchedule` | "컨텍스트가 뜨면 재생이 저절로 시작된다" | 같음 | `scheduler.isRunning()` true. `pollInterval(10ms)`로 `snapshot().t()`를 `Set`에 모아 2초 안에 서로 다른 t가 3개 이상 |
| `TimelineStartupIntegrationTest.failsWithAbsolutePathWhenFileMissing` | "타임라인 파일이 없으면 절대 경로를 알리며 시작하지 않는다" | `SpringApplication` + `WebApplicationType.NONE`, 인자 `--crowdsight.timeline-dir=src/test/resources/timeline --crowdsight.timeline-files=nope.json` (`try (var ctx = app.run(args)) {}`) | `rootCause()`가 `InvalidTimelineException`, 메시지에 `Path.of("src/test/resources/timeline/nope.json").toAbsolutePath().normalize()` |
| `TimelineStartupIntegrationTest.failsOnInvalidReplayInterval` | "재생 간격이 0이면 시작하지 않는다" | 위 + `--crowdsight.timeline-files=valid_v02.json --crowdsight.replay.interval-ms=0` | `rootCause()` 메시지에 `crowdsight.replay.interval-ms` (Boot 4 record compact constructor 바인딩 확인, 검증표 26) |

## 7. 이후 PR이 붙일 곳 (S1에서 만들지 않음)
| PR | 붙는 곳 | 내용 |
|---|---|---|
| S2 | `ZoneRegistry`, `ReplayScheduler.tickAll` | `ZoneRuntime(player, grader)`. 레지스트리는 `ZoneRuntime`을 담고, `tick.discontinuity()`면 `grader.reset()`. `CrowdsightProperties.grade` 추가 |
| S3 | `ReplayScheduler` 생성자 | `ZoneBroadcaster`(인터페이스) + `ZoneSessions` 구현. 한 tick 순서 `pollStateChange()` → `playback` → `zone_state` |
| S3 | `ReplaySchedulerConfig` | `poolSize` 2 (ping 30초) |
| S3 | `ZoneRegistry` | `find(zoneId)`. `hello.meta` = `ZoneTimeline.metaJson()`, `hello.playback` = `ZonePlayer.snapshot()` |
| S3 | 설정 | `time-zone`, `ClockConfig`, `ws.*`, `cors-origin-patterns` |
| S4·S5·S6 | 설정 | `instability.*`, `inflow.*`, `alert-log` |
| S7 | `ZonePlayer` | `play()`, `pause()`, `seek(t)`(`pendingDiscontinuity`), `setLoop()`(`loop`가 non-final), `/api/health`에 tick 처리 시간(`System.nanoTime()`) |

## 8. `server_impl_plan.md` 정정 (이 PR의 docs 커밋)
1. 2장 S1: 테스트 표를 "상세는 `docs/plans/server_s1_timeline_replay_plan.md` 6장"으로 바꾼다. `ReplaySchedulerConfig` poolSize를 "S1 1, S3 2"로 고친다. 서버 추가 규칙 목록(4.3절)을 덧붙인다.
2. 4장 yml: `time-zone`에 "(S3)"를 붙인다. `timeline-dir` 주석의 환경변수를 `CROWDSIGHT_TIMELINEDIR`로 바꾼다. 4장 `CrowdsightProperties` 설명에 "`timeline-dir`은 `String`(PathEditor 회피)"을 추가한다.
3. 5장 예외 행: "Spring `ThreadPoolTaskScheduler`는 반복 작업 예외를 로그 후 계속한다(jar 확인). 구역마다 try/catch는 같은 tick의 다른 구역을 지키기 위해서다."
4. 9장 위험에 "`Executor` 빈 → `applicationTaskExecutor` 생략"을 추가한다 (10장).
- api-spec 8절 yml 주석도 같은 환경변수 표기를 쓴다. D1 브랜치 담당이 고칠지는 `[토론]`이다 (11장).

## 9. TDD 단계
공통 (Git Bash):
```bash
export JAVA_HOME="/c/Program Files/Eclipse Adoptium/jdk-21.0.13.9-hotspot"
cd /c/Users/Woori/Desktop/project/Triple-Y/server
```
> **주의: `bootRun`을 띄워 둔 채로 두지 않는다.** 테스트는 `bootRun`이 필요 없다 (MOCK 웹 환경, 포트 미사용). 6단계 수동 확인에서만 포그라운드로 띄우고 Ctrl+C로 끈다. 에이전트는 `bootRun`을 백그라운드로 실행하지 않는다. 남아 있으면 `netstat -ano | findstr :8080`으로 PID를 찾아 `taskkill //PID <pid> //F`(Git Bash) 또는 `taskkill /PID <pid> /F`(PowerShell)로 끈다.

| 단계 | 할 일 (Red → Green) | 명령 | 완료 조건 |
|---|---|---|---|
| 0 | 브랜치 생성 | `git switch feat/server-skeleton && git switch -c feat/server-timeline-replay` | `git status --short`에 `?? CLAUDE.local.md`만 있음 |
| 1 | `CrowdsightPropertiesTest`, `TestProperties` 작성 → `CrowdsightProperties`, yml 4키, `@ConfigurationPropertiesScan` | `./gradlew test --tests 'com.tripley.crowdsight.config.*'` | 4메서드(5회) 통과. `contextLoads` 통과 (아직 타임라인을 읽지 않음) |
| 2 | fixture, `TimelineFixtures`, `TimelineValidatorTest` 작성 (컴파일용 record·예외 껍데기 포함) → `TimelineValidator` | `./gradlew test --tests 'com.tripley.crowdsight.timeline.TimelineValidatorTest'` | 45메서드(52회) 통과 (`parsesMinorLikeSchemaPy` 8회 포함) |
| 3 | `TimelineLoaderTest` → `TimelineLoader` | `./gradlew test --tests 'com.tripley.crowdsight.timeline.*'` | Loader 8메서드(`rejectsUnreadableJson` 3회) 통과 |
| 4 | `ZonePlayerTest` → `PlaybackState`, `PlaybackSnapshot`, `Tick`, `ZonePlayer` | `./gradlew test --tests 'com.tripley.crowdsight.replay.ZonePlayerTest'` | 7메서드 통과 |
| 5 | `ReplaySchedulerTest` → `ZoneRegistry`, `ReplaySchedulerConfig`, `ReplayScheduler`. 통합 테스트 3개 수정·추가 | `./gradlew test` | 모든 테스트 통과. 이 단계에서 `contextLoads`에 properties가 없으면 실패하는 것도 확인한다 (Red) |
| 6 | README 수정. 가짜 타임라인 수동 확인 (선택, py311 있을 때) | 10장 README 명령 | 로그 `타임라인 폴더: C:\Users\Woori\Desktop\project\Triple-Y\data\processed\timeline`, `구역 등록 zone=zone-e04-039 길이=180초 반복=true`, DEBUG `재생 zone=zone-e04-039 t=…`가 1초마다. Ctrl+C 뒤 `netstat -ano \| findstr :8080`이 비어 있음 |
| 6b | 기본 설정 실패 확인 | `./gradlew bootRun` (인자 없음) | 시작 실패, 메시지 `타임라인 파일 오류 [C:\…\data\processed\timeline\E04_039.json]: 파일이 없습니다`. 프로세스가 스스로 끝남 |
| 7 | 전체 검증 | 아래 표 | 모두 기대대로 |

7단계 검증:

| # | 명령 | 기대 |
|---|---|---|
| 1 | `./gradlew clean build` | `BUILD SUCCESSFUL` |
| 2 | `grep -h -o 'tests="[0-9]*" skipped="[0-9]*" failures="[0-9]*" errors="[0-9]*"' build/test-results/test/*.xml` | 모든 줄이 `failures="0" errors="0"` |
| 3 | `grep -rnE 'Instant\.now|currentTimeMillis' src/main` | 출력 없음 |
| 4 | `grep -rnE '@(Data|Getter|Setter|Builder|Value|AllArgsConstructor|NoArgsConstructor)\b' src` | 출력 없음 (Lombok 규칙) |
| 5 | `grep -rn 'com.fasterxml.jackson.databind' src` | 출력 없음 (Jackson 3 규칙) |
| 6 | `grep -rnP '\t' src README.md` | 출력 없음 |
| 7 | stage 뒤 `git -C .. ls-files --eol server \| grep -v 'i/lf'` | `gradle-wrapper.jar`(`-text`), `gradlew.bat`(crlf)만 |
| 8 | `git -C .. status --short` | `CLAUDE.local.md`가 stage되지 않음 |

커밋은 사용자가 요청할 때만 한다. 제안:
1. `feat: 서버 설정 속성과 타임라인 읽기·검증 추가` (config, timeline, fixture, 테스트)
2. `feat: 구역 1초 재생과 스케줄러 추가` (replay, ReplaySchedulerConfig, 통합 테스트)
3. `docs: 서버 README 타임라인 실행법, S1 계획, 구현 계획 정정`

## 10. `server/README.md` 수정
"타임라인 파일 지정과 가짜 타임라인 만드는 법은 S1에서 추가한다." 줄을 지우고, "## IDE" 앞에 아래를 넣는다.
````markdown
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
- DEBUG를 켜면 `재생 zone=zone-e04-039 t=…`가 1초마다 찍힌다.
- 끝낼 때는 Ctrl+C. 8080이 남아 있으면 `netstat -ano | findstr :8080`으로 PID를 찾아 `taskkill /PID <pid> /F`.
- 테스트(`gradlew build`)는 `src/test/resources/timeline/valid_v02.json`을 쓰므로 실제 데이터가 필요 없다.
````

## 11. PR 설명 (초안)
제목: `feat: 타임라인 읽기·검증과 1초 재생 (S1)` / 기준 `feat/server-skeleton` ← `feat/server-timeline-replay` (쌓인 PR)
- S0(#42)을 병합한 뒤 이 PR의 기준이 `main`으로 바뀌었는지 확인한다. 화면 위쪽이 `into main`이어야 한다 (CLAUDE.md).

- 목적: 설정한 타임라인 파일을 서버 시작 때 읽고 검증한다. 틀리면 파일 절대 경로를 알리며 시작을 멈춘다. 구역마다 1초씩 재생한다. 등급·WS는 없고 로그만 남긴다.
- 변경: `CrowdsightProperties`(`timeline-dir`, `timeline-files`, `replay.*`), `@ConfigurationPropertiesScan`, 타임라인 record 7개, `TimelineValidator`(`schema.py`·`validate.ts` 규칙 + 서버 추가 9개), `TimelineLoader`, `ZonePlayer`, `ZoneRegistry`, `ReplayScheduler`(SmartLifecycle), `ReplaySchedulerConfig`, fixture, README 가짜 타임라인, 계획 문서.
- 참고 결정: 결정 기록 6(S1부터 설정), 7(v0.2 검증). 조사 검증표 8·10·11·16·23·24·26.
- 테스트: 단위 6클래스 + 통합 3클래스. 실제 데이터는 필요 없다.

> [!IMPORTANT]
> **CS 이슈**
> | **주제** | **내용** |
> |---|---|
> | **키 없음 vs null** | record로 바꾸면 둘 다 `null`이 된다. v0.2 필수 키 검사는 `JsonNode.has()` 단계에서만 가능하다 |
> | **실수→정수 강제 변환** | Jackson 3 `ACCEPT_FLOAT_AS_INT` 기본 켜짐: `t: 1.5` → 1. `isIntegralNumber()`로 먼저 막는다 |
> | **Fixed-rate 스케줄링** | `scheduleAtFixedRate`는 늦어진 실행을 몰아서 따라잡는다 (fixed-delay와 다름). S1은 수 µs라 영향 없음. S3 전송이 막히면 연속 tick이 생길 수 있다 |
> | **주기 작업의 예외** | 순수 `ScheduledExecutorService`는 예외 한 번에 그 작업을 멈춘다. Spring `ThreadPoolTaskScheduler`는 로그 후 계속한다(jar 확인). 구역 격리용으로 구역마다 try/catch를 둔다 |
> | **Lifecycle phase** | `ReplayScheduler`(MAX)는 스케줄러(1073741823)·웹 서버보다 늦게 시작하고 먼저 멈춘다 |
> | **모니터 락과 가시성** | `ZonePlayer`는 `synchronized`(S3·S7에서 다른 스레드가 읽음), `ReplayScheduler.future`는 `volatile` |
> | **`Executor` 빈의 부작용** | `ThreadPoolTaskScheduler` 빈은 `Executor`라서 Boot가 `applicationTaskExecutor`를 만들지 않는다. 지금은 `@Async`·MVC 비동기가 없어 영향 없음 |
> | **상대 경로와 작업 폴더** | `../data/...`는 실행 위치 기준이다. 시작 로그와 오류에 절대 경로를 남긴다 |
> | **fail-fast** | 잘못된 파일로 반쯤 뜬 서버보다 시작 실패가 낫다. 원인과 경로가 메시지에 남는다 |
> | **불변식** | record compact constructor 검사 + `List.copyOf` 방어 복사 |

| 선택 | 대안 | 고른 이유 |
|---|---|---|
| JsonNode 직접 검증 → record | Bean Validation, JSON Schema 라이브러리 | 키 없음·정수 검사가 필요하다. 의존성을 추가하지 않는다. 규칙과 메시지를 `schema.py`와 한 줄씩 맞출 수 있다 |
| 서버 추가 규칙(정수·1초·문자열) | `schema.py` 그대로 | 서버가 의존하는 값만 넣었다. 생산자 출력은 이미 만족한다 |
| 시작 시 전체 로드 + 시작 실패 | 틀린 파일 건너뛰기, 지연 로드 | 시연 전에 바로 드러난다. 파일 크기가 작다 (180초 × 9셀) |
| 스레드 1개 + 구역 try/catch | 구역마다 스레드 | 판정 상태에 잠금이 필요 없다. 구역 1~3개 |
| `ThreadPoolTaskScheduler` 빈 + `SmartLifecycle` | `@Scheduled(fixedRateString=…)` | 시작·멈춤 순서를 통제한다. 테스트에서 `tickAll()`을 직접 부를 수 있다. S3 ping과 공유한다 |
| `timeline-dir`을 `String`으로 | `Path` | `PathEditor`의 classpath 우선 해석을 피한다 (확인 필요) |
| `ENDED`는 마지막 프레임 다음 tick | 마지막 프레임 tick에서 바로 | 마지막 초도 1초 보인다. `playback(ended)`가 마지막 `zone_state` 뒤에 온다 |
| `time-zone`은 S3로 | S1에 같이 | S1은 벽시계를 쓰지 않는다 |

남은 일:
- S2 `ZoneRuntime`·등급.
- S3 `ZoneBroadcaster`·poolSize 2·`Clock`.
- 환경변수 옛 형식(`CROWDSIGHT_TIMELINE_DIR`) 동작 확인.
- 실제 `E04_039.json`의 위치·이름 확인 (이유노).
- `[토론]`: 11장.

## 12. 위험·가정·`[토론]`
| 위험 | 대응 |
|---|---|
| 서버 추가 규칙이 실제 생산자 파일을 거부 | 6단계에서 가짜 파일로 확인한다. 실제 `run_density`·`run_flow` 결과는 G1(11-13) 때 bootRun으로 확인한다 |
| `PathEditor`·환경변수 옛 형식 동작이 기억과 다름 | `String` 사용으로 회피한다. 환경변수는 README에 기본형만 적는다 (확인 필요) |
| `applicationTaskExecutor`가 사라져 나중에 `@Async`가 재생 스레드를 씀 | 지금 사용처가 없다. 쓰게 되면 `spring.task.execution.mode: force` 또는 전용 실행기를 둔다 |
| 테스트 컨텍스트 2개가 스케줄러를 계속 돌림 | MOCK 환경이고 tick이 가볍다. JVM 종료 때 닫힌다 |
| 통합 테스트가 작업 폴더 `server/`에 의존 | Gradle 기본값이다. IDE에서 돌릴 때 작업 폴더를 `server/`로 둔다 (README) |
| 스케줄 밀림 시 몰아서 재생 | S3에서 전송 제한 2초(결정 1)와 함께 다시 본다 |

가정:
- (가정) 서버가 시작하면 모든 구역이 t=0부터 재생된다. 접속자가 없어도 재생한다 (api-spec 5절: 공용 상태).
- (가정) 첫 tick은 시작 직후이다 (초기 지연 0).
- (가정) 빈 파일은 Jackson 3 `readTree`가 MissingNode를 준다. 그러면 "형식 오류"로 거부된다.
- (가정) `bootRun`·`test`의 작업 폴더는 `server/`이다 (검증표 23). 6단계 로그로 확인한다.

`[토론]`:

| # | 안건 | 누구와 |
|---|---|---|
| 1 | 서버 추가 규칙(정수만, `interval_s` 1, 문자열 `schema_version`)을 `schema.py`·`validate.ts`에도 넣을지 | 이유노, 나예린 |
| 2 | `density` 음수 거부 (지금 세 곳 모두 허용) | 이유노 |
| 3 | api-spec 8절·계획 4장의 환경변수 표기 `CROWDSIGHT_TIMELINE_DIR` → `CROWDSIGHT_TIMELINEDIR` | 조영준 (D1) |
| 4 | 실제 `E04_039.json` 파일 이름·위치와 `fake_` 구분 유지 | 이유노 |

### Critical Files for Implementation
- C:\Users\Woori\Desktop\project\Triple-Y\server\src\main\java\com\tripley\crowdsight\timeline\TimelineValidator.java (new)
- C:\Users\Woori\Desktop\project\Triple-Y\server\src\main\java\com\tripley\crowdsight\timeline\TimelineLoader.java (new)
- C:\Users\Woori\Desktop\project\Triple-Y\server\src\main\java\com\tripley\crowdsight\replay\ZonePlayer.java (new)
- C:\Users\Woori\Desktop\project\Triple-Y\server\src\main\java\com\tripley\crowdsight\replay\ReplayScheduler.java (new)
- C:\Users\Woori\Desktop\project\Triple-Y\server\src\main\java\com\tripley\crowdsight\config\CrowdsightProperties.java (new), with C:\Users\Woori\Desktop\project\Triple-Y\server\src\main\resources\application.yml and C:\Users\Woori\Desktop\project\Triple-Y\server\src\test\resources\timeline\valid_v02.json
