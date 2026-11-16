package com.tripley.crowdsight.api;

import static com.tripley.crowdsight.timeline.TimelineFixtures.MAPPER;
import static com.tripley.crowdsight.timeline.TimelineFixtures.fixturePath;
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;

import com.tripley.crowdsight.config.CrowdsightProperties;
import com.tripley.crowdsight.config.TestProperties;
import com.tripley.crowdsight.replay.ZoneRegistry;
import com.tripley.crowdsight.timeline.TimelineLoader;

import tools.jackson.databind.JsonNode;

class ZoneControllerTest {

    private final CrowdsightProperties props = TestProperties.replay(1000, true);
    private final ZoneRegistry zones = new ZoneRegistry(new TimelineLoader(MAPPER, props), props);   // zone-test, 길이 5
    private final ZoneController controller = new ZoneController(zones);

    @Test
    @DisplayName("카메라·구역 목록에 zone·camera·video ID를 준다")
    void listsZones() {
        assertThat(controller.list()).containsExactly(new ZoneSummary("zone-test", "cam-test", "TEST_001"));
    }

    @Test
    @DisplayName("meta는 타임라인 원본을 그대로 준다")
    void metaReturnsOriginalTree() {
        ResponseEntity<JsonNode> response = controller.meta("zone-test");

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(response.getBody())
                .isSameAs(zones.find("zone-test").orElseThrow().player().timeline().metaJson())
                .isEqualTo(MAPPER.readTree(fixturePath()).get("meta"));
    }

    @Test
    @DisplayName("없는 구역 meta는 404")
    void metaUnknownZoneIs404() {
        ResponseEntity<JsonNode> response = controller.meta("zone-nope");

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.NOT_FOUND);
        assertThat(response.getBody()).isNull();
    }
}
