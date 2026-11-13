package com.tripley.crowdsight.replay;

import static com.tripley.crowdsight.timeline.TimelineFixtures.timelineWithDensity;
import static com.tripley.crowdsight.timeline.TimelineFixtures.timelineWithInflow;
import static org.assertj.core.api.Assertions.assertThat;

import java.util.ArrayList;
import java.util.List;
import java.util.Optional;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import com.tripley.crowdsight.config.TestProperties;
import com.tripley.crowdsight.grade.Grade;
import com.tripley.crowdsight.timeline.ZoneTimeline;

class ZoneRuntimeTest {

    private static ZoneRuntime runtime(ZoneTimeline timeline, boolean loop) {
        return new ZoneRuntime(new ZonePlayer(timeline, loop), TestProperties.grader(timeline.meta().cells()));
    }

    @Test
    @DisplayName("반복으로 처음에 돌아오면 판정을 초기화한다")
    void resetOnWrap() {
        ZoneRuntime runtime = runtime(timelineWithDensity(3, 4.5), true);
        List<ZoneStep> steps = new ArrayList<>();

        for (int i = 0; i < 5; i++) {
            steps.add(runtime.tick().orElseThrow());
        }

        assertThat(steps).extracting(s -> s.tick().frame().t()).containsExactly(0, 1, 2, 0, 1);
        assertThat(steps).extracting(s -> s.tick().discontinuity()).containsExactly(true, false, false, true, false);
        assertThat(steps).extracting(s -> s.evaluation().zoneGrade())
                .containsExactly(Grade.NORMAL, Grade.ALERT, Grade.ALERT, Grade.NORMAL, Grade.ALERT);
    }

    @Test
    @DisplayName("반복으로 처음에 돌아오면 유입 창과 경보도 초기화한다")
    void resetsInflowOnWrap() {
        ZoneRuntime runtime = runtime(timelineWithInflow(5, 0.8, 5.0), true);
        List<ZoneStep> steps = new ArrayList<>();

        for (int i = 0; i < 10; i++) {
            steps.add(runtime.tick().orElseThrow());
        }

        assertThat(steps).extracting(s -> s.tick().frame().t()).containsExactly(0, 1, 2, 3, 4, 0, 1, 2, 3, 4);
        assertThat(steps).extracting(s -> s.evaluation().inflowAlert())
                .containsExactly(false, false, false, false, true, false, false, false, false, true);
        assertThat(steps.get(5).evaluation().inflowAvg()).isNull();
    }

    @Test
    @DisplayName("끝난 구역은 판정 결과가 없다")
    void emptyAfterEnd() {
        ZoneRuntime runtime = runtime(timelineWithDensity(1, 4.5), false);

        Optional<ZoneStep> first = runtime.tick();
        Optional<ZoneStep> second = runtime.tick();

        assertThat(first).hasValueSatisfying(s -> {
            assertThat(s.tick().frame().t()).isZero();
            assertThat(s.evaluation().zoneGrade()).isEqualTo(Grade.NORMAL);
        });
        assertThat(second).isEmpty();
    }
}
