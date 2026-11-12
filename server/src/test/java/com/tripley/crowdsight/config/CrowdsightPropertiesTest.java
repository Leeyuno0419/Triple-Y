package com.tripley.crowdsight.config;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.util.HashMap;
import java.util.Map;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
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
}
