package com.tripley.crowdsight.grade;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.ArrayList;
import java.util.List;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import com.tripley.crowdsight.config.TestProperties;

class InstabilityTrackerTest {

    private final InstabilityTracker tracker = new InstabilityTracker(TestProperties.INSTABILITY);

    /** pressure를 차례로 넣고 각 초의 불안정 여부를 돌려준다. */
    private static List<Boolean> run(InstabilityTracker tracker, Double... pressures) {
        List<Boolean> result = new ArrayList<>();
        for (Double p : pressures) {
            result.add(tracker.update(p));
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
        InstabilityTracker oneSecond = new InstabilityTracker(new InstabilitySettings(0.02, 1));

        assertThat(run(oneSecond, 0.03, 0.0)).containsExactly(true, false);
    }
}
