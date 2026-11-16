package com.tripley.crowdsight.api;

import static com.tripley.crowdsight.timeline.TimelineFixtures.MAPPER;
import static com.tripley.crowdsight.timeline.TimelineFixtures.fixturePath;
import static org.assertj.core.api.Assertions.assertThat;
import static org.awaitility.Awaitility.await;

import java.nio.charset.StandardCharsets;
import java.time.Duration;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.servlet.assertj.MockMvcTester;
import org.springframework.test.web.servlet.assertj.MvcTestResult;

import tools.jackson.databind.JsonNode;

@SpringBootTest(properties = {
        "crowdsight.timeline-dir=src/test/resources/timeline",
        "crowdsight.timeline-files=valid_v02.json",
        "crowdsight.alert-log=build/test-logs/alerts.jsonl"
})
@AutoConfigureMockMvc
class ZoneControllerIntegrationTest {

    private static final String DEV_ORIGIN = "http://localhost:5173";

    @Autowired
    private MockMvcTester mvc;

    private static JsonNode json(MvcTestResult result) throws Exception {
        return MAPPER.readTree(result.getResponse().getContentAsString(StandardCharsets.UTF_8));
    }

    @Test
    @DisplayName("구역 목록 키가 정해져 있다")
    void listZonesOverHttp() throws Exception {
        MvcTestResult result = mvc.get().uri("/api/zones").exchange();

        assertThat(result).hasStatusOk();
        JsonNode body = json(result);
        assertThat(body.size()).isEqualTo(1);
        JsonNode zone = body.get(0);
        assertThat(zone.propertyNames()).containsExactly("zone_id", "camera_id", "video_id");
        assertThat(zone.get("zone_id").asString()).isEqualTo("zone-test");
        assertThat(zone.get("camera_id").asString()).isEqualTo("cam-test");
        assertThat(zone.get("video_id").asString()).isEqualTo("TEST_001");
    }

    @Test
    @DisplayName("meta를 원본 그대로 준다")
    void metaOverHttp() throws Exception {
        MvcTestResult result = mvc.get().uri("/api/zones/zone-test/meta").exchange();

        assertThat(result).hasStatusOk();
        assertThat(json(result)).isEqualTo(MAPPER.readTree(fixturePath()).get("meta"));
    }

    @Test
    @DisplayName("없는 구역 meta는 404이고 본문이 없다")
    void metaUnknownZoneIs404() {
        MvcTestResult result = mvc.get().uri("/api/zones/zone-nope/meta").exchange();

        assertThat(result).hasStatus(404);
        assertThat(result.getResponse().getContentAsByteArray()).isEmpty();
    }

    @Test
    @DisplayName("health 키가 정해져 있고 처리 시간이 찍힌다")
    void healthOverHttp() throws Exception {
        await().atMost(Duration.ofSeconds(3))
                .until(() -> !json(mvc.get().uri("/api/health").exchange()).get("last_tick_ms").isNull());

        MvcTestResult result = mvc.get().uri("/api/health").exchange();

        assertThat(result).hasStatusOk();
        JsonNode body = json(result);
        assertThat(body.propertyNames())
                .containsExactly("status", "zones", "sessions", "last_tick_ms", "max_tick_ms");
        assertThat(body.get("status").asString()).isEqualTo("UP");
        JsonNode zone = body.get("zones").get(0);
        assertThat(zone.propertyNames()).containsExactly("zone_id", "state", "t", "loop");
        assertThat(zone.get("state").asString()).isEqualTo("playing");
        assertThat(body.get("sessions").asInt()).isEqualTo(0);
    }

    @Test
    @DisplayName("허용 출처의 조회에 CORS 헤더를 준다")
    void corsAllowsDevOrigin() {
        assertThat(mvc.get().uri("/api/zones").header(HttpHeaders.ORIGIN, DEV_ORIGIN))
                .hasStatusOk()
                .hasHeader(HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN, DEV_ORIGIN);
    }
}
