package com.tripley.crowdsight.config;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

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
}
