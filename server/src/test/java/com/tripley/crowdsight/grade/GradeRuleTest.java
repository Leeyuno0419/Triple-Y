package com.tripley.crowdsight.grade;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;

class GradeRuleTest {

    private static final DensityThresholds TH = new DensityThresholds(3.0, 4.0, 5.0);

    @ParameterizedTest
    @CsvSource({"0, NORMAL", "2.99, NORMAL", "3.0, CAUTION", "3.99, CAUTION", "4.0, ALERT", "4.99, ALERT",
            "5.0, CRITICAL", "9.9, CRITICAL"})
    @DisplayName("기준값 이상이면 그 등급이다")
    void ofDensityUsesInclusiveThresholds(double density, Grade expected) {
        assertThat(GradeRule.ofDensity(density, TH)).isEqualTo(expected);
    }

    @Test
    @DisplayName("예측 밀도를 같은 기준으로 바꾼다")
    void ofPredictionMapsValue() {
        assertThat(GradeRule.ofPrediction(4.6, TH)).isEqualTo(Grade.ALERT);
        assertThat(GradeRule.ofPrediction(2.99, TH)).isEqualTo(Grade.NORMAL);
    }

    @Test
    @DisplayName("예측이 null이면 null이다")
    void ofPredictionNull() {
        assertThat(GradeRule.ofPrediction(null, TH)).isNull();
    }
}
