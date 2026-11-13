package com.tripley.crowdsight;

import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.nio.file.Path;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;

import com.tripley.crowdsight.timeline.InvalidTimelineException;

class TimelineStartupIntegrationTest {

    private static void run(String... args) {
        SpringApplication app = new SpringApplication(CrowdsightServerApplication.class);
        app.setWebApplicationType(WebApplicationType.NONE);
        try (var ctx = app.run(args)) {
            // 시작에 성공하면 바로 닫는다
        }
    }

    @Test
    @DisplayName("타임라인 파일이 없으면 절대 경로를 알리며 시작하지 않는다")
    void failsWithAbsolutePathWhenFileMissing() {
        Path expected = Path.of("src/test/resources/timeline/nope.json").toAbsolutePath().normalize();

        assertThatThrownBy(() -> run("--crowdsight.timeline-dir=src/test/resources/timeline",
                "--crowdsight.timeline-files=nope.json"))
                .rootCause()
                .isInstanceOf(InvalidTimelineException.class)
                .hasMessageContaining(expected.toString());
    }

    @Test
    @DisplayName("재생 간격이 0이면 시작하지 않는다")
    void failsOnInvalidReplayInterval() {
        assertThatThrownBy(() -> run("--crowdsight.timeline-dir=src/test/resources/timeline",
                "--crowdsight.timeline-files=valid_v02.json", "--crowdsight.replay.interval-ms=0"))
                .rootCause()
                .hasMessageContaining("crowdsight.replay.interval-ms");
    }

    @Test
    @DisplayName("밀도 기준 순서가 틀리면 시작하지 않는다")
    void failsOnUnorderedDensityThresholds() {
        assertThatThrownBy(() -> run("--crowdsight.timeline-dir=src/test/resources/timeline",
                "--crowdsight.timeline-files=valid_v02.json", "--crowdsight.grade.density.alert=3.0"))
                .rootCause()
                .hasMessageContaining("caution < alert < critical");
    }

    @Test
    @DisplayName("모르는 시간대면 시작하지 않는다")
    void failsOnUnknownTimeZone() {
        assertThatThrownBy(() -> run("--crowdsight.timeline-dir=src/test/resources/timeline",
                "--crowdsight.timeline-files=valid_v02.json", "--crowdsight.time-zone=Mars/Base"))
                .rootCause()
                .hasMessageContaining("crowdsight.time-zone");
    }
}
