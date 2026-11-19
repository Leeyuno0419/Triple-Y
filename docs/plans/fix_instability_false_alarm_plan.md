# 저밀도 셀 불안정 오경보 수정 계획 (`fix/instability-false-alarm`)

| 항목 | 내용 |
|---|---|
| 작성일 | 2026-11-18 |
| 기준 | 이유노 님 리뷰(11-18, E05 불안정 오경보), `docs/api-spec.md` v0.2(3.2·3.3·4.2·4.3·8·10절), `docs/proposal.md` 3.2·3.3, `docs/research/crowd_turbulence_research.md` 1.2·5.4절, `docs/plans/server_s4_instability_inflow_plan.md`, `outputs/e8/*_alert_latency.json`, PR #62(`feat/flow-e5`, 미병합) |
| 대상 | `server/` (`main` `24537bb`에서 분기), `docs/api-spec.md`, `server/README.md` |
| 범위 | 서버 불안정 판정에 셀 밀도 하한(`crowdsight.instability.min-density`)을 더한다. 흐름 모듈(`src/flow/`)·통합 분석(`src/counting/analyze.py`)은 바꾸지 않는다(후속 안건 7장). |
| 상태 | 계획 v1. **사용자 검토 전** (권장안은 `제안`) |

## 0. 확인한 사실

### 0.1 문제 (리뷰 내용과 확인 범위)
- 확인함 (`outputs/e8/`, 30분 반복 측정):

  | 영상 | 반복 | INSTABILITY | GRADE_UP(CRITICAL) | INFLOW |
  |---|---|---|---|---|
  | E04_039 | 10 | 0 | 0 | 20 |
  | E05_035 | 29 | 30 | 30 | 89 |
  | E05_038 | 30 | 30 | 30 | 60 |

  - E05 두 영상은 반복마다 INSTABILITY 1번과 그 다음 초의 GRADE_UP(심각) 1번이 난다. 첫 INSTABILITY는 E05_035·E05_038 모두 `t` 31(`onset_t` 29)이다. 흐름 창 30초가 처음 찬 직후다.
  - E04_039는 불안정 알림이 0개다. 이번 수정으로 E04_039에서 잃는 불안정 탐지는 없다.
- **아직 확인 못 함** (E05 타임라인 파일이 이 PC에 없다. 도착하면 8장에서 확인):
  - E05_035·E05_038 셀 최대 밀도 1.35·1.6명/㎡, E05_038 구역 ≈ 0.47명/㎡(41.4명 / 87.2㎡).
  - pressure > 0.02 개수: E05_038 268/500(최대 0.80), E05_035 130/1113(최대 0.20).
  - 속력 최대 6.4m/s(E05_038 t=25), 3.56m/s(E04_039 t=10). 모두 0.15~0.52명/㎡ 셀.

### 0.2 서버 코드 (불안정 경로)
- `grade/InstabilityTracker.update(Double pressure)`: `pressure != null && pressure > threshold`이면 연속 +1(최대 `seconds`), 아니면 0. `streak >= seconds`이면 true. **밀도를 보지 않는다.**
- `grade/ZoneGrader.evaluate`: 셀마다 `trackers[i].update(state.pressure())` → `observedGrade(density, unstable)`(불안정이면 CRITICAL, 아니면 밀도 등급) → `GradeHysteresis.update`. 구역 등급은 판정 대상(`walkable_area_m2 ≥ 2.0`) 셀 등급의 최댓값.
- `GradeHysteresis`: 올림은 최근 2개 관측이 모두 현재보다 높을 때, 내림은 최근 10개가 모두 낮을 때 한 단계. null 관측은 건너뛴다.
- `alert/AlertDetector`: 판정 대상 셀 중 `unstable` 셀이 없다가 생긴 초에 INSTABILITY(값 = 그 셀들의 최대 `pressure`, `unstable`이면 non-null). 구역 등급이 경계 이상으로 오르면 GRADE_UP.
- `grade/InstabilitySettings(double pressure, int seconds)`: `pressure > 0`, `seconds ≥ 1` 검사. `CrowdsightProperties.instability`로 바로 묶인다. 메시지에 키 이름을 쓴다(테스트가 `hasMessageContaining(key)`로 확인).
- 설정 바인딩: 중첩 record의 기본형(`double`·`int`) 키가 없으면 0으로 묶인다(`CrowdsightProperties` `unackedAlertLimit` 주석). 절 전체가 없으면 record가 null이 되어 거부된다(`rejectsMissingSection`).
- `ws/message/ThresholdsView(density, pressure, inflowRatio)`: `hello.thresholds`. 표시용이다.
- `zone_state.cells[]`에는 `unstable` 키가 없다(api-spec 3.2, 키 10개). 불안정은 셀 `grade`(심각)와 `alert`로만 보인다.
- `application.yml`: `grade.density {caution 3.0, alert 4.0, critical 5.0}`, `instability {pressure 0.02, seconds 3}`.

### 0.3 흐름 모듈 (읽기만, 원인 쪽)
- `src/flow/run_flow.py:67` `analyze_video(..., min_heads: int = 1, noise_var=None, ...)`. 유효 머리가 `min_heads`보다 적은 셀은 `vx`·`vy`·`speed_var`·`pressure`가 null이다. 즉 머리 1개 셀도 속도를 낸다.
- `src/counting/analyze.py:56`은 `min_heads`·`noise_var`를 넘기지 않는다. 기본값(1, None)이 쓰인다.
- `src/flow/cells.py` `speed_var`는 셀 평균 속도의 **시간 분산**(30초 창)이고, `noise_var`가 None이면 잡음 바닥이 0이다(뺄 것이 없다). 머리 1~2개 셀은 사람이 드나들 때마다 셀 평균이 다른 사람의 속도로 바뀌어 분산이 커진다(가정, 8장에서 확인).
- `pressure = round(density, 2) × speed_var`. 속력 상한(이상치 제거)은 코드에 없다.

### 0.4 문헌·기획서
- 기획서 3.3: `P = ρ × Var(v)`, 초기 기준 0.02/s², E5로 민감도 공개. 3.2: 주의 3, 경계 4, 심각 5명/㎡.
- 조사 문서 1.2: 군중난류는 고밀도 현상이다. Helbing 2007 국소 > 10명/㎡(평균 약 6), Fruin 약 7명/㎡, Gu 2025 집단 진동 시작 4.0±0.5명/㎡. "난류 지표는 이미 심각에 가까운 상황에서만 의미가 커진다."
- 조사 문서 1.2 끝·2.2: 원 저자들이 밀도를 곱한 이유는 저밀도에서 사람들이 자유롭게 엇갈려 걸어도 속도 분산이 커지기 때문이다. 그런데 0.47명/㎡에서도 P > 0.02가 되려면 분산 > 0.043m²/s²(성분별 σ ≈ 0.15m/s)면 된다. 저밀도 셀은 머리 수가 적어 이 정도 분산이 쉽게 생긴다.

### 0.5 PR #62 (`feat/flow-e5`, OPEN, base `main`)
- `server/src/test/java/com/tripley/crowdsight/e5/E5Sweep.java:105` `new InstabilitySettings(pressure, seconds)`, `E5SweepTest`의 `new InstabilitySettings(0.04, 3)`. 인자 2개 생성자를 쓴다.
- `E5SweepTest`의 손 계산 기대값은 fixture `e5/e5_sweep_v02.json`(c-0000 밀도 1.0, pressure 0.03)에서 INSTABILITY가 난다는 전제다(`tuple(2, INSTABILITY, ...)`, `"0.02,3,true,2,2,1,..."`).
- 두 PR이 모두 병합되면 컴파일과 기대값이 깨진다. 처리 방법은 6장.

## 1. 선택지 비교

| | (a) `instability.pressure` 올림 | (b) 저밀도 셀을 불안정 판정에서 뺌 | (c) 흐름 쪽 `min_heads`·속력 상한·`noise_var` |
|---|---|---|---|
| 고치는 곳 | `application.yml` 1줄 | 서버 `InstabilityTracker`·`InstabilitySettings`·yml | `src/flow/`(조영준) + `src/counting/analyze.py`(이유노) |
| 재분석 | 필요 없음 | 필요 없음 | **3개 영상 재분석**(이유노 PC, 개당 약 8.5분) + E8·E5 재실행 |
| E05 오경보 | E05_038 최대 0.80(미확인)을 막으려면 기준 > 0.80. 0.02의 40배 | 셀 밀도 < 3이면 모두 막힌다(보고된 셀 0.15~1.6) | 원인을 줄이지만 얼마나 줄지는 재분석 전에 모름 |
| 고밀도 탐지 | 크게 잃는다. ρ = 5에서 분산 > 0.16m²/s²가 되어야 경보. 기준이 장면별 잡음에 맞춰지는 것이지 물리에 맞춰지는 것이 아니다 | 유지(ρ ≥ 3 셀은 지금과 같다) | 유지 |
| 근거 | 없음. E5 결과 없이 숫자만 바꿈 | 조사 문서 1.2(난류는 고밀도 현상), 기획서 3.2 주의 기준 | 조사 문서 5.4(잡음 바닥), 머리 1개 셀 분산 |
| 코드 동결(11-19) 전 | 가능 | 가능(서버만, 테스트 포함 반나절 이내) | 담당자 합의 + 재분석 시간이 필요해 빠듯함 |
| 남는 문제 | 밀도에 비례해 고밀도일수록 같은 잡음으로 경보 | 고밀도 셀의 잡음 경보(잡음 바닥 미적용)는 그대로 → (c)·E5 | 서버는 여전히 밀도와 무관하게 판정 |

- **권장 (제안)**: 지금은 (b)를 서버에서 고친다. (c)는 이유노 님과 합의해 후속 안건으로 넘긴다(7장). (a)는 하지 않고 E5(#62) 민감도 표로 정한다.
- (b)와 (c)는 겹치지 않는다. (b)는 "저밀도에서는 난류가 없다"는 물리 조건이고, (c)는 측정 잡음을 줄인다. (c)를 해도 (b)는 남긴다.

## 2. 설계 (제안)

### 2.1 규칙
- 셀의 그 초를 "넘은 초"로 세는 조건:
  `pressure != null && pressure > instability.pressure && density != null && density >= instability.min-density`
- 조건이 거짓이면 연속을 0으로 되돌린다. 지금 `pressure`가 null이거나 기준 이하일 때와 같은 처리다.
- 불안정 = 연속이 `seconds`(3)에 닿음. 변경 없음.

### 2.2 기본값 `min-density: 3.0` (제안)
- 기획서 3.2 주의 기준(3명/㎡)과 같다. 밀도 등급이 정상인 셀에서 심각이 바로 뜨는 경우를 없앤다. 이번 오경보가 바로 이 경우다(정상 → 심각).
- 문헌의 가장 낮은 시작 밀도(Gu 2025 집단 진동 4.0±0.5, 아래쪽 3.5)보다 낮다. 고밀도에서 P2PNet이 가려진 머리를 덜 세는 쪽(과소 추정) 여유를 둔다.
- 4.0(경계·Gu 중앙값)도 가능하다. 오경보는 더 줄지만, 불안정이 경계 등급 위에서만 더해져 "밀도 등급보다 먼저 위험을 알린다"는 역할이 약해진다. 3.0으로 시작하고 E5로 조정한다.
- 별도 키로 둔다(`grade.density.caution`을 읽지 않는다). 주의 기준을 바꿔도 불안정 판정이 같이 바뀌지 않게 하고, E5가 따로 훑을 수 있게 한다.
- 0은 허용한다(= 밀도 조건 끔, 지금 동작). 음수·NaN은 거부한다.

### 2.3 세부 동작

| 경우 | 동작 | 이유 |
|---|---|---|
| 판정 위치 | `InstabilityTracker`(셀마다) 안. `ZoneGrader`는 `state.density()`를 넘기기만 한다 | 연속(streak)이 tracker 안에 있으므로 끊는 조건도 같은 곳에 둔다. `ZoneGrader`는 한 줄만 바뀐다 |
| 연속 중 밀도가 하한 아래로 | 그 초에 연속 0, `unstable` 바로 false | `pressure`가 기준 아래로 내려갈 때와 같다(api-spec 4.3 "조건이 깨진 초에 바로 false") |
| 밀도 == 하한 | 센다(`>=`) | 등급 규칙(api-spec 4.1 "값 이상이면 그 등급")과 같다 |
| 밀도 null | 세지 않고 연속 0 | 고밀도를 확인할 수 없으면 심각을 내지 않는다. 서버는 `density` null 파일을 거부하므로 방어용(api-spec 4.2·10절 7번). `GradeHysteresis`는 지금처럼 null 관측을 건너뛴다 |
| 불안정이 풀린 뒤 셀 등급 | 변경 없음. 관측 등급이 밀도 등급으로 돌아가고 `GradeHysteresis` 내림(10초에 한 단계)이 정한다 | api-spec 4.3·4.2 |
| GRADE_UP(심각) | 불안정 경로의 심각은 ρ ≥ 3 셀에서만 생긴다. 관측 등급은 이미 주의 이상이다. 올림 2초 규칙은 그대로 | `ZoneGrader.observedGrade` 변경 없음 |
| INSTABILITY 알림 | 규칙 변경 없음(판정 대상 불안정 셀이 생긴 초, 값 = 최대 `pressure`). `unstable`이면 `pressure` non-null도 그대로 성립 | `AlertDetector` 변경 없음 |
| 메시지 스키마 | `hello`·`zone_state`·`alert` 키 변경 없음. `hello.thresholds`에 `min_density`를 **넣지 않는다**(제안) | 화면은 판정하지 않는다. 범례·기준선에 쓰지 않는 값이다. 넣으면 `MessageJsonTest`·화면 어댑터·api-spec 3.1이 같이 바뀐다 |
| 반복·초기화 | 변경 없음(`reset()`이 연속을 0으로) | |
| 키가 빠진 설정 | 기본형이라 0.0(밀도 조건 끔)으로 묶인다 | 기존 `unacked-alert-limit`와 같은 바인딩 동작. `application.yml`에 키가 있고 통합 테스트(`bindsDefaultInstabilityInflowSettings`)가 3.0을 확인한다. 위험 9장 |

## 3. 바꿀 파일

| 파일 | 변경 |
|---|---|
| `server/src/main/java/com/tripley/crowdsight/grade/InstabilitySettings.java` | 성분 `minDensity` 추가, 검사 |
| `server/src/main/java/com/tripley/crowdsight/grade/InstabilityTracker.java` | `update(Double pressure, Double density)`, 밀도 조건 |
| `server/src/main/java/com/tripley/crowdsight/grade/ZoneGrader.java` | `trackers[i].update(state.pressure(), density)` 1줄, Javadoc 1줄 |
| `server/src/main/resources/application.yml` | `instability.min-density: 3.0` |
| `server/src/test/java/com/tripley/crowdsight/config/TestProperties.java` | `INSTABILITY = new InstabilitySettings(0.02, 3, 3.0)` |
| `server/src/test/java/com/tripley/crowdsight/config/CrowdsightPropertiesTest.java` | `defaults()` 키 추가, 거부 사례 추가, 0 허용 테스트 |
| `server/src/test/java/com/tripley/crowdsight/grade/InstabilityTrackerTest.java` | 도우미 시그니처, 새 테스트 6개 |
| `server/src/test/java/com/tripley/crowdsight/grade/ZoneGraderTest.java` | 기존 4개 밀도 수정, 새 테스트 1개 |
| `docs/api-spec.md` | 문서 상태 행, 4.3, 8절, 10절 2번 |
| `server/README.md` | 42행 기준값 설명에 `min-density` 한 마디 |

- 바꾸지 않는 것: `AlertDetector`, `GradeHysteresis`, `CrowdsightProperties`(성분 검사는 `InstabilitySettings`가 한다), `ThresholdsView`·`MessageFactory`, `ZoneRegistry`, `MessageJsonTest`·`ZoneWebSocketIntegrationTest`(`hello.thresholds.pressure` 0.02 그대로), `src/flow/`, `src/counting/`.

### 3.1 `grade/InstabilitySettings.java`

```java
package com.tripley.crowdsight.grade;

/**
 * 셀 불안정 판정 설정 (api-spec 4.3). crowdsight.instability.*로 바인딩한다.
 * pressure는 hello.thresholds.pressure로도 그대로 보낸다. minDensity는 보내지 않는다.
 *
 * @param pressure   군중 압력 기준(1/s²). 이 값을 넘어야(초과) 그 초를 센다
 * @param seconds    기준을 연속으로 넘어야 하는 초 (1 이상)
 * @param minDensity 셀 밀도 하한(명/㎡, 0 이상). 밀도가 이 값 이상인 초만 센다. 0이면 밀도를 보지 않는다
 */
public record InstabilitySettings(double pressure, int seconds, double minDensity) {

    public InstabilitySettings {
        if (!(pressure > 0)) {   // NaN도 거부
            throw new IllegalArgumentException("pressure 는 0보다 커야 합니다: " + pressure);
        }
        if (seconds < 1) {
            throw new IllegalArgumentException("seconds 는 1 이상이어야 합니다: " + seconds);
        }
        if (!(minDensity >= 0)) {   // NaN도 거부
            throw new IllegalArgumentException("min-density 는 0 이상이어야 합니다: " + minDensity);
        }
    }
}
```

### 3.2 `grade/InstabilityTracker.java`

```java
/**
 * 셀 하나의 불안정 판정 (api-spec 4.3). pressure가 기준을 넘고(초과) 밀도가 하한 이상인 초가
 * seconds초 이어지면 불안정이다. 군중난류는 고밀도 현상이라 저밀도 셀은 세지 않는다.
 * pressure·density가 null이거나 조건이 깨지면 연속을 0으로 되돌린다. 조건이 깨진 초에 바로 false가 된다.
 * 심각 등급이 얼마나 남는지는 GradeHysteresis 내림 규칙이 정한다 (별도 유지 타이머 없음).
 * 스레드 규칙: 재생 스레드 하나만 부른다. 잠금 없음.
 */
public final class InstabilityTracker {

    private final double threshold;
    private final int seconds;
    private final double minDensity;
    private int streak;   // 조건을 만족한 연속 초. seconds에서 멈춘다

    /** @param settings 불안정 설정 (값 검사는 InstabilitySettings가 한다) */
    public InstabilityTracker(InstabilitySettings settings) {
        Objects.requireNonNull(settings, "settings");
        this.threshold = settings.pressure();
        this.seconds = settings.seconds();
        this.minDensity = settings.minDensity();
    }

    /** 이번 초의 pressure·density를 반영하고 불안정이면 true를 돌려준다. */
    public boolean update(Double pressure, Double density) {
        if (counts(pressure, density)) {
            if (streak < seconds) {
                streak++;
            }
        } else {
            streak = 0;
        }
        return streak >= seconds;
    }

    // reset() 변경 없음

    private boolean counts(Double pressure, Double density) {
        return pressure != null && pressure > threshold && density != null && density >= minDensity;
    }
}
```

### 3.3 `grade/ZoneGrader.java` (수정분)

```java
 * 셀 관측 등급 = 불안정이면 CRITICAL, 아니면 밀도 등급. 여기에 히스테리시스를 적용한다.
 * 불안정은 밀도가 instability.min-density 이상인 셀만 될 수 있다 (InstabilityTracker).
...
            Double density = state.density();
            boolean unstable = trackers[i].update(state.pressure(), density);
```

### 3.4 `application.yml` (수정분)

```yaml
  instability:
    pressure: 0.02                           # 군중 압력 기준(1/s²). 넘는 초가 이어지면 셀 심각 (가정, E5로 조정)
    seconds: 3                               # 기준을 이 초만큼 연속 넘으면 불안정 (api-spec 4.3)
    min-density: 3.0                         # 셀 밀도(명/㎡)가 이 값 이상인 초만 센다. 주의 기준과 같게 (제안, E5로 조정). 0이면 끔
```

### 3.5 `config/TestProperties.java`

```java
    /** application.yml crowdsight.instability 기본값과 같다 (bindsDefaultInstabilityInflowSettings가 확인). */
    public static final InstabilitySettings INSTABILITY = new InstabilitySettings(0.02, 3, 3.0);
```

## 4. 테스트

### 4.1 `config/CrowdsightPropertiesTest`
- `defaults()`에 `map.put("crowdsight.instability.min-density", "3.0");` 추가. 없으면 0.0으로 묶여 `bindsInstabilityAndInflowKeys`(`isEqualTo(TestProperties.INSTABILITY)`)가 깨진다.
- `rejectsInvalidInstability`의 `@CsvSource`에 `"min-density, -0.1"`, `"min-density, NaN"` 추가. 메시지에 `min-density`가 들어 있는지 확인(기존 방식).
- 추가:

```java
    @Test
    @DisplayName("불안정 밀도 하한 0은 받는다 (밀도 조건 끔)")
    void acceptsZeroMinDensity() {
        Map<String, String> map = defaults();
        map.put("crowdsight.instability.min-density", "0");

        assertThat(bind(map).instability().minDensity()).isZero();
    }
```

### 4.2 `grade/InstabilityTrackerTest`
- 도우미: 기존 `run(tracker, Double... pressures)`는 고밀도(`DENSE = 4.0`)로 부르게 바꾼다. 기존 테스트 6개의 기대값은 그대로다. 밀도가 바뀌는 경우용 도우미를 하나 더 둔다.

```java
    private static final Double DENSE = 4.0;   // 기본 하한 3.0 이상

    /** 고밀도 셀에 pressure를 차례로 넣고 각 초의 불안정 여부를 돌려준다. */
    private static List<Boolean> run(InstabilityTracker tracker, Double... pressures) {
        List<Boolean> result = new ArrayList<>();
        for (Double p : pressures) {
            result.add(tracker.update(p, DENSE));
        }
        return result;
    }

    /** 같은 pressure를 넣고 밀도만 차례로 바꾼다. */
    private static List<Boolean> runDensities(InstabilityTracker tracker, Double pressure, Double... densities) {
        List<Boolean> result = new ArrayList<>();
        for (Double d : densities) {
            result.add(tracker.update(pressure, d));
        }
        return result;
    }
```

- `oneSecondSetting`: `new InstabilitySettings(0.02, 1, 3.0)`.
- 새 테스트:

| 메서드 | `@DisplayName` | 입력 | 기대 |
|---|---|---|---|
| `sparseHighPressureNeverUnstable` | 저밀도 셀은 압력이 커도 불안정이 아니다 | pressure 0.8, 밀도 0.47 × 10 | 모두 false |
| `densityBelowFloorBreaksStreak` | 밀도가 하한 아래인 초는 연속을 끊는다 | 0.03, 밀도 4.0, 4.0, 2.9, 4.0, 4.0, 4.0 | F, F, F, F, F, T |
| `endsWhenDensityDrops` | 불안정 중 밀도가 하한 아래로 내려가면 그 초에 풀린다 | 0.03, 밀도 4.0, 4.0, 4.0, 2.9 | F, F, T, F |
| `densityEqualToFloorCounts` | 밀도가 하한과 같으면 센다 | 0.03, 밀도 3.0 × 3 | F, F, T |
| `nullDensityBreaksStreak` | 밀도 null은 연속을 끊는다 | 0.03, 밀도 4.0, 4.0, null, 4.0 | F, F, F, F |
| `zeroMinDensityIgnoresDensity` | 하한 0이면 밀도와 무관하게 판정한다 | 설정 `(0.02, 3, 0.0)`, 0.03, 밀도 0.0 × 3 | F, F, T |

- `runDensities`의 가변 인자에 null을 넣을 때는 `(Double) null`로 쓴다.

### 4.3 `grade/ZoneGraderTest`
- 밀도 1.0에 압력 0.03으로 불안정을 만들던 기존 테스트 4개는 하한 3.0 때문에 불안정이 안 된다. 밀도를 3.5(주의, 하한 이상)로 바꾼다.

| 테스트 | 바꿀 곳 | 기대값 변화 |
|---|---|---|
| `instabilityToCritical` | `runOne(grader(ONE), 4, 3.5, 0.03, null, null)` | `unstable` F, F, T, T 그대로. 셀 등급·구역 등급 `NORMAL, NORMAL, NORMAL, CRITICAL` → **`NORMAL, CAUTION, CAUTION, CRITICAL`** (t1 주의 관측 2개로 주의, t2 최근 2개 [주의, 심각] 최솟값 주의라 유지, t3 [심각, 심각]으로 심각). 이름(2초 뒤 심각)은 그대로 맞다 |
| `instabilityReleaseUsesDownHysteresis` | `runOne(grader, 4, 3.5, 0.03, null, null)`. 뒤 10초(밀도 1.0, 압력 0.0)는 그대로 | 그대로(t12 심각, t13 경계) |
| `smallCellUnstableExcludedFromZone` | `densities(1.0, 1.0, 3.5)` | 그대로(마지막 t3: `NORMAL, NORMAL, CRITICAL`, 구역 정상) |
| `resetClearsInstabilityAndInflow` | `runOne(grader, 5, 3.5, 0.03, 0.8, 5.0)`, 초기화 뒤 프레임 `densities(3.5)` | 그대로(초기화 뒤 관측 1개라 정상, 불안정 false) |

- `instabilityOverridesDensity`(밀도 4.5)는 그대로 통과한다. fixture 테스트(`valid_v02.json`)는 압력 > 0.02가 2초(t3·t4)뿐이라 지금도 불안정이 없다. 그대로다.
- 새 테스트:

```java
    @Test
    @DisplayName("저밀도 셀은 압력이 기준을 넘어도 정상이다 (E05 오경보)")
    void sparseHighPressureStaysNormal() {
        List<ZoneEvaluation> results = runOne(grader(ONE), 10, 0.47, 0.8, null, null);

        assertThat(results).extracting(e -> e.cells().get(0).unstable()).containsOnly(false);
        assertThat(results).extracting(e -> e.cells().get(0).grade()).containsOnly(NORMAL);
        assertThat(results).extracting(ZoneEvaluation::zoneGrade).containsOnly(NORMAL);
    }
```

### 4.4 영향 없는 테스트 (확인함)
- `AlertDetectorTest`: `CellEvaluation`을 `unstable` 값으로 직접 만든다. 판정기를 거치지 않는다.
- `ZoneRuntimeTest`·`ReplaySchedulerTest`·`MessageFactoryTest`·`WsZoneBroadcasterTest`: `TestProperties.grader`로 `valid_v02.json`을 재생한다. 이 fixture에는 불안정이 없다.
- `MessageJsonTest`·`ZoneWebSocketIntegrationTest`: `hello.thresholds.pressure` 0.02만 본다.
- `CrowdsightServerApplicationIntegrationTest.bindsDefaultInstabilityInflowSettings`: `TestProperties.INSTABILITY`(3.0)와 yml을 비교한다. yml을 고치면 통과한다(고치지 않으면 0.0으로 묶여 실패: 키 누락 검출 역할).

## 5. TDD 단계 (3단계)

1. **설정** (red → green)
   - red: 4.1의 `CrowdsightPropertiesTest` 변경(`defaults()` 키, 거부 2건, `acceptsZeroMinDensity`). `minDensity()`가 없어 컴파일 실패.
   - green: `InstabilitySettings` 3성분(3.1), `TestProperties.INSTABILITY`(3.5), `application.yml`(3.4), `InstabilityTrackerTest.oneSecondSetting` 생성자 인자 추가. tracker는 아직 `minDensity`를 쓰지 않는다.
   - 확인: `./gradlew test` 전부 통과.
2. **셀 밀도 조건** (red → green)
   - red: 4.2 `InstabilityTrackerTest`(도우미 `update(p, DENSE)`, 새 테스트 6개)와 4.3 `ZoneGraderTest`(새 테스트 1개, 기존 4개 밀도 3.5·기대값). `update(Double, Double)`가 없어 컴파일 실패.
   - green: `InstabilityTracker`(3.2), `ZoneGrader` 1줄과 Javadoc(3.3).
   - 확인: `./gradlew test` 전부 통과. 기존 4개를 밀도만 바꾸기 전에 돌리면 실패하는지 한 번 본다(하한이 실제로 적용됨).
3. **문서** (코드 변경 없음)
   - 6장 문서 수정. `./gradlew test` 한 번 더.

- 실행 (Git Bash):
  ```bash
  cd server && JAVA_HOME="/c/Program Files/Eclipse Adoptium/jdk-21.0.13.9-hotspot" ./gradlew test --no-daemon
  ```
- 에이전트는 `bootRun`을 실행하지 않는다.

## 6. 문서

### 6.1 `docs/api-spec.md`
- 문서 상태 표에 행 추가: `| 11-18 보충 | 4.3 불안정은 셀 밀도 `instability.min-density`(3명/㎡, 제안) 이상인 초만 센다 (E05 저밀도 오경보, `docs/plans/fix_instability_false_alarm_plan.md`) |`
- 4.3 첫 항목을 고친다:
  - "셀 `pressure`가 `thresholds.pressure`(0.02/s², 가정)를 넘고 셀 `density`가 `instability.min-density`(3명/㎡, 제안) 이상인 초가 **3초 연속**이면 그 셀을 심각 조건으로 본다."
  - 추가 항목: "밀도 하한 이유: 군중난류는 고밀도 현상이다(`crowd_turbulence_research.md` 1.2). E05_035·E05_038처럼 밀도 1명/㎡ 안팎 셀에서도 머리 수가 적으면 속도 분산이 커져 압력이 기준을 넘는다. 하한은 주의 기준과 같은 3명/㎡로 시작하고 E5로 조정한다 `[토론]`."
  - "`pressure`가 `null`이거나 기준 이하이면" → "`pressure`·`density`가 `null`이거나, `pressure`가 기준 이하이거나, `density`가 하한 미만이면 연속 횟수를 0으로 되돌린다."
  - 추가 항목: "`min-density`는 `hello.thresholds`로 보내지 않는다(표시에 쓰지 않음)."
- 8절 yml: `instability`에 `min-density: 3.0                         # 제안, 주의 기준과 같게. 0이면 끔` 추가.
- 10절 2번 초안: "E5 결과로 조정" → "E5 결과로 조정. 11-18: 저밀도 오경보(E05)로 셀 밀도 하한 3명/㎡ 추가 (4.3절, 제안)".

### 6.2 `server/README.md`
- 42행: "`crowdsight.instability.*`(군중 압력)" → "`crowdsight.instability.*`(군중 압력, 셀 밀도 하한 `min-density`)". 나머지 문장은 그대로. `min-density`는 `hello.thresholds`에 없다는 점을 괄호로 덧붙인다.

### 6.3 바꾸지 않는 문서
- `docs/proposal.md` 3.3은 이유노 님 담당(제출본, v3.2 PDF 재생성 끝)이다. 고치지 않는다. 한 줄 추가 여부는 결정 D5.
- `docs/plans/server_impl_plan.md`·`server_s4_instability_inflow_plan.md`는 기록 문서라 고치지 않는다. 이 계획이 정정 기록이다.

## 7. 후속: 흐름 쪽 (c) — 이유노 님과 합의할 내용 (이 PR에서 하지 않음)

| 항목 | 지금 | 제안 | 고칠 곳 (담당) | 이유 |
|---|---|---|---|---|
| 셀 머리 하한 | `analyze.py:56`이 `min_heads`를 안 넘김 → 1 | `min_heads=3`(가정, E5로 확인) | `src/counting/analyze.py`(이유노) | 머리 1~2개 셀은 사람이 드나들 때마다 셀 평균 속도가 다른 사람 값으로 바뀌어 시간 분산이 커진다. 해당 셀 `pressure`는 null이 된다 |
| 잡음 바닥 | `noise_var` 안 넘김 → 0 | 정지 구간에서 잰 셀별 `Var_noise_c`를 넘김 | `src/counting/analyze.py`(이유노), 측정은 `src/flow/`(조영준) | 조사 문서 5.4. 고밀도 셀의 잡음 경보는 (b)로 막히지 않는다 |
| 속력 상한 | 없음 | 머리 속력 > 3m/s(가정, 걷기 상한 약 2.5m/s 위)는 버림 | `src/flow/run_flow.py`(조영준) 새 인자 + `analyze.py` 전달(이유노) | 보고된 6.4m/s·3.56m/s는 사람 걸음이 아니다(미확인). 패치 흐름 오정합으로 추정 |

- 할 일 순서: (1) 이유노 님과 값 합의 → (2) 코드 변경(동결 11-19 전에 넣을지는 결정 D4) → (3) E04_039·E05_035·E05_038 재분석(이유노 PC, 개당 약 8.5분) → (4) E8 재측정·`e5Sweep` 재실행.
- 이 계획은 `analyze.py`를 고치지 않는다.

## 8. 확인 (타임라인 도착 뒤)

- 도구: PR #62 병합 뒤 `e5Sweep`(서버 판정 클래스를 그대로 재생, `bootRun` 아님).
  ```bash
  cd server && JAVA_HOME="/c/Program Files/Eclipse Adoptium/jdk-21.0.13.9-hotspot" ./gradlew e5Sweep --no-daemon --args="../data/processed/timeline/E05_038.json ../outputs/e5"
  ```
- 체크리스트:
  1. 리뷰 수치 확인: E05_035·E05_038에서 셀 밀도 최대, `pressure > 0.02` 개수·최대, 그 셀의 밀도 구간(< 3 / ≥ 3). 0.1절 "확인 못 함" 항목을 확인함으로 옮긴다.
  2. E05_035·E05_038 `_alerts.csv`: INSTABILITY 0개, 불안정 경로 GRADE_UP(심각) 0개. 남는 것이 있으면 그 셀·초의 밀도·압력으로 설명한다(밀도 ≥ 3 셀이면 (c) 잡음 쪽).
  3. E04_039: 지금도 INSTABILITY 0개(E8). 바뀌지 않아야 한다. `_ticks.csv`의 `zone_grade`·INFLOW 알림이 수정 전과 같아야 한다(밀도 하한은 불안정만 바꾼다).
  4. `_sweep_instability.csv`: 기본 행(`is_default` true)이 2번과 같다. 하한을 훑을지는 결정 D3.
  5. E8을 다시 잴 경우: E05 알림 수가 줄어 `alert_delay_ms` n이 작아진다. 합격 기준(p95 ≤ 5초)은 INFLOW로 계속 측정된다.

## 9. PR #62(E5)와의 충돌

- 두 PR이 모두 병합되면: `E5Sweep`·`E5SweepTest`의 `new InstabilitySettings(p, s)`가 컴파일되지 않고, `E5SweepTest` 손 계산 기대값(fixture c-0000 밀도 1.0에서 INSTABILITY 2번)이 깨진다.
- 처리 (제안): #62를 먼저 병합하고, 이 브랜치를 `main`에 맞춘 뒤 같은 PR에 커밋 1개로 고친다. 둘 다 조영준 님 파일이다.
  - `E5Sweep.instabilityRows`: `new InstabilitySettings(pressure, seconds, TestProperties.INSTABILITY.minDensity())`. 격자·머리줄은 그대로(하한을 격자에 넣을지는 D3).
  - `E5SweepTest`의 `new InstabilitySettings(0.04, 3)` → `(0.04, 3, TestProperties.INSTABILITY.minDensity())`.
  - fixture `e5/e5_sweep_v02.json`의 판정 대상 셀 c-0000 밀도를 1.0 → 3.0(하한 경계)으로 바꾼다. 손 계산 영향: 불안정·심각·알림 시각은 그대로(올림 2초 규칙상 주의 관측이 심각 올림 시각을 바꾸지 않음). GRADE_UP `value`(최대 밀도) 1.0 → 3.0, `_ticks`의 `max_density`, 심각에서 내려온 뒤 바닥 등급이 정상 → 주의로 바뀐다. TDD 에이전트가 기대값을 다시 손 계산하고 테스트로 확인한다.
- #62가 늦어지면 반대로 이 PR을 먼저 병합하고, #62 쪽에서 같은 수정을 한다.
- `src/flow/e5/analysis.py`의 Python 연속 계산(압력만 봄)은 기술 통계용이다. 판정 결과는 `e5Sweep`(서버 클래스)를 기준으로 한다(서버 로직 재사용 원칙).

## 10. 결정

| 번호 | 내용 | 상태 |
|---|---|---|
| D1 | 지금 고칠 방법: (b) 서버에서 저밀도 셀을 불안정 판정에서 뺀다. (a)는 하지 않음, (c)는 후속 | **확정** (11-18 사용자) |
| D2 | 새 키 `crowdsight.instability.min-density`, 기본 3.0(주의 기준과 같음), `>=`, 0 허용(끔), 음수·NaN 거부 | **확정** (11-18 사용자) |
| D3 | `e5Sweep`에 `min-density` 격자(예: 0, 3, 4)를 넣을지 | **확정** (11-18 사용자): 넣는다. 격자 `min_density` ∈ {0, 2.0, **3.0**}. #62 병합 뒤 이 PR 2단계에서 |
| D4 | (c) 흐름 쪽 수정(`min_heads`·`noise_var`·속력 상한)을 동결(11-19) 전에 넣을지 | **확정** (11-18 사용자): 동결 전에는 넣지 않음. 이유노 님과 동결 뒤 상의 |
| D5 | 기획서 3.3에 "서버는 ρ ≥ 3 셀에서만 판정" 한 줄 추가 요청 여부 | **확정** (11-18 사용자): 이유노 님께 요청만 한다(이 PR에서 고치지 않음) |
| D6 | `hello.thresholds`에 `min_density`를 넣지 않음(메시지 스키마 변경 없음) | **확정** (11-18 사용자) |
| D7 | 밀도 null인 초는 연속을 끊음 | **확정** (11-18 사용자) |
| D8 | 판정 위치는 `InstabilityTracker`(셀마다). 연속 중 밀도가 하한 아래로 내려가면 그 초에 연속 0 | **확정** (11-18 사용자) |
| D9 | #62와의 충돌: #62 먼저 병합, 이 PR에서 E5 코드·fixture를 맞춘다 | **확정** (11-18 사용자). #62가 아직 열려 있어 1단계(서버 수정)를 먼저 하고, #62 병합 뒤 `main`을 합쳐 2단계(E5 맞춤 + D3 격자)를 한다 |
| — | 메시지 키·`AlertDetector` 규칙·히스테리시스 규칙 변경 없음 | 확정 (사실) |
| — | `src/counting/analyze.py`는 이 PR에서 고치지 않는다 | 확정 (담당 규칙) |

## 11. 위험

| 위험 | 영향 | 대응 |
|---|---|---|
| 고밀도에서 P2PNet 과소 추정으로 실제 3명/㎡ 이상 셀이 3 미만으로 나옴 | 실제 불안정을 놓침 | 하한을 문헌 최저(3.5)보다 낮은 3.0으로. E5·실영상으로 조정 |
| `min-density` 키가 빠진 설정 파일 | 0.0으로 묶여 밀도 조건이 꺼짐(오경보 재발) | yml에 키, 통합 테스트가 3.0 확인. 운영 설정을 따로 만들면 키를 함께 넣는다 |
| 고밀도 셀의 잡음 경보(잡음 바닥 미적용) | 오경보가 ρ ≥ 3 셀에 남음 | 7장 (c), E5 표로 `pressure` 조정 |
| 리뷰 수치 미확인 | E05 오경보 셀이 실제로는 ρ ≥ 3일 수 있음 | 8장 1·2번. 그때 남은 경보를 설명하거나 (c)로 |
| #62와 병합 순서 | 한쪽이 컴파일 실패 | 9장 |
| 기존 E8 결과(E05)와 달라짐 | 보고서 수치 불일치 | E8 보고서는 수정 전 측정으로 둔다. 다시 재면 새 파일로 남긴다(D4와 함께) |

## 12. 커밋 제안
- `fix: 저밀도 셀은 군중 압력 불안정 판정에서 뺀다 (instability.min-density)` — 코드·테스트·yml (TDD 1·2단계)
- `docs: 불안정 밀도 하한을 api-spec·README에 반영` — 문서 (3단계)
- (#62 병합 뒤) `fix: E5 실행기를 불안정 밀도 하한에 맞춘다`
- PR 제목: `fix: 저밀도 셀 불안정 오경보 제외 (instability.min-density)`, base `main`.

## 변경 이력
| 버전 | 날짜 | 내용 |
|---|---|---|
| v1 | 2026-11-18 | 최초 작성 (Planner). (a)(b)(c) 비교, (b) 제안, 기본 3.0 제안, #62 충돌 처리 |
| v1.1 | 11-18 | 사용자 "추천안대로 진행": D1~D9 확정. D3은 계획 초안(넣지 않음)과 달리 넣는다(0·2.0·3.0). 진행은 1단계 서버 수정 → #62 병합 뒤 2단계 E5 맞춤 |
| v1.2 | 11-19 | 2단계(#62 병합 뒤): `E5Sweep`·`E5SweepTest`를 3인자 `InstabilitySettings`로, fixture c-0000 밀도 1.0 → 3.0(알림 시각·요약 그대로, GRADE_UP `value`·`max_density` 3.0, 바닥 등급 주의). 저밀도 변형 fixture 시험(기본값 INSTABILITY 0개, 하한 0이면 2개) 추가. D3 격자 `min_density` {0, 2.0, 3.0}을 CSV·`report.py`에 반영. api-spec 4.3 `counterflow` 문구와 10절 2번 닫힘 |
