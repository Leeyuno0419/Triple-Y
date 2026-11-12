package com.tripley.crowdsight.grade;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.Arrays;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;

class GradeTest {

    @Test
    @DisplayName("등급 순서와 표기는 정상·주의·경계·심각이다")
    void orderAndLabels() {
        assertThat(Grade.values()).containsExactly(Grade.NORMAL, Grade.CAUTION, Grade.ALERT, Grade.CRITICAL);
        assertThat(Arrays.stream(Grade.values()).map(Grade::label)).containsExactly("정상", "주의", "경계", "심각");
    }

    @ParameterizedTest
    @CsvSource({"CRITICAL, ALERT", "ALERT, CAUTION", "CAUTION, NORMAL", "NORMAL, NORMAL"})
    @DisplayName("한 단계 아래 등급을 준다 (정상은 그대로)")
    void lowerStepsDownOne(Grade grade, Grade expected) {
        assertThat(grade.lower()).isEqualTo(expected);
    }

    @Test
    @DisplayName("둘 중 높은 등급을 고른다")
    void maxPicksHigher() {
        assertThat(Grade.max(Grade.CAUTION, Grade.ALERT)).isEqualTo(Grade.ALERT);
        assertThat(Grade.max(Grade.ALERT, Grade.CAUTION)).isEqualTo(Grade.ALERT);
        assertThat(Grade.max(Grade.NORMAL, Grade.NORMAL)).isEqualTo(Grade.NORMAL);
        assertThat(Grade.max(Grade.CRITICAL, Grade.NORMAL)).isEqualTo(Grade.CRITICAL);
    }
}
