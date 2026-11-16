package com.tripley.crowdsight.replay;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

class TickStatsTest {

    private final TickStats stats = new TickStats();

    @Test
    @DisplayName("기록 전에는 null이다")
    void emptyBeforeFirstRecord() {
        assertThat(stats.lastMs()).isNull();
        assertThat(stats.maxMs()).isNull();
    }

    @Test
    @DisplayName("마지막 값과 최댓값을 ms로 준다")
    void recordsLastAndMax() {
        stats.record(1_234_567);
        assertThat(stats.lastMs()).isEqualTo(1.235);
        assertThat(stats.maxMs()).isEqualTo(1.235);

        stats.record(500_000);
        assertThat(stats.lastMs()).isEqualTo(0.5);
        assertThat(stats.maxMs()).isEqualTo(1.235);

        stats.record(2_000_000);
        assertThat(stats.lastMs()).isEqualTo(2.0);
        assertThat(stats.maxMs()).isEqualTo(2.0);
    }

    @Test
    @DisplayName("소수 3자리로 반올림한다")
    void roundsToMicroseconds() {
        stats.record(999);
        assertThat(stats.lastMs()).isEqualTo(0.001);

        stats.record(1_499);
        assertThat(stats.lastMs()).isEqualTo(0.001);
    }

    @Test
    @DisplayName("음수 시간은 거부한다")
    void rejectsNegative() {
        assertThatThrownBy(() -> stats.record(-1))
                .isInstanceOf(IllegalArgumentException.class);
    }
}
