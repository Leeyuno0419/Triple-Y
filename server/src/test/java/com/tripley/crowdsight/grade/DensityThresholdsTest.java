package com.tripley.crowdsight.grade;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;

class DensityThresholdsTest {

    @Test
    @DisplayName("0 < 주의 < 경계 < 심각이면 만든다")
    void acceptsOrdered() {
        DensityThresholds th = new DensityThresholds(3.0, 4.0, 5.0);

        assertThat(th.caution()).isEqualTo(3.0);
        assertThat(th.alert()).isEqualTo(4.0);
        assertThat(th.critical()).isEqualTo(5.0);
    }

    @ParameterizedTest
    @CsvSource({"3, 3, 5", "3, 4, 4", "4, 3, 5", "0, 4, 5", "-1, 4, 5", "NaN, 4, 5"})
    @DisplayName("기준 순서가 틀리면 거부한다")
    void rejectsUnordered(double caution, double alert, double critical) {
        assertThatThrownBy(() -> new DensityThresholds(caution, alert, critical))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("caution < alert < critical");
    }
}
