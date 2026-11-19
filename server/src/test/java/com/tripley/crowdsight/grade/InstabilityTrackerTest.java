package com.tripley.crowdsight.grade;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import com.tripley.crowdsight.config.TestProperties;

class InstabilityTrackerTest {

    private final InstabilityTracker tracker = new InstabilityTracker(TestProperties.INSTABILITY);

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

    @Test
    @DisplayName("기준을 3초 연속 넘으면 불안정이다")
    void activeAfterThreeSeconds() {
        assertThat(run(tracker, 0.03, 0.03, 0.03, 0.03)).containsExactly(false, false, true, true);
    }

    @Test
    @DisplayName("pressure null은 연속을 끊는다")
    void nullBreaksStreak() {
        assertThat(run(tracker, 0.03, 0.03, null, 0.03, 0.03, 0.03))
                .containsExactly(false, false, false, false, false, true);
    }

    @Test
    @DisplayName("기준과 같은 값은 넘은 것이 아니다")
    void equalToThresholdBreaksStreak() {
        assertThat(run(tracker, 0.03, 0.02, 0.03, 0.03, 0.03)).containsExactly(false, false, false, false, true);
    }

    @Test
    @DisplayName("기준 아래로 내려간 초에 바로 풀린다")
    void endsAsSoonAsBelow() {
        assertThat(run(tracker, 0.03, 0.03, 0.03, 0.01, 0.03)).containsExactly(false, false, true, false, false);
    }

    @Test
    @DisplayName("초기화하면 연속이 0부터 다시 쌓인다")
    void resetClearsStreak() {
        run(tracker, 0.03, 0.03);

        tracker.reset();

        assertThat(run(tracker, 0.03, 0.03, 0.03)).containsExactly(false, false, true);
    }

    @Test
    @DisplayName("seconds 1이면 넘은 초에 바로 불안정이다")
    void oneSecondSetting() {
        InstabilityTracker oneSecond = new InstabilityTracker(new InstabilitySettings(0.02, 1, 3.0));

        assertThat(run(oneSecond, 0.03, 0.0)).containsExactly(true, false);
    }

    @Test
    @DisplayName("저밀도 셀은 압력이 커도 불안정이 아니다")
    void sparseHighPressureNeverUnstable() {
        Double[] sparse = new Double[10];
        Arrays.fill(sparse, 0.47);

        assertThat(runDensities(tracker, 0.8, sparse)).containsOnly(false);
    }

    @Test
    @DisplayName("밀도가 하한 아래인 초는 연속을 끊는다")
    void densityBelowFloorBreaksStreak() {
        assertThat(runDensities(tracker, 0.03, 4.0, 4.0, 2.9, 4.0, 4.0, 4.0))
                .containsExactly(false, false, false, false, false, true);
    }

    @Test
    @DisplayName("불안정 중 밀도가 하한 아래로 내려가면 그 초에 풀린다")
    void endsWhenDensityDrops() {
        assertThat(runDensities(tracker, 0.03, 4.0, 4.0, 4.0, 2.9)).containsExactly(false, false, true, false);
    }

    @Test
    @DisplayName("밀도가 하한과 같으면 센다")
    void densityEqualToFloorCounts() {
        assertThat(runDensities(tracker, 0.03, 3.0, 3.0, 3.0)).containsExactly(false, false, true);
    }

    @Test
    @DisplayName("밀도 null은 연속을 끊는다")
    void nullDensityBreaksStreak() {
        assertThat(runDensities(tracker, 0.03, 4.0, 4.0, null, 4.0)).containsExactly(false, false, false, false);
    }

    @Test
    @DisplayName("하한 0이면 밀도와 무관하게 판정한다")
    void zeroMinDensityIgnoresDensity() {
        InstabilityTracker noFloor = new InstabilityTracker(new InstabilitySettings(0.02, 3, 0.0));

        assertThat(runDensities(noFloor, 0.03, 0.0, 0.0, 0.0)).containsExactly(false, false, true);
    }
}
