package com.tripley.crowdsight.grade;

import static com.tripley.crowdsight.grade.Grade.ALERT;
import static com.tripley.crowdsight.grade.Grade.CAUTION;
import static com.tripley.crowdsight.grade.Grade.CRITICAL;
import static com.tripley.crowdsight.grade.Grade.NORMAL;
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.util.ArrayList;
import java.util.Collection;
import java.util.Collections;
import java.util.List;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;

import com.tripley.crowdsight.config.TestProperties;

class GradeHysteresisTest {

    private static final DensityThresholds TH = TestProperties.GRADE.density();

    /** 밀도를 차례로 넣고 각 초 뒤의 등급을 돌려준다. null이면 null 관측. */
    private static List<Grade> run(GradeHysteresis h, Double... densities) {
        List<Grade> result = new ArrayList<>();
        for (Double d : densities) {
            result.add(h.update(d == null ? null : GradeRule.ofDensity(d, TH)));
        }
        return result;
    }

    /** 같은 값 n개. seq·grades 안에서 펼친다. */
    private static List<Object> repeat(Object value, int n) {
        return Collections.nCopies(n, value);
    }

    private static List<Object> flatten(Object... parts) {
        List<Object> out = new ArrayList<>();
        for (Object part : parts) {
            if (part instanceof Collection<?> c) {
                out.addAll(c);
            } else {
                out.add(part);
            }
        }
        return out;
    }

    /** 밀도 순서. repeat(2.0, 9) 같은 반복을 펼친다. */
    private static Double[] seq(Object... parts) {
        return flatten(parts).stream().map(o -> (Double) o).toArray(Double[]::new);
    }

    /** 기대 등급 순서. repeat(ALERT, 10) 같은 반복을 펼친다. */
    private static List<Grade> grades(Object... parts) {
        return flatten(parts).stream().map(o -> (Grade) o).toList();
    }

    private static GradeHysteresis newHysteresis() {
        return new GradeHysteresis(2, 10);
    }

    @Test
    @DisplayName("시작 등급은 정상이다")
    void startsNormal() {
        assertThat(newHysteresis().current()).isEqualTo(NORMAL);
    }

    @Test
    @DisplayName("2초 연속 높으면 올린다")
    void upAfterTwoSeconds() {
        assertThat(run(newHysteresis(), 4.2, 4.5)).containsExactly(NORMAL, ALERT);
    }

    @Test
    @DisplayName("1초짜리 튐은 무시한다")
    void spikeIgnored() {
        assertThat(run(newHysteresis(), 4.5, 2.0, 4.5, 2.0)).containsExactly(NORMAL, NORMAL, NORMAL, NORMAL);
    }

    @Test
    @DisplayName("2초 중 낮은 쪽 등급으로 올린다")
    void upToLowerOfStreak() {
        assertThat(run(newHysteresis(), 4.1, 3.9, 4.1, 4.1)).containsExactly(NORMAL, CAUTION, CAUTION, ALERT);
    }

    @Test
    @DisplayName("단계를 건너뛰어 올릴 수 있다")
    void jumpDirectly() {
        assertThat(run(newHysteresis(), 5.5, 5.5)).containsExactly(NORMAL, CRITICAL);
    }

    @Test
    @DisplayName("올린 뒤 기록을 비우지 않아 다음 초에 다시 올릴 수 있다")
    void upKeepsHistory() {
        assertThat(run(newHysteresis(), 3.5, 4.5, 4.5)).containsExactly(NORMAL, CAUTION, ALERT);
    }

    @Test
    @DisplayName("10초 연속 낮으면 한 단계만 내린다")
    void downOneStepPer10s() {
        List<Grade> result = run(newHysteresis(), seq(4.5, 4.5, repeat(2.0, 20)));

        assertThat(result).hasSize(22)
                .isEqualTo(grades(NORMAL, repeat(ALERT, 10), repeat(CAUTION, 10), NORMAL));
    }

    @Test
    @DisplayName("현재와 같은 관측이 내림 연속을 끊는다")
    void downInterrupted() {
        List<Grade> result = run(newHysteresis(), seq(4.5, 4.5, repeat(2.0, 9), 4.0, repeat(2.0, 10)));

        assertThat(result).hasSize(22)
                .isEqualTo(grades(NORMAL, repeat(ALERT, 20), CAUTION));
    }

    @Test
    @DisplayName("심각에서도 10초마다 한 단계씩만 내린다")
    void criticalStepsDownOnly1() {
        List<Grade> result = run(newHysteresis(), seq(5.5, 5.5, repeat(3.5, 30)));

        assertThat(result).hasSize(32)
                .isEqualTo(grades(NORMAL, repeat(CRITICAL, 10), repeat(ALERT, 10), repeat(CAUTION, 11)));
    }

    @Test
    @DisplayName("null 관측은 세지 않는다")
    void nullSkipped() {
        assertThat(run(newHysteresis(), 4.5, null, 4.5)).containsExactly(NORMAL, NORMAL, ALERT);
    }

    @Test
    @DisplayName("null은 내림 연속을 끊지 않는다")
    void nullKeepsDownStreak() {
        List<Grade> result = run(newHysteresis(), seq(4.5, 4.5, repeat(2.0, 5), null, repeat(2.0, 5)));

        assertThat(result).hasSize(13)
                .isEqualTo(grades(NORMAL, repeat(ALERT, 11), CAUTION));
    }

    @Test
    @DisplayName("null만 이어지면 등급을 유지한다")
    void nullOnlyKeepsGrade() {
        List<Grade> result = run(newHysteresis(), seq(4.5, 4.5, repeat(null, 20)));

        assertThat(result).isEqualTo(grades(NORMAL, repeat(ALERT, 21)));
    }

    @Test
    @DisplayName("초기화하면 정상으로 돌아가고 기록을 비운다")
    void resetClears() {
        GradeHysteresis h = newHysteresis();
        run(h, 4.5, 4.5);

        h.reset();

        assertThat(h.current()).isEqualTo(NORMAL);
        assertThat(run(h, 4.5)).containsExactly(NORMAL);
    }

    @ParameterizedTest
    @CsvSource({"0, 10", "2, 0"})
    @DisplayName("관측 수가 1보다 작으면 거부한다")
    void rejectsNonPositiveSeconds(int up, int down) {
        assertThatThrownBy(() -> new GradeHysteresis(up, down))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("1 이상");
    }
}
