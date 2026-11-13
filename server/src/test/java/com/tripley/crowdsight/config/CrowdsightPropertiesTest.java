package com.tripley.crowdsight.config;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.time.ZoneId;
import java.util.HashMap;
import java.util.Map;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;
import org.junit.jupiter.params.provider.ValueSource;
import org.springframework.boot.context.properties.bind.BindException;
import org.springframework.boot.context.properties.bind.Binder;
import org.springframework.boot.context.properties.source.MapConfigurationPropertySource;

class CrowdsightPropertiesTest {

    private static Map<String, String> defaults() {
        Map<String, String> map = new HashMap<>();
        map.put("crowdsight.timeline-dir", "../data/processed/timeline");
        map.put("crowdsight.timeline-files[0]", "a.json");
        map.put("crowdsight.timeline-files[1]", "b.json");
        map.put("crowdsight.replay.interval-ms", "1000");
        map.put("crowdsight.replay.loop", "true");
        map.put("crowdsight.grade.density.caution", "3.0");
        map.put("crowdsight.grade.density.alert", "4.0");
        map.put("crowdsight.grade.density.critical", "5.0");
        map.put("crowdsight.grade.up-seconds", "2");
        map.put("crowdsight.grade.down-seconds", "10");
        map.put("crowdsight.grade.min-walkable-area-m2", "2.0");
        map.put("crowdsight.instability.pressure", "0.02");
        map.put("crowdsight.instability.seconds", "3");
        map.put("crowdsight.inflow.ratio", "0.6");
        map.put("crowdsight.inflow.window-seconds", "5");
        map.put("crowdsight.inflow.min-samples", "3");
        map.put("crowdsight.inflow.off-seconds", "10");
        map.put("crowdsight.inflow.min-count", "3");
        map.put("crowdsight.unacked-alert-limit", "100");
        map.put("crowdsight.time-zone", "Asia/Seoul");
        map.put("crowdsight.ws.ping-interval-ms", "30000");
        map.put("crowdsight.ws.send-time-limit-ms", "2000");
        map.put("crowdsight.ws.buffer-size-limit-bytes", "524288");
        map.put("crowdsight.cors-origin-patterns[0]", "http://localhost:*");
        map.put("crowdsight.cors-origin-patterns[1]", "http://127.0.0.1:*");
        return map;
    }

    private static CrowdsightProperties bind(Map<String, String> map) {
        return new Binder(new MapConfigurationPropertySource(map)).bind("crowdsight", CrowdsightProperties.class).get();
    }

    @Test
    @DisplayName("timeline·replay 키를 record로 묶는다")
    void bindsTimelineAndReplayKeys() {
        CrowdsightProperties props = bind(defaults());

        assertThat(props.timelineDir()).isEqualTo("../data/processed/timeline");
        assertThat(props.timelineFiles()).containsExactly("a.json", "b.json");
        assertThat(props.replay().intervalMs()).isEqualTo(1000);
        assertThat(props.replay().loop()).isTrue();
    }

    @ParameterizedTest
    @ValueSource(longs = {0, -1})
    @DisplayName("재생 간격이 0 이하이면 바인딩에서 거부한다")
    void rejectsNonPositiveInterval(long interval) {
        Map<String, String> map = defaults();
        map.put("crowdsight.replay.interval-ms", String.valueOf(interval));

        assertThatThrownBy(() -> bind(map))
                .isInstanceOf(BindException.class)
                .rootCause().hasMessageContaining("crowdsight.replay.interval-ms");
    }

    @Test
    @DisplayName("타임라인 파일이 없으면 거부한다")
    void rejectsEmptyTimelineFiles() {
        Map<String, String> map = defaults();
        map.remove("crowdsight.timeline-files[0]");
        map.remove("crowdsight.timeline-files[1]");

        assertThatThrownBy(() -> bind(map))
                .isInstanceOf(BindException.class)
                .rootCause().hasMessageContaining("crowdsight.timeline-files");
    }

    @Test
    @DisplayName("타임라인 폴더가 없으면 거부한다")
    void rejectsMissingTimelineDir() {
        Map<String, String> map = defaults();
        map.remove("crowdsight.timeline-dir");

        assertThatThrownBy(() -> bind(map))
                .isInstanceOf(BindException.class)
                .rootCause().hasMessageContaining("crowdsight.timeline-dir");
    }

    @Test
    @DisplayName("grade 키를 등급 설정 record로 묶는다")
    void bindsGradeKeys() {
        assertThat(bind(defaults()).grade()).isEqualTo(TestProperties.GRADE);
    }

    @ParameterizedTest
    @CsvSource({"alert, 3.0", "critical, 4.0"})
    @DisplayName("밀도 기준 순서가 틀리면 바인딩에서 거부한다")
    void rejectsUnorderedDensity(String key, String value) {
        Map<String, String> map = defaults();
        map.put("crowdsight.grade.density." + key, value);

        assertThatThrownBy(() -> bind(map))
                .isInstanceOf(BindException.class)
                .hasMessageContaining("crowdsight.grade.density")
                .rootCause().hasMessageContaining("caution < alert < critical");
    }

    @ParameterizedTest
    @ValueSource(strings = {"up-seconds", "down-seconds"})
    @DisplayName("올림·내림 초가 0이면 거부한다")
    void rejectsNonPositiveGradeSeconds(String key) {
        Map<String, String> map = defaults();
        map.put("crowdsight.grade." + key, "0");

        assertThatThrownBy(() -> bind(map))
                .isInstanceOf(BindException.class)
                .rootCause().hasMessageContaining(key);
    }

    @Test
    @DisplayName("최소 면적 0이면 모든 셀이 대상이 되도록 바인딩된다")
    void bindsZeroMinWalkableArea() {
        Map<String, String> map = defaults();
        map.put("crowdsight.grade.min-walkable-area-m2", "0");

        assertThat(bind(map).grade().minWalkableAreaM2()).isEqualTo(0.0);
    }

    @Test
    @DisplayName("최소 면적이 음수면 거부한다")
    void rejectsNegativeMinWalkableArea() {
        Map<String, String> map = defaults();
        map.put("crowdsight.grade.min-walkable-area-m2", "-0.1");

        assertThatThrownBy(() -> bind(map))
                .isInstanceOf(BindException.class)
                .rootCause().hasMessageContaining("min-walkable-area-m2");
    }

    @Test
    @DisplayName("grade 설정이 없으면 거부한다")
    void rejectsMissingGrade() {
        Map<String, String> map = defaults();
        map.keySet().removeIf(key -> key.startsWith("crowdsight.grade."));

        assertThatThrownBy(() -> bind(map))
                .isInstanceOf(BindException.class)
                .rootCause().hasMessageContaining("crowdsight.grade");
    }

    @Test
    @DisplayName("ws·허용 출처·시간대 키를 묶는다")
    void bindsWsCorsAndTimeZone() {
        CrowdsightProperties props = bind(defaults());

        assertThat(props.ws()).isEqualTo(TestProperties.WS);
        assertThat(props.corsOriginPatterns()).isEqualTo(TestProperties.CORS);
        assertThat(props.clockZone()).isEqualTo(ZoneId.of("Asia/Seoul"));
    }

    @ParameterizedTest
    @ValueSource(strings = {"ping-interval-ms", "send-time-limit-ms", "buffer-size-limit-bytes"})
    @DisplayName("ws 값이 0이면 거부한다")
    void rejectsNonPositiveWs(String key) {
        Map<String, String> map = defaults();
        map.put("crowdsight.ws." + key, "0");

        assertThatThrownBy(() -> bind(map))
                .isInstanceOf(BindException.class)
                .rootCause().hasMessageContaining("crowdsight.ws." + key);
    }

    @Test
    @DisplayName("ws 설정이 없으면 거부한다")
    void rejectsMissingWs() {
        Map<String, String> map = defaults();
        map.keySet().removeIf(key -> key.startsWith("crowdsight.ws."));

        assertThatThrownBy(() -> bind(map))
                .isInstanceOf(BindException.class)
                .rootCause().hasMessageContaining("crowdsight.ws");
    }

    @Test
    @DisplayName("모르는 시간대면 거부한다")
    void rejectsUnknownTimeZone() {
        Map<String, String> map = defaults();
        map.put("crowdsight.time-zone", "Mars/Base");

        assertThatThrownBy(() -> bind(map))
                .isInstanceOf(BindException.class)
                .rootCause().hasMessageContaining("crowdsight.time-zone");
    }

    @Test
    @DisplayName("허용 출처가 없으면 거부한다")
    void rejectsMissingCorsPatterns() {
        Map<String, String> map = defaults();
        map.keySet().removeIf(key -> key.startsWith("crowdsight.cors-origin-patterns"));

        assertThatThrownBy(() -> bind(map))
                .isInstanceOf(BindException.class)
                .rootCause().hasMessageContaining("crowdsight.cors-origin-patterns");
    }

    @Test
    @DisplayName("빈 허용 출처 패턴을 거부한다")
    void rejectsBlankCorsPattern() {
        Map<String, String> map = defaults();
        map.put("crowdsight.cors-origin-patterns[1]", " ");

        assertThatThrownBy(() -> bind(map))
                .isInstanceOf(BindException.class)
                .rootCause().hasMessageContaining("빈 패턴");
    }

    @Test
    @DisplayName("instability·inflow 키를 설정 record로 묶는다")
    void bindsInstabilityAndInflowKeys() {
        CrowdsightProperties props = bind(defaults());

        assertThat(props.instability()).isEqualTo(TestProperties.INSTABILITY);
        assertThat(props.inflow()).isEqualTo(TestProperties.INFLOW);
    }

    @ParameterizedTest
    @CsvSource({"pressure, 0", "pressure, -0.01", "seconds, 0"})
    @DisplayName("불안정 기준·초가 틀리면 거부한다")
    void rejectsInvalidInstability(String key, String value) {
        Map<String, String> map = defaults();
        map.put("crowdsight.instability." + key, value);

        assertThatThrownBy(() -> bind(map))
                .isInstanceOf(BindException.class)
                .rootCause().hasMessageContaining(key);
    }

    @ParameterizedTest
    @CsvSource({"ratio, 1.0", "ratio, -0.1", "window-seconds, 0", "min-samples, 0", "off-seconds, 0",
            "min-count, -1"})
    @DisplayName("유입 설정 값이 틀리면 거부한다")
    void rejectsInvalidInflow(String key, String value) {
        Map<String, String> map = defaults();
        map.put("crowdsight.inflow." + key, value);

        assertThatThrownBy(() -> bind(map))
                .isInstanceOf(BindException.class)
                .rootCause().hasMessageContaining(key);
    }

    @Test
    @DisplayName("min-samples가 창보다 크면 거부한다")
    void rejectsMinSamplesAboveWindow() {
        Map<String, String> map = defaults();
        map.put("crowdsight.inflow.min-samples", "6");

        assertThatThrownBy(() -> bind(map))
                .isInstanceOf(BindException.class)
                .rootCause().hasMessageContaining("min-samples").hasMessageContaining("window-seconds");
    }

    @ParameterizedTest
    @ValueSource(strings = {"instability", "inflow"})
    @DisplayName("instability·inflow 설정이 없으면 거부한다")
    void rejectsMissingSection(String key) {
        Map<String, String> map = defaults();
        map.keySet().removeIf(k -> k.startsWith("crowdsight." + key + "."));

        assertThatThrownBy(() -> bind(map))
                .isInstanceOf(BindException.class)
                .rootCause().hasMessageContaining("crowdsight." + key);
    }

    @Test
    @DisplayName("미확인 알림 상한을 묶는다")
    void bindsUnackedAlertLimit() {
        assertThat(bind(defaults()).unackedAlertLimit()).isEqualTo(100);
    }

    @ParameterizedTest
    @ValueSource(ints = {0, -1})
    @DisplayName("미확인 알림 상한이 1 미만이면 거부한다")
    void rejectsNonPositiveUnackedAlertLimit(int limit) {
        Map<String, String> map = defaults();
        map.put("crowdsight.unacked-alert-limit", String.valueOf(limit));

        assertThatThrownBy(() -> bind(map))
                .isInstanceOf(BindException.class)
                .rootCause().hasMessageContaining("crowdsight.unacked-alert-limit");
    }

    @Test
    @DisplayName("미확인 알림 상한이 없으면 거부한다")
    void rejectsMissingUnackedAlertLimit() {
        Map<String, String> map = defaults();
        map.remove("crowdsight.unacked-alert-limit");

        assertThatThrownBy(() -> bind(map))
                .isInstanceOf(BindException.class)
                .rootCause().hasMessageContaining("crowdsight.unacked-alert-limit");
    }
}
