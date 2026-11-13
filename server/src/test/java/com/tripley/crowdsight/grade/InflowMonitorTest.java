package com.tripley.crowdsight.grade;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.within;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import com.tripley.crowdsight.config.TestProperties;

class InflowMonitorTest {

    private final InflowMonitor monitor = new InflowMonitor(TestProperties.INFLOW);

    /** inflow_ratio를 차례로 넣고 각 초의 결과를 돌려준다. counts는 초마다의 구역 인원. */
    private static List<InflowStatus> run(InflowMonitor monitor, Double[] ratios, Double[] counts) {
        List<InflowStatus> result = new ArrayList<>();
        for (int i = 0; i < ratios.length; i++) {
            result.add(monitor.update(ratios[i], counts[i]));
        }
        return result;
    }

    /** count가 매 초 같을 때. */
    private static List<InflowStatus> run(InflowMonitor monitor, Double[] ratios, Double count) {
        Double[] counts = new Double[ratios.length];
        Arrays.fill(counts, count);
        return run(monitor, ratios, counts);
    }

    /** 이어 붙인 값 배열. List는 펼친다. */
    private static Double[] seq(Object... parts) {
        List<Double> out = new ArrayList<>();
        for (Object part : parts) {
            if (part instanceof List<?> list) {
                list.forEach(v -> out.add((Double) v));
            } else {
                out.add((Double) part);
            }
        }
        return out.toArray(Double[]::new);
    }

    private static List<Double> repeat(Double value, int n) {
        return Collections.nCopies(n, value);
    }

    private static List<Boolean> ons(List<InflowStatus> statuses) {
        return statuses.stream().map(InflowStatus::on).toList();
    }

    @Test
    @DisplayName("5초 평균이 기준을 넘는 초에 켠다")
    void onAt5sAverage() {
        List<InflowStatus> s = run(monitor, seq(repeat(0.4, 3), repeat(0.8, 3)), 5.0);

        for (int t = 0; t < 4; t++) {
            assertThat(s.get(t).average()).isNull();
        }
        assertThat(s.get(4).average()).isCloseTo(0.56, within(1e-9));
        assertThat(s.get(5).average()).isCloseTo(0.64, within(1e-9));
        assertThat(ons(s)).containsExactly(false, false, false, false, false, true);
    }

    @Test
    @DisplayName("창이 다 차기 전에는 평균이 null이다")
    void nullUntilWindowFull() {
        List<InflowStatus> s = run(monitor, seq(repeat(0.7, 5)), 5.0);

        for (int t = 0; t < 4; t++) {
            assertThat(s.get(t).average()).isNull();
        }
        assertThat(s.get(4).average()).isCloseTo(0.7, within(1e-9));
        assertThat(ons(s)).containsExactly(false, false, false, false, true);
    }

    @Test
    @DisplayName("창 안 null은 빼고 평균을 낸다")
    void nullInWindow() {
        List<InflowStatus> s = run(monitor, seq(0.7, null, 0.8, 0.7, 0.9), 5.0);

        for (int t = 0; t < 4; t++) {
            assertThat(s.get(t).average()).isNull();
        }
        assertThat(s.get(4).average()).isCloseTo(0.775, within(1e-9));
        assertThat(ons(s)).containsExactly(false, false, false, false, true);
    }

    @Test
    @DisplayName("창 안 값이 3개 미만이면 평균은 null이다")
    void tooFewSamplesStaysOff() {
        List<InflowStatus> s = run(monitor, seq(0.9, null, null, null, 0.9, repeat(null, 5)), 5.0);

        assertThat(s).extracting(InflowStatus::average).containsOnlyNulls();
        assertThat(ons(s)).containsOnly(false);
    }

    @Test
    @DisplayName("평균이 기준과 같으면 켜지 않는다")
    void strictlyAboveRatio() {
        InflowMonitor half = new InflowMonitor(new InflowSettings(0.5, 5, 3, 10, 3.0));

        List<InflowStatus> s = run(half, seq(repeat(0.5, 5), 0.75), 5.0);

        assertThat(s.get(4).average()).isEqualTo(0.5);
        assertThat(s.get(4).on()).isFalse();
        assertThat(s.get(5).average()).isCloseTo(0.55, within(1e-9));
        assertThat(s.get(5).on()).isTrue();
    }

    @Test
    @DisplayName("구역 인원이 3명 미만이면 켜지 않는다")
    void blockedBelowMinCount() {
        List<InflowStatus> s = run(monitor, seq(repeat(0.7, 5)), 2.9);

        assertThat(s.get(4).average()).isCloseTo(0.7, within(1e-9));
        assertThat(s.get(4).on()).isFalse();
    }

    @Test
    @DisplayName("구역 인원이 정확히 3명이면 켤 수 있다")
    void countBoundaryIncluded() {
        List<InflowStatus> s = run(monitor, seq(repeat(0.7, 5)), 3.0);

        assertThat(s.get(4).on()).isTrue();
    }

    @Test
    @DisplayName("count null이면 켜지 않는다")
    void nullCountBlocks() {
        List<InflowStatus> s = run(monitor, seq(repeat(0.7, 5)), (Double) null);

        assertThat(s.get(4).average()).isCloseTo(0.7, within(1e-9));
        assertThat(s.get(4).on()).isFalse();
    }

    @Test
    @DisplayName("켜진 뒤 조건이 10초 연속 거짓이면 끈다")
    void offAfter10s() {
        List<InflowStatus> s = run(monitor, seq(repeat(0.8, 5), repeat(0.1, 11)), 5.0);

        assertThat(s.get(4).on()).isTrue();
        assertThat(s.get(5).average()).isCloseTo(0.66, within(1e-9));
        assertThat(s.get(5).on()).isTrue();
        assertThat(s.get(6).average()).isCloseTo(0.52, within(1e-9));
        assertThat(s.get(14).on()).isTrue();
        assertThat(s.get(15).on()).isFalse();
    }

    @Test
    @DisplayName("평균 null인 초도 끄는 연속에 센다")
    void nullAverageCountsTowardOff() {
        List<InflowStatus> s = run(monitor, seq(repeat(0.8, 5), repeat(null, 12)), 5.0);

        assertThat(s.get(4).on()).isTrue();
        assertThat(s.get(5).average()).isCloseTo(0.8, within(1e-9));
        assertThat(s.get(6).average()).isCloseTo(0.8, within(1e-9));
        assertThat(s.get(7).average()).isNull();
        assertThat(s.get(15).on()).isTrue();
        assertThat(s.get(16).on()).isFalse();
    }

    @Test
    @DisplayName("중간에 조건이 참이면 끄는 연속이 처음부터 다시 쌓인다")
    void trueResetsOffStreak() {
        Double[] counts = seq(repeat(5.0, 5), repeat(2.0, 9), 5.0, repeat(2.0, 10));

        List<InflowStatus> s = run(monitor, seq(repeat(0.8, 25)), counts);

        assertThat(s.get(4).on()).isTrue();
        assertThat(s.get(13).on()).isTrue();
        assertThat(s.get(14).on()).isTrue();
        assertThat(s.get(23).on()).isTrue();
        assertThat(s.get(24).on()).isFalse();
    }

    @Test
    @DisplayName("초기화하면 창·경보가 비워진다")
    void resetClears() {
        List<InflowStatus> before = run(monitor, seq(repeat(0.7, 5)), 5.0);

        monitor.reset();
        List<InflowStatus> after = run(monitor, seq(repeat(0.7, 5)), 5.0);

        assertThat(before.get(4).on()).isTrue();
        for (int t = 0; t < 4; t++) {
            assertThat(after.get(t).average()).isNull();
        }
        assertThat(ons(after)).containsExactly(false, false, false, false, true);
        assertThat(after.get(4).average()).isCloseTo(0.7, within(1e-9));
    }
}
