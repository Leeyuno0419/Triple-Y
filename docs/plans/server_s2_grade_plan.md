# 서버 S2 등급 판정 구현 계획 (`feat/server-grade`)

| 항목 | 내용 |
|---|---|
| 작성일 | 2026-11-12 |
| 기준 | `docs/plans/server_impl_plan.md`(결정 기록 1~8, 1.2절, 2장 S2, 4장 `grade.*`, 6장 null), `docs/plans/server_s1_timeline_replay_plan.md`(7장), `origin/feat/api-spec-v02:docs/api-spec.md`(3.2, 4.1~4.2, 8, 10절 #17), `docs/proposal.md` v3.1(3.2), `docs/research/server_research.md`(1.4, 검증표 17~19), `docs/research/server_recheck_2026-11-11.md`(3.1) |
| 대상 | `server/` (S1 #43 `feat/server-timeline-replay` 위에 쌓음), `docs/plans/` |
| 범위 | `crowdsight.grade.*` 설정, 셀 등급, 히스테리시스, 구역 등급·`max_density`, 예측 등급, `ZoneRuntime`(재생+판정 묶음, 불연속 초기화), 재생 로그에 구역 등급. **불안정·유입(S4), 알림(S5), WS(S3) 없음** |
| 상태 | 사용자 점검 완료(11-12), 구현 완료, 리뷰 통과 |

## 0. 확인한 사실 (코드·jar로 확인)
- 작업 트리: 브랜치 `feat/server-timeline-replay`, 최신 커밋 `88bf708`. untracked 파일은 `CLAUDE.local.md` 하나다. 이 파일은 stage하지 않는다.
- S1 코드 상태:
  - `ZoneRegistry.all()`은 `List<ZonePlayer>`를 돌려준다.
  - `ReplayScheduler.tickAll()`은 `player.tick()` → `pollStateChange()` → DEBUG 로그 순서로 돈다. `// S2:` 주석 자리가 있다.
  - `Tick(frame, discontinuity, wrapped)`가 있다. 첫 tick과 반복 직후에 `discontinuity`가 true이다.
- `CrowdsightProperties(timelineDir, timelineFiles, replay)`는 지금 `TestProperties.of(...)` 한 곳에서만 만든다. 쓰는 곳은 `TimelineLoaderTest`와 `ReplaySchedulerTest`다.
- `CellState.density`는 `Double`이다. 검증기가 null을 거부하므로 판정에서 null은 방어용이다. `densityPred60s`는 `Double`이고 null일 수 있다.
- `CellMeta.walkableAreaM2`는 `double`이고 0보다 크다(검증됨).
- `frames[].cells`는 `meta.cells`와 순서·개수가 같다(검증됨).
- `spring-boot-4.1.2.jar`를 javap로 확인했다:
  - `BindException` 메시지는 `"Failed to bind properties under '<이름>' to <타입>"`이다.
  - `Binder.handleBindError`는 이미 `BindException`이면 그대로 다시 던진다. 그래서 메시지에는 **가장 안쪽** 바인딩 이름이 남는다. 예: `crowdsight.grade.density`.
  - 단위 테스트(`Binder`)와 시작 실패 둘 다 `rootCause()`가 우리 `IllegalArgumentException`이 된다.
- fixture `valid_v02.json`의 판정 관련 값:

| t | c-0000 (4.0㎡) 밀도 / 예측 | c-0001 (4.0㎡) | c-0102 (1.5㎡, 대상 아님) |
|---|---|---|---|
| 0 | 1.25 / null | 0 / null | 1.0 / null |
| 1 | 1.5 / 1.8 | 0.5 / 0.6 | 2.0 / 2.1 |
| 2 | 2.0 / 2.5 | 1.0 / 1.1 | 2.0 / 2.2 |
| 3 | 3.2 / 3.6 | 1.0 / 1.2 | 4.0 / 4.4 |
| 4 | 4.2 / 4.6 | 1.5 / 1.6 | 5.5 / 5.9 |

- api-spec 4.2의 규칙:
  - 시작 등급은 정상이다.
  - 올림: 최근 2초 관측이 모두 현재보다 높으면, 그중 낮은 쪽 등급으로 올린다.
  - 내림: 현재보다 낮은 상태가 10초 연속이면 한 단계만 내린다.
  - null 관측은 건너뛴다(유지, 연속을 끊지 않음).
  - 구역 등급은 2㎡ 이상 셀 등급의 최댓값이다. 대상 셀이 없으면 정상이다.
  - 예측 등급에는 히스테리시스가 없다.
  - 반복·이동하면 초기화한다.
- 이 규칙은 proposal v3.1 3.2(3·4·5명/㎡, 2초 올림, 10초 한 단계 내림)와 같다. 재점검 3.1절도 일치한다고 확인했다.
- 계획 2장 S2의 히스테리시스 표는 이번에 손으로 다시 계산했고 모두 맞다 (6.4절 추적표). 조사 검증표 18과도 일치한다.

## 1. 이번 계획에서 정한 것 (계획 대비)
| # | 항목 | 결정 | 이유 |
|---|---|---|---|
| 1 | 설정 바인딩 대상 | `CrowdsightProperties`에 성분 `GradeSettings grade`를 더한다. `grade/` 패키지의 순수 record `GradeSettings`·`DensityThresholds`를 Spring이 **직접** 생성자로 바인딩한다 | 같은 4개 값을 담는 record가 둘(설정용·판정용)이 되지 않는다. `grade/`는 Spring 어노테이션 없이 순수 Java로 남는다. 의존 방향은 config → grade 한 방향이다. S3 `hello.thresholds.density`도 같은 `DensityThresholds`를 쓴다 |
| 2 | 값 검사 위치 | `DensityThresholds`: `0 < caution < alert < critical`. `GradeSettings`: `density` 있음, `up-seconds`·`down-seconds` ≥ 1, `min-walkable-area-m2` ≥ 0. `CrowdsightProperties`: `grade` 있음 | 불변식은 그 값을 가진 record가 지킨다. 키가 빠지면 기본형이 0이 되는데 이 검사가 잡는다. `BindException` 메시지에 키 경로가 남는다 (0장) |
| 3 | `GradeSettings` 성분 | 4개만: `density`, `upSeconds`, `downSeconds`, `minWalkableAreaM2` | 계획 S2에 있던 `pressure`·`instabilitySeconds`는 yml에서 `crowdsight.instability.*` 키다. S4가 별도 record로 더한다 (8장 정정) |
| 4 | S4 자리 성분 (`unstable`, `inflowAlert`, `inflowAvg`) | **넣지 않는다** | 지금 넣으면 항상 false·null인 값을 테스트 없이 들고 다닌다. S4에서 실제 값과 함께 더해도 고칠 곳은 `ZoneGrader`(생성하는 유일한 곳)와 테스트뿐이다. S3는 `inflow_alert`를 S4 전까지 `false`로 보낸다 |
| 5 | `ZoneEvaluation` 성분 | `(int t, Grade zoneGrade, Double maxDensity, List<CellEvaluation> cells)` | 판정 결과만 담는다. `inflow_ratio`·`count` 같은 통과 값은 `Tick.frame()`에 있다 |
| 6 | `ZoneRuntime.tick()` 반환 | `Optional<ZoneStep>`. `record ZoneStep(Tick tick, ZoneEvaluation evaluation)` | S1의 DEBUG 로그(`discontinuity`·`wrapped`)를 유지한다. S3는 `wrapped`(→ playback)와 통과 필드를 꺼내 쓴다 |
| 7 | 히스테리시스 기록 | 셀마다 `ArrayDeque<Grade>`, 최대 `max(up, down)`칸. null은 넣지 않는다. 올린 뒤에는 기록을 비우지 않고, 내린 뒤에는 비운다 | 계획 S2 그대로다. 올림과 내림은 둘 다 최신 관측을 포함하므로 동시에 참일 수 없다 |
| 8 | 현재와 같은 등급의 관측 | 올림 연속도, 내림 연속도 끊는다 | api-spec 4.2 문언("현재보다 높으면/낮은 상태가 연속")을 따른다. `downInterrupted`의 4.0(현재 경계)이 이 경우다 |
| 9 | 셀 ID 검사 | `evaluate`는 셀 수·순서가 meta와 같은지 **갱신 전에** 모두 확인한다. 다르면 `IllegalArgumentException` | 검증기가 이미 보장하는 값이다. 방어용이고, 예외 때 일부 셀만 갱신되는 것을 막는다 |
| 10 | `max_density` | 판정 대상 셀 중 non-null 밀도의 최댓값. 대상이 없거나 모두 null이면 null | api-spec 3.2 |
| 11 | 로그 | tick DEBUG 한 줄에 `grade=`·`max_density=`. 등록 INFO에 `판정 대상 셀=n/m`, 대상이 0개면 WARN | 2㎡ 기준이 셀을 얼마나 빼는지(api-spec 10절 #17)가 시작 로그에 드러난다 |
| 12 | `GradeRule` null | `ofDensity(double)`는 null을 받지 않는다. `ofPrediction(Double)`은 null이면 null | 밀도 null 방어는 `ZoneGrader`가 한다 |
| 13 | 테스트용 설정 | `TestProperties.GRADE` 상수(yml 기본값과 같음). `CrowdsightProperties`는 여전히 `TestProperties.of`에서만 만든다 | S1 결정 9(생성 지점 하나)를 잇는다 |

## 2. 구조와 파일

### 2.1 추가·수정 파일
```text
server/
├─ README.md                                                     수정 (DEBUG 로그 설명 한 줄)
├─ src/main/resources/application.yml                            수정 (crowdsight.grade.*)
├─ src/main/java/com/tripley/crowdsight/
│  ├─ config/  CrowdsightProperties.java                         수정 (grade 성분)
│  ├─ grade/   Grade, DensityThresholds, GradeSettings, GradeRule, GradeHysteresis,
│  │           CellEvaluation, ZoneEvaluation, ZoneGrader        추가 (Spring 의존 없음)
│  └─ replay/  ZoneStep, ZoneRuntime                             추가
│              ZoneRegistry, ReplayScheduler                     수정
└─ src/test/java/com/tripley/crowdsight/
   ├─ CrowdsightServerApplicationIntegrationTest.java            수정 (+1)
   ├─ TimelineStartupIntegrationTest.java                        수정 (+1)
   ├─ config/   CrowdsightPropertiesTest (+5), TestProperties (GRADE)
   ├─ timeline/ TimelineFixtures                                  수정 (timelineWithDensity)
   ├─ grade/    GradeTest, DensityThresholdsTest, GradeRuleTest, GradeHysteresisTest, ZoneGraderTest   추가
   └─ replay/   ZoneRuntimeTest (추가), ReplaySchedulerTest·ReplaySchedulerIntegrationTest (수정)
docs/plans/server_s2_grade_plan.md                               (이 문서)
docs/plans/server_impl_plan.md                                   정정 (8장)
```

### 2.2 1초 흐름 (S2)
```text
ReplayScheduler.tickAll()                       재생 스레드 1개
  └─ for each ZoneRuntime (구역마다 try/catch)
       ZoneRuntime.tick()
         ZonePlayer.tick() → Tick 또는 빈 값(ENDED)
         tick.discontinuity() → ZoneGrader.reset()        (첫 tick·반복, S7 이동)
         ZoneGrader.evaluate(frame) → ZoneEvaluation
         → ZoneStep(tick, evaluation)
       player().pollStateChange() → INFO "재생 상태 …"
       DEBUG "재생 zone= t= discontinuity= wrapped= grade= max_density="
       (S3: [playback?] → zone_state 방송, S5: AlertDetector)
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

# crowdsight.* 설정은 그 값을 읽는 클래스와 같은 PR에서 추가한다 (S3: time-zone·ws·cors, S4: instability·inflow ...)
crowdsight:
  timeline-dir: ../data/processed/timeline   # 작업 폴더(bootRun·test는 server/) 기준. 시작 로그에 절대 경로가 찍힌다
  timeline-files: [E04_039.json]             # 파일당 구역 1개. 가짜는 --crowdsight.timeline-files=fake_E04_039.json
  replay:
    interval-ms: 1000                        # 1초 = 타임라인 1칸 (interval_s 1)
    loop: true                               # 끝에서 처음으로 (E8 30분 반복)
  grade:
    density: { caution: 3.0, alert: 4.0, critical: 5.0 }   # 명/㎡, 이상이면 그 등급 (proposal 3.2)
    up-seconds: 2                            # 최근 2개 관측이 모두 현재보다 높으면 올림 (가정)
    down-seconds: 10                         # 최근 10개 관측이 모두 현재보다 낮으면 한 단계 내림 (가정)
    min-walkable-area-m2: 2.0                # 구역 등급·max_density 판정 대상 셀 (결정 4)
```
- 컴포넌트 이름 `minWalkableAreaM2`는 relaxed binding에서 `min-walkable-area-m2`가 된다. 4단계 `bindsGradeKeys`로 확인한다.

### 3.2 `config/CrowdsightProperties.java` (수정분)
```java
package com.tripley.crowdsight.config;

import java.util.List;

import org.springframework.boot.context.properties.ConfigurationProperties;

import com.tripley.crowdsight.grade.GradeSettings;

/**
 * crowdsight.* 설정 (application.yml). 기준값·시간·경로는 이 record 한 곳에만 둔다.
 * 값 검사는 compact constructor에서 한다 (validation 스타터 안 씀). 틀리면 서버가 시작하지 않는다.
 * grade는 grade 패키지의 record로 바로 묶고, 그 값 검사는 해당 record가 한다.
 * instability·inflow·ws·alert-log·cors-origin-patterns·time-zone은 그 값을 쓰는 PR(S3~S6)에서 추가한다.
 *
 * @param timelineDir   타임라인 폴더. 상대 경로면 작업 폴더(bootRun·test는 server/) 기준
 * @param timelineFiles timelineDir 안의 파일 이름. 1개 이상, 파일당 구역 1개
 * @param replay        재생 설정
 * @param grade         등급 판정 설정 (crowdsight.grade.*)
 */
@ConfigurationProperties("crowdsight")
public record CrowdsightProperties(String timelineDir, List<String> timelineFiles, Replay replay,
                                   GradeSettings grade) {

    public CrowdsightProperties {
        // ... S1 검사 그대로 (timelineDir, timelineFiles, replay) ...
        if (grade == null) {
            throw new IllegalArgumentException("crowdsight.grade 가 없습니다.");
        }
        timelineFiles = List.copyOf(timelineFiles);
    }

    // Replay record는 그대로
}
```

### 3.3 `grade/DensityThresholds.java`, `grade/GradeSettings.java`
```java
package com.tripley.crowdsight.grade;

/**
 * 밀도 등급 기준(명/㎡). 값 이상이면 그 등급이다 (api-spec 4.1). crowdsight.grade.density로 바인딩한다.
 * S3 hello.thresholds.density로도 그대로 보낸다.
 *
 * @param caution  주의 기준
 * @param alert    경계 기준
 * @param critical 심각 기준
 */
public record DensityThresholds(double caution, double alert, double critical) {

    public DensityThresholds {
        if (!(0 < caution && caution < alert && alert < critical)) {   // NaN도 여기서 거부
            throw new IllegalArgumentException("밀도 기준은 0 < caution < alert < critical 이어야 합니다: caution="
                    + caution + ", alert=" + alert + ", critical=" + critical);
        }
    }
}
```
```java
package com.tripley.crowdsight.grade;

/**
 * 등급 판정 설정. crowdsight.grade.*로 바인딩한다 (CrowdsightProperties.grade).
 *
 * @param density           밀도 등급 기준
 * @param upSeconds         올림에 필요한 연속 관측 수 (1 이상)
 * @param downSeconds       한 단계 내림에 필요한 연속 관측 수 (1 이상)
 * @param minWalkableAreaM2 구역 등급·max_density 판정 대상 셀의 최소 보행 면적(㎡, 0 이상). 이상이면 대상
 */
public record GradeSettings(DensityThresholds density, int upSeconds, int downSeconds, double minWalkableAreaM2) {

    public GradeSettings {
        if (density == null) {
            throw new IllegalArgumentException("density(밀도 등급 기준)가 없습니다.");
        }
        if (upSeconds < 1) {
            throw new IllegalArgumentException("up-seconds 는 1 이상이어야 합니다: " + upSeconds);
        }
        if (downSeconds < 1) {
            throw new IllegalArgumentException("down-seconds 는 1 이상이어야 합니다: " + downSeconds);
        }
        if (!(minWalkableAreaM2 >= 0)) {
            throw new IllegalArgumentException("min-walkable-area-m2 는 0 이상이어야 합니다: " + minWalkableAreaM2);
        }
    }
}
```

## 4. 등급 규칙

### 4.1 `grade/Grade.java`
```java
package com.tripley.crowdsight.grade;

/**
 * 위험 등급 (api-spec 4.1, proposal 3.2). 선언 순서가 곧 등급 순서다.
 * compareTo·max·GradeHysteresis가 이 순서에 의존하므로 상수 순서를 바꾸지 않는다.
 * JSON에는 이름(NORMAL 등)으로 나간다 (S3). 화면 표기는 label이다.
 */
public enum Grade {
    NORMAL("정상"),
    CAUTION("주의"),
    ALERT("경계"),
    CRITICAL("심각");

    private static final Grade[] ALL = values();

    private final String label;

    Grade(String label) {
        this.label = label;
    }

    /** 화면 표기 (정상·주의·경계·심각). */
    public String label() {
        return label;
    }

    /** 한 단계 아래 등급. NORMAL은 그대로. */
    public Grade lower() {
        return this == NORMAL ? NORMAL : ALL[ordinal() - 1];
    }

    /** 둘 중 높은 등급. */
    public static Grade max(Grade a, Grade b) {
        return a.compareTo(b) >= 0 ? a : b;
    }
}
```

### 4.2 `grade/GradeRule.java`
```java
package com.tripley.crowdsight.grade;

/** 밀도 → 등급 변환. 상태가 없어 여러 스레드에서 불러도 된다. */
public final class GradeRule {

    private GradeRule() {
    }

    /** 밀도의 조건 등급. 기준값 이상이면 그 등급이다 (3.0 → CAUTION, 2.99 → NORMAL). */
    public static Grade ofDensity(double density, DensityThresholds th) {
        if (density >= th.critical()) {
            return Grade.CRITICAL;
        }
        if (density >= th.alert()) {
            return Grade.ALERT;
        }
        if (density >= th.caution()) {
            return Grade.CAUTION;
        }
        return Grade.NORMAL;
    }

    /** 예측 등급 (grade_pred_60s). 히스테리시스 없이 바로 변환한다. 예측이 null이면 null. */
    public static Grade ofPrediction(Double densityPred60s, DensityThresholds th) {
        return densityPred60s == null ? null : ofDensity(densityPred60s, th);
    }
}
```

### 4.3 `grade/GradeHysteresis.java`
```java
package com.tripley.crowdsight.grade;

import java.util.ArrayDeque;
import java.util.Deque;
import java.util.Iterator;

/**
 * 셀 하나의 등급 히스테리시스 (api-spec 4.2). 시작 등급은 NORMAL.
 * 올림: 최근 upSeconds개 관측이 모두 현재보다 높으면 그중 가장 낮은 등급으로 올린다. 기록은 비우지 않는다.
 * 내림: 최근 downSeconds개 관측이 모두 현재보다 낮으면 한 단계만 내리고 기록을 비운다.
 * null 관측은 세지 않는다. 등급을 유지하고 연속도 끊지 않는다 (결정 기록 4).
 * 올림·내림 조건은 둘 다 최신 관측을 포함하므로 동시에 참일 수 없다.
 * 스레드 규칙: 재생 스레드 하나만 부른다. 잠금 없음.
 */
public final class GradeHysteresis {

    private final int upSeconds;
    private final int downSeconds;
    private final int capacity;
    private final Deque<Grade> recent = new ArrayDeque<>();   // null이 아닌 관측, 마지막이 최신
    private Grade current = Grade.NORMAL;

    public GradeHysteresis(int upSeconds, int downSeconds) {
        if (upSeconds < 1 || downSeconds < 1) {
            throw new IllegalArgumentException(
                    "올림·내림 관측 수는 1 이상이어야 합니다: up=" + upSeconds + ", down=" + downSeconds);
        }
        this.upSeconds = upSeconds;
        this.downSeconds = downSeconds;
        this.capacity = Math.max(upSeconds, downSeconds);
    }

    /** 관측 1개를 반영하고 현재 등급을 돌려준다. observed가 null이면 아무것도 바꾸지 않는다. */
    public Grade update(Grade observed) {
        if (observed == null) {
            return current;
        }
        recent.addLast(observed);
        if (recent.size() > capacity) {
            recent.removeFirst();
        }
        if (recent.size() >= upSeconds) {
            Grade lowest = minOfLast(upSeconds);
            if (lowest.compareTo(current) > 0) {
                current = lowest;
                return current;
            }
        }
        if (recent.size() >= downSeconds && maxOfLast(downSeconds).compareTo(current) < 0) {
            current = current.lower();
            recent.clear();
        }
        return current;
    }

    /** 현재 등급. */
    public Grade current() {
        return current;
    }

    /** NORMAL로 되돌리고 기록을 비운다 (반복·이동). */
    public void reset() {
        current = Grade.NORMAL;
        recent.clear();
    }

    private Grade minOfLast(int n) {
        Grade min = Grade.CRITICAL;
        Iterator<Grade> it = recent.descendingIterator();
        for (int i = 0; i < n; i++) {
            Grade g = it.next();
            if (g.compareTo(min) < 0) {
                min = g;
            }
        }
        return min;
    }

    private Grade maxOfLast(int n) {
        Grade max = Grade.NORMAL;
        Iterator<Grade> it = recent.descendingIterator();
        for (int i = 0; i < n; i++) {
            max = Grade.max(max, it.next());
        }
        return max;
    }
}
```

## 5. 구역 판정과 재생 연결

### 5.1 결과 record (`grade/`)
```java
package com.tripley.crowdsight.grade;

import com.tripley.crowdsight.timeline.CellState;

/**
 * 셀 하나의 한 초 판정 결과.
 *
 * @param cellId       셀 ID
 * @param grade        히스테리시스를 거친 셀 등급. 판정 대상이 아닌 작은 셀도 계산한다 (api-spec 3.2)
 * @param gradePred60s density_pred_60s의 등급 (히스테리시스 없음). 예측이 null이면 null
 * @param eligible     판정 대상(walkable_area_m2 ≥ min-walkable-area-m2)인지. 구역 등급·max_density에만 쓴다
 * @param state        타임라인 셀 값 그대로 (S3 zone_state cells[]로 옮김)
 */
public record CellEvaluation(String cellId, Grade grade, Grade gradePred60s, boolean eligible, CellState state) {
}
```
```java
package com.tripley.crowdsight.grade;

import java.util.List;

/**
 * 구역 1개의 한 초 판정 결과. zone_state(S3)·알림(S5)의 입력이다.
 * 불안정·유입 성분은 S4에서 더한다.
 *
 * @param t          프레임 t
 * @param zoneGrade  판정 대상 셀 등급의 최댓값. 대상 셀이 없으면 NORMAL
 * @param maxDensity 판정 대상 셀 중 null이 아닌 밀도의 최댓값. 없으면 null
 * @param cells      셀별 결과 (meta 순서)
 */
public record ZoneEvaluation(int t, Grade zoneGrade, Double maxDensity, List<CellEvaluation> cells) {

    public ZoneEvaluation {
        cells = List.copyOf(cells);
    }
}
```

### 5.2 `grade/ZoneGrader.java`
```java
package com.tripley.crowdsight.grade;

import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

import com.tripley.crowdsight.timeline.CellMeta;
import com.tripley.crowdsight.timeline.CellState;
import com.tripley.crowdsight.timeline.Frame;

/**
 * 구역 1개의 셀 등급·구역 등급 판정 (api-spec 4.1~4.2). 셀마다 GradeHysteresis를 가진다.
 * 스레드 규칙: evaluate·reset은 재생 스레드 하나만 부른다. 잠금 없음.
 */
public final class ZoneGrader {

    private final List<String> cellIds;
    private final boolean[] eligible;
    private final GradeHysteresis[] hysteresis;
    private final DensityThresholds thresholds;
    private final int eligibleCount;

    /**
     * @param cells    meta.cells (frame.cells와 같은 순서)
     * @param settings 등급 설정
     */
    public ZoneGrader(List<CellMeta> cells, GradeSettings settings) {
        Objects.requireNonNull(cells, "cells");
        Objects.requireNonNull(settings, "settings");
        int n = cells.size();
        this.cellIds = cells.stream().map(CellMeta::cellId).toList();
        this.eligible = new boolean[n];
        this.hysteresis = new GradeHysteresis[n];
        int count = 0;
        for (int i = 0; i < n; i++) {
            eligible[i] = cells.get(i).walkableAreaM2() >= settings.minWalkableAreaM2();
            hysteresis[i] = new GradeHysteresis(settings.upSeconds(), settings.downSeconds());
            if (eligible[i]) {
                count++;
            }
        }
        this.eligibleCount = count;
        this.thresholds = settings.density();
    }

    /** 판정 대상 셀 수 (등록 로그용). */
    public int eligibleCount() {
        return eligibleCount;
    }

    /**
     * 한 프레임을 판정한다. 셀 수·순서가 meta와 다르면 상태를 바꾸지 않고 IllegalArgumentException을 던진다.
     */
    public ZoneEvaluation evaluate(Frame frame) {
        List<CellState> states = frame.cells();
        requireSameCells(frame.t(), states);
        List<CellEvaluation> cells = new ArrayList<>(states.size());
        Grade zoneGrade = Grade.NORMAL;
        Double maxDensity = null;
        for (int i = 0; i < states.size(); i++) {
            CellState state = states.get(i);
            Double density = state.density();
            Grade observed = density == null ? null : GradeRule.ofDensity(density, thresholds);
            Grade grade = hysteresis[i].update(observed);
            if (eligible[i]) {
                zoneGrade = Grade.max(zoneGrade, grade);
                if (density != null && (maxDensity == null || density > maxDensity)) {
                    maxDensity = density;
                }
            }
            Grade predicted = GradeRule.ofPrediction(state.densityPred60s(), thresholds);
            cells.add(new CellEvaluation(state.cellId(), grade, predicted, eligible[i], state));
        }
        return new ZoneEvaluation(frame.t(), zoneGrade, maxDensity, cells);
    }

    /** 모든 셀을 NORMAL로 되돌리고 기록을 비운다 (첫 프레임·반복·이동). */
    public void reset() {
        for (GradeHysteresis h : hysteresis) {
            h.reset();
        }
    }

    private void requireSameCells(int t, List<CellState> states) {
        if (states.size() != cellIds.size()) {
            throw new IllegalArgumentException("t=" + t + ": 셀 수가 meta와 다릅니다: "
                    + states.size() + " != " + cellIds.size());
        }
        for (int i = 0; i < states.size(); i++) {
            if (!cellIds.get(i).equals(states.get(i).cellId())) {
                throw new IllegalArgumentException("t=" + t + ": " + i + "번째 셀이 meta와 다릅니다: "
                        + states.get(i).cellId() + " != " + cellIds.get(i));
            }
        }
    }
}
```

### 5.3 `replay/ZoneStep.java`, `replay/ZoneRuntime.java`
```java
package com.tripley.crowdsight.replay;

import com.tripley.crowdsight.grade.ZoneEvaluation;

/**
 * 구역 1개의 tick 한 번 결과.
 *
 * @param tick       재생 결과. S3가 wrapped(→ playback)와 통과 필드(inflow_ratio·count)에 쓴다
 * @param evaluation 이번 프레임 판정
 */
public record ZoneStep(Tick tick, ZoneEvaluation evaluation) {
}
```
```java
package com.tripley.crowdsight.replay;

import java.util.Objects;
import java.util.Optional;

import com.tripley.crowdsight.grade.ZoneGrader;

/**
 * 구역 1개의 재생기와 판정기를 묶는다. 불연속 tick(첫 프레임·반복·이동)이면 판정 상태를 먼저 초기화한다.
 * 스레드 규칙: tick()은 재생 스레드만 부른다 (ZoneGrader는 잠금 없음).
 * player()가 주는 ZonePlayer는 synchronized라 다른 스레드(S3 hello, S7 제어)에서 써도 된다.
 * S5에서 AlertDetector를 더한다.
 */
public final class ZoneRuntime {

    private final ZonePlayer player;
    private final ZoneGrader grader;

    public ZoneRuntime(ZonePlayer player, ZoneGrader grader) {
        this.player = Objects.requireNonNull(player, "player");
        this.grader = Objects.requireNonNull(grader, "grader");
    }

    /** 구역 ID. */
    public String zoneId() {
        return player.zoneId();
    }

    /** 재생기 (상태 조회·변화 확인용). */
    public ZonePlayer player() {
        return player;
    }

    /** 한 칸 재생하고 판정한다. 재생할 프레임이 없으면(PAUSED·ENDED) 빈 값. */
    public Optional<ZoneStep> tick() {
        return player.tick().map(this::evaluate);
    }

    private ZoneStep evaluate(Tick tick) {
        if (tick.discontinuity()) {
            grader.reset();
        }
        return new ZoneStep(tick, grader.evaluate(tick.frame()));
    }
}
```

### 5.4 `replay/ZoneRegistry.java` (수정)
```java
/**
 * 서버가 재생하는 구역 목록. 생성할 때 타임라인을 모두 읽고, 하나라도 틀리면 예외로 서버 시작을 멈춘다.
 * 목록은 만든 뒤 바뀌지 않으므로 여러 스레드에서 읽어도 된다.
 */
@Slf4j
@Component
public class ZoneRegistry {

    private final List<ZoneRuntime> zones;

    public ZoneRegistry(TimelineLoader loader, CrowdsightProperties props) {
        this.zones = loader.loadAll().stream()
                .map(timeline -> register(timeline, props))
                .toList();
    }

    /** 설정 순서의 모든 구역. */
    public List<ZoneRuntime> all() {
        return zones;
    }

    private static ZoneRuntime register(ZoneTimeline timeline, CrowdsightProperties props) {
        ZoneGrader grader = new ZoneGrader(timeline.meta().cells(), props.grade());
        int cells = timeline.meta().cells().size();
        double minArea = props.grade().minWalkableAreaM2();
        log.info("구역 등록 zone={} 길이={}초 반복={} 판정 대상 셀={}/{} (면적 ≥ {}㎡)", timeline.zoneId(),
                timeline.durationS(), props.replay().loop(), grader.eligibleCount(), cells, minArea);
        if (grader.eligibleCount() == 0) {
            log.warn("판정 대상 셀이 없어 구역 등급은 늘 정상입니다 zone={} (min-walkable-area-m2={})",
                    timeline.zoneId(), minArea);
        }
        return new ZoneRuntime(new ZonePlayer(timeline, props.replay().loop()), grader);
    }
}
```

### 5.5 `replay/ReplayScheduler.java` (`tickAll`과 클래스 Javadoc 마지막 줄만 수정)
```java
 * S2는 판정 결과(구역 등급)를 DEBUG 로그로만 남긴다. S3에서 방송(ZoneBroadcaster)을 붙인다.
```
```java
    /** 모든 구역을 한 칸씩 진행하고 판정한다. 재생 스레드에서만 부른다 (테스트는 직접 부른다). */
    void tickAll() {
        for (ZoneRuntime zone : zones.all()) {
            try {
                Optional<ZoneStep> step = zone.tick();
                zone.player().pollStateChange().ifPresent(s -> log.info("재생 상태 zone={} state={} t={} loop={}",
                        zone.zoneId(), s.state(), s.t(), s.loop()));
                step.ifPresent(s -> log.debug("재생 zone={} t={} discontinuity={} wrapped={} grade={} max_density={}",
                        zone.zoneId(), s.tick().frame().t(), s.tick().discontinuity(), s.tick().wrapped(),
                        s.evaluation().zoneGrade(), s.evaluation().maxDensity()));
                // S3: [playback?] → zone_state 방송
            } catch (RuntimeException e) {
                log.error("구역 재생 중 오류, 다음 구역으로 계속 zone={}", zone.zoneId(), e);
            }
        }
    }
```
- `ZonePlayer`·`Tick` 대신 `ZoneStep`을 쓴다. 같은 패키지라 import는 필요 없다. `Optional` import는 유지한다.
- 줄 길이 120자 이하. DEBUG 줄은 약 116자다. 구현 때 확인한다.

## 6. 테스트

공통 기준값은 `TestProperties.GRADE`: 기준 3/4/5, 올림 2, 내림 10, 최소 면적 2.0. 표기 N=NORMAL, C=CAUTION, A=ALERT, CR=CRITICAL.

### 6.1 테스트 도우미
```java
// config/TestProperties.java
/** 테스트용 CrowdsightProperties·GradeSettings. S3~S6이 성분을 늘리면 여기만 고친다. */
public final class TestProperties {

    /** application.yml crowdsight.grade 기본값과 같다 (bindsDefaultGradeSettings가 확인). */
    public static final GradeSettings GRADE = new GradeSettings(new DensityThresholds(3.0, 4.0, 5.0), 2, 10, 2.0);

    /** 모든 값을 지정해 만든다. 등급 설정은 GRADE. */
    public static CrowdsightProperties of(String timelineDir, List<String> files, long intervalMs, boolean loop) {
        return new CrowdsightProperties(timelineDir, files, new CrowdsightProperties.Replay(intervalMs, loop), GRADE);
    }
    // replay(...)는 그대로
}
```
```java
// timeline/TimelineFixtures.java 추가 (timelineOf와 공통 부분은 private timeline(duration, cells, frameCells)로 뺀다)
/** 4.0㎡ 셀 c-0000 하나에 매 초 같은 밀도를 넣은 타임라인 (판정 시험용). 검증기를 거치지 않는다. */
public static ZoneTimeline timelineWithDensity(int duration, double density) {
    List<CellMeta> cells = List.of(new CellMeta("c-0000", 0, 0, 4.0, List.of()));
    return timeline(duration, cells,
            t -> List.of(new CellState("c-0000", density, null, null, null, null, null, null)));
}
```
`ZoneGraderTest` private 도우미:
- `meta(String id, double area)`: `row`·`col`은 id에서 읽고 `imagePolygon`은 `List.of()`.
- `frame(int t, List<CellMeta> metas, Double[] densities, Double[] preds)`.
- `densities(Double...)`.

`GradeHysteresisTest` 도우미:
- `run(GradeHysteresis h, Double... densities)`: null이면 null 관측, 아니면 `GradeRule.ofDensity(d, GRADE.density())`로 바꿔 `update`. 반환값은 각 초 뒤의 등급 목록.
- `seq(Object... parts)`: `repeat(2.0, 9)` 같은 반복을 펼친다.

### 6.2 `grade/GradeTest`
| 메서드 | `@DisplayName` | 입력 | 기대 |
|---|---|---|---|
| `orderAndLabels` | "등급 순서와 표기는 정상·주의·경계·심각이다" | `Grade.values()` | `[NORMAL, CAUTION, ALERT, CRITICAL]`, label `[정상, 주의, 경계, 심각]` |
| `lowerStepsDownOne` (`@ParameterizedTest @CsvSource`) | "한 단계 아래 등급을 준다 (정상은 그대로)" | CR, A, C, N | A, C, N, N |
| `maxPicksHigher` | "둘 중 높은 등급을 고른다" | (C, A), (A, C), (N, N), (CR, N) | A, A, N, CR |

### 6.3 `grade/DensityThresholdsTest`, `grade/GradeRuleTest`
| 클래스.메서드 | `@DisplayName` | 입력 | 기대 |
|---|---|---|---|
| `DensityThresholdsTest.acceptsOrdered` | "0 < 주의 < 경계 < 심각이면 만든다" | 3.0, 4.0, 5.0 | 예외 없음, 값 그대로 |
| `DensityThresholdsTest.rejectsUnordered` (`@CsvSource` 6개) | "기준 순서가 틀리면 거부한다" | (3,3,5), (3,4,4), (4,3,5), (0,4,5), (−1,4,5), (NaN,4,5) | `IllegalArgumentException`, `caution < alert < critical` |
| `GradeRuleTest.ofDensityUsesInclusiveThresholds` (`@CsvSource` 8개) | "기준값 이상이면 그 등급이다" | 0, 2.99, 3.0, 3.99, 4.0, 4.99, 5.0, 9.9 | N, N, C, C, A, A, CR, CR |
| `GradeRuleTest.ofPredictionMapsValue` | "예측 밀도를 같은 기준으로 바꾼다" | 4.6, 2.99 | A, N |
| `GradeRuleTest.ofPredictionNull` | "예측이 null이면 null이다" | null | null |

### 6.4 `grade/GradeHysteresisTest` (`new GradeHysteresis(2, 10)`)
| 메서드 | `@DisplayName` | 밀도 (t0부터) | 기대 등급 (각 초 뒤) |
|---|---|---|---|
| `startsNormal` | "시작 등급은 정상이다" | 없음 | `current()` N |
| `upAfterTwoSeconds` | "2초 연속 높으면 올린다" | 4.2, 4.5 | N, A |
| `spikeIgnored` | "1초짜리 튐은 무시한다" | 4.5, 2.0, 4.5, 2.0 | N, N, N, N |
| `upToLowerOfStreak` | "2초 중 낮은 쪽 등급으로 올린다" | 4.1, 3.9, 4.1, 4.1 | N, C, C, A |
| `jumpDirectly` | "단계를 건너뛰어 올릴 수 있다" | 5.5, 5.5 | N, CR |
| `upKeepsHistory` | "올린 뒤 기록을 비우지 않아 다음 초에 다시 올릴 수 있다" | 3.5, 4.5, 4.5 | N, C, A |
| `downOneStepPer10s` | "10초 연속 낮으면 한 단계만 내린다" | 4.5, 4.5, 2.0 × 20 | N, A × 10 (t1~t10), C × 10 (t11~t20), N (t21). 22개 |
| `downInterrupted` | "현재와 같은 관측이 내림 연속을 끊는다" | 4.5, 4.5, 2.0 × 9, 4.0 (t11), 2.0 × 10 | N, A × 20 (t1~t20), C (t21). 22개 |
| `criticalStepsDownOnly1` | "심각에서도 10초마다 한 단계씩만 내린다" | 5.5, 5.5, 3.5 × 30 | N, CR × 10 (t1~t10), A × 10 (t11~t20), C × 11 (t21~t31). 32개 |
| `nullSkipped` | "null 관측은 세지 않는다" | 4.5, null, 4.5 | N, N, A |
| `nullKeepsDownStreak` | "null은 내림 연속을 끊지 않는다" | 4.5, 4.5, 2.0 × 5, null, 2.0 × 5 | N, A × 11 (t1~t11), C (t12). 13개 |
| `nullOnlyKeepsGrade` | "null만 이어지면 등급을 유지한다" | 4.5, 4.5, null × 20 | N, A × 21 |
| `resetClears` | "초기화하면 정상으로 돌아가고 기록을 비운다" | 4.5, 4.5, `reset()`, 4.5 | reset 직후 `current()` N, 마지막 N |
| `rejectsNonPositiveSeconds` (`@CsvSource` (0,10), (2,0)) | "관측 수가 1보다 작으면 거부한다" | 생성자 | `IllegalArgumentException`, `1 이상` |

손 계산 추적 (기록 최대 10칸, 왼쪽이 오래된 것):

`downInterrupted` (4.0은 A, 2.0은 N)

| t | 밀도 | 관측 | 기록 (최근 10) | 올림 검사 (최근 2 최솟값 > 현재) | 내림 검사 (최근 10 최댓값 < 현재) | 결과 |
|---|---|---|---|---|---|---|
| 0 | 4.5 | A | [A] | 1개 < 2 | 1개 < 10 | N |
| 1 | 4.5 | A | [A, A] | min A > N → **올림** | — | **A** |
| 2 | 2.0 | N | [A, A, N] | min N ≤ A | 3개 | A |
| 3~9 | 2.0 | N | t9: [A, A, N×8] (10칸) | min N | t9: max A, 낮지 않음 | A |
| 10 | 2.0 | N | t0이 빠짐 → [A(t1), N×9] | min N | max A, 낮지 않음 | A |
| 11 | 4.0 | A | [N×9(t2~t10), A] | min N | max A, 낮지 않음 (같은 등급이라 연속이 끊김) | A |
| 12~19 | 2.0 | N | t19: [N(t10), A(t11), N×8] | min N | max A | A |
| 20 | 2.0 | N | [A(t11), N×9] | min N | max A | **A** (기대 t20 A) |
| 21 | 2.0 | N | [N×10(t12~t21)] | min N | max N < A → **내림**, 기록 비움 | **C** (기대 t21 C) |

`criticalStepsDownOnly1` (5.5는 CR, 3.5는 C)

| t | 밀도 | 관측 | 기록 | 올림 | 내림 | 결과 |
|---|---|---|---|---|---|---|
| 0 | 5.5 | CR | [CR] | 1개 | 1개 | N |
| 1 | 5.5 | CR | [CR, CR] | min CR > N → **올림** | — | **CR** |
| 2~9 | 3.5 | C | t9: [CR, CR, C×8] | min C ≤ CR | t9: max CR | CR |
| 10 | 3.5 | C | [CR(t1), C×9] | min C | max CR, 낮지 않음 | CR |
| 11 | 3.5 | C | [C×10(t2~t11)] | min C | max C < CR → **내림**, 비움 | **A** (기대 t11 A) |
| 12~20 | 3.5 | C | 1~9칸 | min C ≤ A | 10칸 미만 | A |
| 21 | 3.5 | C | [C×10(t12~t21)] | min C | max C < A → **내림**, 비움 | **C** (기대 t21 C) |
| 22~31 | 3.5 | C | t31: [C×10(t22~t31)] | min C ≤ C | max C, 낮지 않음 | **C** (기대 t31 C) |

- 기록을 비우지 않는다면 t12에서 최근 10칸(t3~t12)이 모두 C < A이므로 바로 C로 한 번 더 내려간다. 이 테스트는 "내림 뒤 기록 비움"을 고정한다.

`downOneStepPer10s`:
- t1에 A로 오른다.
- t10: 최근 10칸 t1~t10 = [A, N×9]. 최댓값이 A라 A 유지.
- t11: t2~t11 = N×10 → C, 기록 비움.
- t20: 기록 9칸(t12~t20) → C 유지.
- t21: t12~t21 = N×10 → N.

`nullKeepsDownStreak`:
- t1에 A로 오른다.
- t2~t6에 N 관측 5개.
- t7은 null. 기록 그대로, A 유지.
- t8~t11에 N이 들어와 모두 9개. A 유지.
- t12: 10번째 N. 최근 10칸 = t2~t6, t8~t12 → C.

### 6.5 `config/CrowdsightPropertiesTest` (수정, `Binder`)
`defaults()`에 다음 키를 더한다:
- `crowdsight.grade.density.caution`=3.0, `.alert`=4.0, `.critical`=5.0
- `crowdsight.grade.up-seconds`=2, `down-seconds`=10, `min-walkable-area-m2`=2.0

| 메서드 | `@DisplayName` | 입력 | 기대 |
|---|---|---|---|
| (S1 4개) | 그대로 | 기본 맵에 grade 키 포함 | 그대로 통과 |
| `bindsGradeKeys` | "grade 키를 등급 설정 record로 묶는다" | 기본 맵 | `props.grade()` == `TestProperties.GRADE` |
| `rejectsUnorderedDensity` (`@CsvSource({"alert,3.0", "critical,4.0"})`) | "밀도 기준 순서가 틀리면 바인딩에서 거부한다" | `crowdsight.grade.density.{key}`=값 | `BindException`. 메시지에 `crowdsight.grade.density`, `rootCause()` 메시지에 `caution < alert < critical` |
| `rejectsNonPositiveGradeSeconds` (`@ValueSource(strings = {"up-seconds", "down-seconds"})`) | "올림·내림 초가 0이면 거부한다" | `crowdsight.grade.{key}`=0 | `BindException`, 원인 메시지에 key |
| `bindsZeroMinWalkableArea` | "최소 면적 0이면 모든 셀이 대상이 되도록 바인딩된다" | `min-walkable-area-m2`=0 | 거부 없음, `props.grade().minWalkableAreaM2()` == 0.0 |
| `rejectsNegativeMinWalkableArea` | "최소 면적이 음수면 거부한다" | `min-walkable-area-m2`=−0.1 | 원인 메시지 `min-walkable-area-m2` |
| `rejectsMissingGrade` | "grade 설정이 없으면 거부한다" | grade 키 6개 제거 | 원인 메시지 `crowdsight.grade` (중첩 record가 null로 묶임, 4단계에서 확인) |

### 6.6 `grade/ZoneGraderTest`
기본 meta는 fixture와 같다: `c-0000`(4.0), `c-0001`(4.0), `c-0102`(1.5). 예측은 따로 적지 않으면 null.

| 메서드 | `@DisplayName` | 입력 | 기대 |
|---|---|---|---|
| `smallCellExcluded` | "2㎡ 미만 셀은 자기 등급만 내고 구역 등급에서 빠진다" | t0 [3.2, 1.0, 6.0], t1 [3.4, 1.0, 6.0] | `eligibleCount()` 2. t0: 셀 [N, N, N], 구역 N, max 3.2. t1: 셀 [C, N, CR], eligible [T, T, F], 구역 C, max 3.4 |
| `areaBoundaryIncluded` | "면적이 정확히 2㎡인 셀은 판정 대상이다" | meta [c-0000 2.0, c-0001 1.99], t0·t1 [4.5, 5.5] | t1 셀 [A, CR], eligible [T, F], 구역 A, max 4.5 |
| `noEligibleCells` | "판정 대상 셀이 없으면 구역은 정상, 최대 밀도는 null이다" | meta [c-0000 1.5, c-0001 1.5], t0·t1 [4.5, 4.5] | `eligibleCount()` 0. t1 셀 [A, A], 구역 N, max null |
| `predictionNoHysteresis` | "예측 등급은 히스테리시스 없이 바로 바뀐다" | t0 밀도 [1.0, 1.0, 1.0], 예측 [4.6, 2.99, 5.0] | `gradePred60s` [A, N, CR], `grade` [N, N, N] |
| `predictionNull` | "예측이 null이면 예측 등급도 null이다" | t0 예측 [null, 1.0, null] | [null, N, null] |
| `orderPreserved` | "셀 결과는 meta 순서이고 원래 값을 그대로 담는다" | meta [c-0102 1.5, c-0000 4.0, c-0001 4.0], t=7 프레임 [1, 1, 1] | `t()` 7. cellId [c-0102, c-0000, c-0001], eligible [F, T, T]. 각 `state()`가 `frame.cells().get(i)`와 같은 객체 (`isSameAs`) |
| `nullDensitySkipped` | "밀도 null은 등급을 유지하고 최대 밀도에서 뺀다" | meta [c-0000 4.0], 4.5, null, 4.5 | 셀·구역 [N, N, A], max [4.5, null, 4.5] |
| `resetRestartsHysteresis` | "초기화하면 셀 등급이 처음부터 다시 쌓인다" | meta [c-0000 4.0], 4.5, 4.5, `reset()`, 4.5 | 둘째 초 A, reset 뒤 셀·구역 N |
| `rejectsMismatchedCells` | "셀 수나 순서가 meta와 다르면 거부한다" | ① 셀 2개 프레임 ② [c-0000, c-0102, c-0001] | 둘 다 `IllegalArgumentException`, `셀`. ① 뒤 정상 프레임 4.5를 넣으면 셀 등급 N (갱신 안 됨) |
| `gradesFixtureTimeline` | "fixture 5초를 판정한다" | `new TimelineLoader(MAPPER, TestProperties.of(fixturePath().getParent().toString(), List.of("valid_v02.json"), 1000, true)).loadAll().get(0)`, t0~t4 | 구역 [N, N, N, N, C]. max [1.25, 1.5, 2.0, 3.2, 4.2]. t3 셀 [N, N, N], t4 셀 [C, N, A]. 예측 t0 [null×3], t3 [C, N, A], t4 [A, N, CR] |

`gradesFixtureTimeline` 손 계산:
- c-0000 관측 N, N, N, C(3.2), A(4.2).
  - t3: 최근 2 = [N, C], 최솟값 N → N 유지.
  - t4: 최근 2 = [C, A], 최솟값 C > N → **C**.
- c-0102 관측 N, N, N, A(4.0), CR(5.5).
  - t3: N 유지.
  - t4: 최근 2 = [A, CR], 최솟값 A → **A**. 판정 대상이 아니라 구역 등급에 안 들어감.
- c-0001 관측은 모두 N.
- 구역 t4 = max(C, N) = **C**.
- `max_density`는 대상 셀(c-0000, c-0001) 중 최댓값. t0 = max(1.25, 0) = 1.25.

### 6.7 `replay/ZoneRuntimeTest`
| 메서드 | `@DisplayName` | 입력 | 기대 |
|---|---|---|---|
| `resetOnWrap` | "반복으로 처음에 돌아오면 판정을 초기화한다" | `timelineWithDensity(3, 4.5)`, loop, `tick()` 5번 | t [0, 1, 2, 0, 1], discontinuity [T, F, F, T, F], 구역 등급 [N, A, A, N, A] |
| `emptyAfterEnd` | "끝난 구역은 판정 결과가 없다" | `timelineWithDensity(1, 4.5)`, loop false, `tick()` 2번 | 첫 번째: 결과 있음, t 0, 등급 N. 두 번째: 빈 값 |

### 6.8 `replay/ReplaySchedulerTest` (수정)
- 도우미는 `new ZoneRuntime(p, new ZoneGrader(List.of(), TestProperties.GRADE))`로 단순하게 만든다. mock 플레이어에는 timeline이 없고, `timelineOf`의 셀이 비어 있으므로 맞는다.

| 메서드 | 바뀌는 것 | 기대 |
|---|---|---|
| `survivesZoneException` | A = `runtime(mock 플레이어, tick이 예외)`, B = `runtime(new ZonePlayer(timelineOf(5), true))`. `registry.all()` = [A, B] | S1과 같다. `B.player().snapshot().t()` 1 |
| `ticksOnSchedule` | mock 플레이어를 `runtime(...)`으로 감싼다 | S1과 같다 |

### 6.9 통합 테스트 (수정·추가)
| 클래스.메서드 | `@DisplayName` | 설정 | 기대 |
|---|---|---|---|
| `ReplaySchedulerIntegrationTest.loadsFixtureZone`·`advancesOnSchedule` (수정) | 그대로 | 그대로 | `registry.all().get(0).player()`로 바꾼다 |
| `CrowdsightServerApplicationIntegrationTest.bindsDefaultGradeSettings` (추가) | "application.yml의 등급 기본값을 읽는다" | 기존 properties | `props.grade()` == `TestProperties.GRADE` |
| `TimelineStartupIntegrationTest.failsOnUnorderedDensityThresholds` (추가) | "밀도 기준 순서가 틀리면 시작하지 않는다" | `--crowdsight.timeline-dir=src/test/resources/timeline --crowdsight.timeline-files=valid_v02.json --crowdsight.grade.density.alert=3.0` | `rootCause()` 메시지에 `caution < alert < critical` |

## 7. 이후 PR이 붙일 곳 (S2에서 만들지 않음)
| PR | 붙는 곳 | 내용 |
|---|---|---|
| S3 | `ReplayScheduler.tickAll` | `ZoneStep`에서 `tick().wrapped()` → playback, `tick().frame()`의 `inflow_ratio`·`count` + `evaluation()` → `zone_state`. `inflow_alert`는 `false` |
| S3 | `ZoneRegistry` | `find(zoneId)`. `hello.playback` = `runtime.player().snapshot()`, `hello.thresholds.density` = `props.grade().density()` |
| S4 | `ZoneGrader` 생성자, `CellEvaluation`, `ZoneEvaluation` | `CrowdsightProperties.instability`(별도 record) → `InstabilityTracker`. 관측 = `max(ofDensity, unstable ? CRITICAL : NORMAL)`. `CellEvaluation.unstable`, `ZoneEvaluation`에 `inflowAvg`·`inflowAlert` 추가 |
| S5 | `ZoneRuntime` | `AlertDetector` 보유, 불연속이면 `reset()`, `ZoneStep`에 알림 목록 |
| S7 | `ZonePlayer.seek` | `pendingDiscontinuity`. 그러면 `ZoneRuntime`이 그대로 판정을 초기화한다 |

## 8. `server_impl_plan.md` 정정 (이 PR의 docs 커밋)
1. 1.1절 패키지: `grade/`에 `DensityThresholds`, `replay/`에 `ZoneStep`.
2. 1.2절 흐름: "`ZoneRuntime.tick()` → `ZoneStep(tick, evaluation)`. discontinuity면 `ZoneGrader.reset()`(S5부터 `AlertDetector.reset()`도)".
3. 2장 S2 코드 블록:
   - `GradeSettings(DensityThresholds density, int upSeconds, int downSeconds, double minWalkableAreaM2)`. `pressure`·`instabilitySeconds`를 빼고 "S4가 `crowdsight.instability.*` 별도 record로 추가".
   - "`CrowdsightProperties.grade`는 `GradeSettings`를 직접 바인딩, 검사는 `DensityThresholds`(0 < caution < alert < critical)·`GradeSettings`(초 ≥ 1, 면적 ≥ 0)".
   - `CellEvaluation`에서 `unstable`을 뺀다 (S4).
   - `ZoneEvaluation(int t, Grade zoneGrade, Double maxDensity, List<CellEvaluation> cells)`. `inflowRatio`·`count`는 S3가 `Tick.frame()`에서 읽고, `inflowAlert`·`inflowAvg`는 S4에서 더한다.
   - `ZoneRuntime`·`ZoneStep` 시그니처 추가.
   - "올림·내림은 동시에 참일 수 없다", "같은 등급 관측은 두 연속을 모두 끊는다", "`evaluate`는 셀 ID를 갱신 전에 검사".
   - 테스트 표 뒤에 "상세는 `docs/plans/server_s2_grade_plan.md` 6장". 표의 기대값은 고칠 것이 없다.
4. 2장 S4: "`ZoneGrader` 생성자에 불안정 설정 추가, `CellEvaluation.unstable`·`ZoneEvaluation.inflowAvg`·`inflowAlert` 추가".
5. 4장 `CrowdsightProperties` 설명: "`caution < alert < critical`" 검사를 "`DensityThresholds`(0 < caution < alert < critical)"로.
6. 6장 null 표 `density` 행: "`max_density` 계산에서도 뺀다".

## 9. TDD 단계
공통 (Git Bash, `server/`):
```bash
cd /c/Users/Woori/Desktop/project/Triple-Y/server
JAVA_HOME="/c/Program Files/Eclipse Adoptium/jdk-21.0.13.9-hotspot" ./gradlew test --tests '<패턴>' --no-daemon
```
> **에이전트는 `bootRun`을 실행하지 않는다** (포그라운드·백그라운드 모두). 모든 확인은 `test`·`build`로 한다. 테스트는 MOCK 웹 환경이라 포트를 쓰지 않는다.

각 단계의 Red는 "테스트 먼저 작성 → 컴파일 실패 또는 단언 실패 확인"이다.

| 단계 | 할 일 (Red → Green) | `--tests` | 완료 조건 |
|---|---|---|---|
| 0 | 브랜치 생성: `git switch feat/server-timeline-replay && git switch -c feat/server-grade` | — | `git status --short`에 `?? CLAUDE.local.md`만 있음 |
| 1 | `GradeTest` → `Grade` | `'com.tripley.crowdsight.grade.GradeTest'` | 3메서드(6회) 통과 |
| 2 | `DensityThresholdsTest`, `GradeRuleTest` → `DensityThresholds`, `GradeRule` | `'com.tripley.crowdsight.grade.*'` | 누적 8메서드(23회) 통과 |
| 3 | `GradeHysteresisTest` → `GradeHysteresis` | `'com.tripley.crowdsight.grade.GradeHysteresisTest'` | 14메서드(15회) 통과. `downInterrupted`·`criticalStepsDownOnly1` 리스트가 6.4절 표와 같음 |
| 4 | `CrowdsightPropertiesTest` 수정·추가 → `GradeSettings`, `CrowdsightProperties.grade`, yml `grade`, `TestProperties.GRADE`. `bindsDefaultGradeSettings` 추가 | `'com.tripley.crowdsight.config.*'` 다음 `'com.tripley.crowdsight.CrowdsightServerApplicationIntegrationTest'` | config 10메서드(13회) 통과. 통합 3메서드 통과 |
| 5 | `ZoneGraderTest` → `CellEvaluation`, `ZoneEvaluation`, `ZoneGrader` | `'com.tripley.crowdsight.grade.ZoneGraderTest'` | 10메서드 통과 |
| 6 | `TimelineFixtures.timelineWithDensity`, `ZoneRuntimeTest` → `ZoneStep`, `ZoneRuntime` | `'com.tripley.crowdsight.replay.ZoneRuntimeTest'` | 2메서드 통과 |
| 7 | `ReplaySchedulerTest`·`ReplaySchedulerIntegrationTest` 수정, `failsOnUnorderedDensityThresholds` 추가 → `ZoneRegistry`, `ReplayScheduler` 수정 | 없음 (`./gradlew test --no-daemon`) | 모든 테스트 통과 |
| 8 | README DEBUG 줄을 "DEBUG를 켜면 `재생 zone=zone-e04-039 t=… grade=… max_density=…`가 1초마다 찍힌다. 시작 로그 `판정 대상 셀=n/m`으로 2㎡ 기준에 빠진 셀 수를 확인한다."로 고친다 | — | 문구만 |
| 9 | 전체 검증 (아래 표) | — | 모두 기대대로 |

9단계 검증:

| # | 명령 | 기대 |
|---|---|---|
| 1 | `JAVA_HOME=… ./gradlew clean build --no-daemon` | `BUILD SUCCESSFUL` |
| 2 | `grep -h -o 'tests="[0-9]*" skipped="[0-9]*" failures="[0-9]*" errors="[0-9]*"' build/test-results/test/*.xml` | 모든 줄이 `failures="0" errors="0"` |
| 3 | `grep -rn 'springframework' src/main/java/com/tripley/crowdsight/grade` | 출력 없음 |
| 4 | `grep -rnE 'Instant\.now\|currentTimeMillis' src/main` | 출력 없음 |
| 5 | `grep -rnE '@(Data\|Getter\|Setter\|Builder\|Value\|AllArgsConstructor\|NoArgsConstructor)\b' src` | 출력 없음 |
| 6 | `grep -rn 'com.fasterxml.jackson.databind' src` | 출력 없음 |
| 7 | `grep -rnP '\t' src README.md` | 출력 없음 |
| 8 | 바뀐 `.java` 파일에 120자 초과 줄 없음 (문자 수 기준) | 출력 없음 |
| 9 | stage 뒤 `git -C .. ls-files --eol server \| grep -v 'i/lf'` | `gradle-wrapper.jar`, `gradlew.bat`만 |
| 10 | `git -C .. status --short` | `CLAUDE.local.md`가 stage되지 않음 |

커밋 제안:
1. `feat: 등급·밀도 기준·히스테리시스 추가` (`Grade`, `DensityThresholds`, `GradeRule`, `GradeHysteresis` + 테스트)
2. `feat: 등급 설정과 구역 판정을 재생에 연결 (S2)` (`GradeSettings`, 설정, yml, `ZoneGrader`, `ZoneRuntime`, 레지스트리·스케줄러, 테스트)
3. `docs: S2 계획 추가, 구현 계획 정정, README 로그 설명`

## 10. PR 설명 (초안)
제목: `feat: 셀·구역 등급 판정과 히스테리시스 (S2)` / 기준 `feat/server-timeline-replay` ← `feat/server-grade` (쌓인 PR)

> **병합 순서**: S0(#42) → S1(#43) → 이 PR. 앞 PR이 병합되면 이 PR의 기준이 `main`으로 바뀌었는지 확인한다. 화면 위쪽이 `into main`이어야 한다 (CLAUDE.md). 바뀌지 않았으면 Edit에서 base를 `main`으로 고친 뒤 병합한다.

- 목적: 1초마다 셀 밀도로 등급을 정하고(정상·주의·경계·심각), 깜빡이지 않게 히스테리시스를 건다. 2㎡ 이상 셀로 구역 등급과 최대 밀도를 낸다. 예측 등급도 계산한다. 반복 재생 때 초기화한다. WS·알림 없이 DEBUG 로그만 남긴다.
- 변경:
  - `crowdsight.grade.*` (밀도 3/4/5, 올림 2, 내림 10, 최소 면적 2.0)
  - `grade/`: `Grade`, `DensityThresholds`, `GradeSettings`, `GradeRule`, `GradeHysteresis`, `CellEvaluation`, `ZoneEvaluation`, `ZoneGrader`
  - `replay/`: `ZoneRuntime`, `ZoneStep`. `ZoneRegistry`·`ReplayScheduler`가 `ZoneRuntime`을 쓴다
  - 등록 로그에 판정 대상 셀 수
- 참고 결정: 결정 4(2㎡ 이상 셀 최댓값), 결정 기록 4(null 관측 건너뜀), api-spec 4.1~4.2, proposal 3.2. 조사 검증표 17~19.

> [!IMPORTANT]
> **CS 이슈**
> | **주제** | **내용** |
> |---|---|
> | **히스테리시스 (Schmitt trigger)** | 올림 2초와 내림 10초 한 단계로 조건을 비대칭으로 둔다. 기준값 근처에서 등급이 깜빡이는 것(chattering)을 막는다. 대가는 올림 +1초, 내림 최대 10초/단계의 지연이다 |
> | **슬라이딩 윈도** | 셀마다 `ArrayDeque` 최대 10칸. 검사는 O(n), n ≤ 10. 30분 반복해도 메모리가 늘지 않는다 |
> | **올림·내림 상호 배타** | 두 조건 모두 최신 관측을 포함한다. 검사 순서는 결과를 바꾸지 않는다 |
> | **enum 순서 = 의미** | `compareTo`는 ordinal 기준. 상수 순서를 바꾸면 판정이 바뀐다. `GradeTest.orderAndLabels`가 순서를 고정한다 |
> | **부동소수점 경계** | `>=` 비교. 3.0·4.0·5.0·2.0은 이진수로 정확하다. 계산된 면적 1.9999…㎡는 대상에서 빠진다 |
> | **null 의미** | 건너뜀(등급·연속 유지)과 초기화는 다르다. 결정 기록 4에 따라 건너뛴다. `max_density`에서도 뺀다 |
> | **스레드 한정 (thread confinement)** | 판정 상태는 재생 스레드 하나만 만져서 잠금이 없다. 다른 스레드가 보는 `ZonePlayer`만 `synchronized` |
> | **원자적 갱신** | 셀 ID 검사를 상태 갱신 전에 끝낸다. 예외 때 반쪽 상태가 남지 않는다 |
> | **생성자 바인딩과 불변식** | record compact constructor에서 검사. 잘못된 설정은 `BindException`으로 시작 실패. 메시지에 가장 안쪽 키 경로 (jar 확인) |
> | **순수 도메인 계층** | `grade/`는 Spring에 의존하지 않는다. 의존 방향은 config → grade 한 방향 |

| 선택 | 대안 | 고른 이유 |
|---|---|---|
| `GradeSettings`·`DensityThresholds`를 설정이 직접 바인딩 | 중첩 record + 판정용 record로 변환 | 같은 값의 record가 둘이 되지 않는다. S3 `hello.thresholds`도 같은 타입 |
| S4 성분은 S4에서 추가 | 지금 false·null로 미리 둠 | 테스트 없는 죽은 성분을 만들지 않는다 |
| `ZoneStep(Tick, ZoneEvaluation)` 반환 | `ZoneEvaluation`에 `Frame`·`wrapped` 포함 | 판정 결과와 재생 결과의 역할을 나눈다 |
| 관측 기록 deque | 연속 횟수 카운터 2개 | "그중 가장 낮은 등급" 계산이 단순하다. 10칸이라 비용 없음 |
| 올림은 최근 2개 중 최솟값으로 | 한 단계씩 올림 | api-spec 4.2·proposal 3.2. 심각을 1초 만에 반영 |
| 내림 뒤 기록 비움, 올림 뒤 유지 | 둘 다 비움 / 둘 다 유지 | 내림은 "10초마다 한 단계" 보장. 올림은 명세 문언과 같고 빠르게 반영 |
| 같은 등급 관측이 내림 연속을 끊음 | 같거나 낮으면 셈 | 명세 "현재보다 낮은 상태가 10초 연속" (가정) |
| 셀 ID 불일치 시 예외 | 무시하고 인덱스로 판정 | 검증기를 우회한 입력을 조용히 넘기지 않는다 |
| 구역 등급 변화는 DEBUG만 | INFO로 등급 변화 로그 | 범위를 지킨다. 등급 변화 알림은 S5 |

리뷰 요청: 히스테리시스 규칙 해석 3가지(올림 뒤 기록 유지, 같은 등급이 연속을 끊음, null 건너뜀), 설정 record를 `grade/`에 둔 구조.

남은 일: S3(`ZoneStep` → `zone_state`·`playback`, `hello.thresholds`), S4(불안정 → 심각, 유입 성분), S5(알림·초기화), 실제 E04_039 셀 면적 확인(이유노), `[토론]` 11장.

## 11. 위험·가정·`[토론]`
| 위험 | 대응 |
|---|---|
| 다른 패키지의 중첩 record 바인딩이 기대와 다름 (키 이름 `min-walkable-area-m2`, grade 키가 없을 때 null) | 4단계 `bindsGradeKeys`·`rejectsMissingGrade`로 먼저 확인. 실패하면 `CrowdsightProperties` 안에 중첩 record를 두고 변환하는 방식으로 바꾼다 |
| 계산된 면적이 2.0 바로 아래(1.9999…)라 셀이 의도와 달리 빠짐 | 등록 로그 `판정 대상 셀=n/m`. 실제 meta 값을 이유노와 확인 |
| enum 상수 순서 변경으로 판정이 바뀜 | Javadoc 경고 + `GradeTest.orderAndLabels` |
| 가짜 E04_039에서 가장 붐비는 왼쪽 열(1.0~1.2㎡)이 빠져 구역 등급이 낮게 나옴 (api-spec 10절 #17) | 결정 4 유지, 로그로 드러냄. 대상 셀 0개면 WARN |
| E8에 히스테리시스 지연(+1초) 포함 여부 | 계획 9장 토론 4. 이번 PR은 동작만 고정 |
| `ReplaySchedulerTest` mock이 `ZoneRuntime`을 거치며 깨짐 | 실제 `ZoneRuntime`에 mock 플레이어를 감싸 S1 의미 유지 |

가정:
- (가정) 셀 시작 등급은 NORMAL. 첫 tick도 불연속이라 `reset()`이 불리지만 결과는 같다.
- (가정) 현재와 같은 등급의 관측은 올림·내림 연속을 모두 끊는다.
- (가정) 올린 뒤에는 기록 유지, 내린 뒤에는 비움.
- (가정) `min-walkable-area-m2` 0은 허용 (모든 셀이 대상). `caution`은 0보다 커야 한다.
- (가정) 판정 대상이 아닌 셀도 자기 `grade`·`grade_pred_60s`를 계산해 S3 `cells[]`로 보낸다 (api-spec 3.2).

`[토론]`:

| # | 안건 | 누구와 |
|---|---|---|
| 1 | 2㎡ 기준이 실제 E04_039에서 빼는 셀 수와 면적 반올림(1.9999…) 처리 | 이유노 |
| 2 | 현재와 같은 등급 관측이 내림 연속을 끊는 해석을 api-spec 4.2에 한 줄로 적을지 | 조영준 (D1) |
| 3 | 화면이 판정 대상이 아닌 작은 셀을 구분해 표시할지 (`eligible`은 지금 API에 없음) | 나예린 |
| 4 | 화면 표기 "경고" → "경계"와 서버 `grade` 사용 | 나예린 |
| 5 | `density` null 셀 허용. 지금은 건너뜀으로 방어만 한다 | 이유노 |
