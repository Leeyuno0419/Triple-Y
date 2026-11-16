package com.tripley.crowdsight.api;

import static com.tripley.crowdsight.timeline.TimelineFixtures.MAPPER;
import static org.assertj.core.api.Assertions.assertThat;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.regex.Pattern;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.assertj.MockMvcTester;
import org.springframework.test.web.servlet.assertj.MvcTestResult;

import com.tripley.crowdsight.alert.Alert;
import com.tripley.crowdsight.alert.AlertEvent;
import com.tripley.crowdsight.alert.AlertReason;
import com.tripley.crowdsight.alert.AlertStore;
import com.tripley.crowdsight.grade.Grade;

import tools.jackson.databind.JsonNode;

@SpringBootTest(properties = {
        "crowdsight.timeline-dir=src/test/resources/timeline",
        "crowdsight.timeline-files=valid_v02.json",
        "crowdsight.alert-log=build/test-logs/alerts.jsonl"
})
@AutoConfigureMockMvc
class AlertControllerIntegrationTest {

    private static final Path LOG = Path.of("build/test-logs/alerts.jsonl");
    private static final Pattern TS = Pattern.compile("\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}\\.\\d{3}\\+09:00");
    private static final String MESSAGE = "구역 등급이 주의 → 경계로 올랐다";

    @Autowired
    private MockMvcTester mvc;

    @Autowired
    private AlertStore alerts;

    @BeforeEach
    void clearLog() throws IOException {
        Files.deleteIfExists(LOG);
    }

    private Alert issue() {
        return alerts.issue("zone-test", 3, "2026-11-18T14:02:31.512+09:00",
                new AlertEvent(Grade.ALERT, AlertReason.GRADE_UP, MESSAGE, 4.3, List.of("c-0000")));
    }

    private static JsonNode json(MvcTestResult result) throws Exception {
        return MAPPER.readTree(result.getResponse().getContentAsString(StandardCharsets.UTF_8));
    }

    @Test
    @DisplayName("HTTP로 확인하면 alert_id·acked_at을 돌려주고 기록 파일에 한 줄을 쓴다")
    void ackOverHttp() throws Exception {
        Alert alert = issue();

        MvcTestResult result = mvc.post().uri("/api/alerts/{id}/ack", alert.alertId()).exchange();

        assertThat(result).hasStatusOk();
        assertThat(MediaType.parseMediaType(result.getResponse().getContentType()))
                .matches(type -> type.isCompatibleWith(MediaType.APPLICATION_JSON));
        JsonNode body = json(result);
        assertThat(body.propertyNames()).containsExactly("alert_id", "acked_at");
        assertThat(body.get("alert_id").asString()).isEqualTo(alert.alertId());
        assertThat(body.get("acked_at").asString()).matches(TS);

        List<String> lines = Files.readAllLines(LOG, StandardCharsets.UTF_8);
        assertThat(lines).hasSize(1);
        JsonNode line = MAPPER.readTree(lines.get(0));
        assertThat(line.propertyNames())
                .containsExactly("alert_id", "zone_id", "t", "level", "reason", "sent_at", "acked_at");
        assertThat(line.get("alert_id").asString()).isEqualTo(alert.alertId());
        assertThat(line.get("acked_at").asString()).isEqualTo(body.get("acked_at").asString());
    }

    @Test
    @DisplayName("없는 알림 확인은 404")
    void ackUnknownOverHttpIs404() {
        assertThat(mvc.post().uri("/api/alerts/a-19990101-0001/ack")).hasStatus(404);
        assertThat(LOG).doesNotExist();
    }

    @Test
    @DisplayName("미확인 목록에서 확인한 알림이 빠지고 원소 키가 정해져 있다")
    void listUnackedOverHttp() throws Exception {
        Alert first = issue();
        Alert second = issue();
        assertThat(mvc.post().uri("/api/alerts/{id}/ack", first.alertId())).hasStatusOk();

        MvcTestResult result = mvc.get().uri("/api/zones/zone-test/alerts?unacked=true").exchange();

        assertThat(result).hasStatusOk();
        JsonNode body = json(result);
        List<JsonNode> items = body.valueStream().toList();
        assertThat(items).extracting(n -> n.get("alert_id").asString())
                .contains(second.alertId()).doesNotContain(first.alertId());
        JsonNode item = items.stream().filter(n -> n.get("alert_id").asString().equals(second.alertId()))
                .findFirst().orElseThrow();
        assertThat(item.propertyNames()).containsExactly("type", "alert_id", "zone_id", "t", "frame_ts", "level",
                "reason", "message", "value", "cell_ids", "acked_at");
        assertThat(item.get("message").asString()).isEqualTo(MESSAGE);
        assertThat(item.get("acked_at").isNull()).isTrue();
    }

    @Test
    @DisplayName("unacked 값이 불리언이 아니면 400")
    void invalidUnackedParamIs400() {
        assertThat(mvc.get().uri("/api/zones/zone-test/alerts?unacked=abc")).hasStatus(400);
    }

    @Test
    @DisplayName("없는 구역 알림 목록은 404")
    void listUnknownZoneOverHttpIs404() {
        assertThat(mvc.get().uri("/api/zones/zone-nope/alerts")).hasStatus(404);
    }

    @ParameterizedTest
    @ValueSource(strings = {"http://localhost:5173", "http://127.0.0.1:5173"})
    @DisplayName("허용 출처의 사전 요청을 받아 준다")
    void corsPreflightAllowsLocalOrigin(String origin) {
        assertThat(mvc.options().uri("/api/alerts/x/ack")
                .header(HttpHeaders.ORIGIN, origin)
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "POST"))
                .hasStatusOk()
                .hasHeader(HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN, origin);
    }

    @Test
    @DisplayName("허용하지 않는 출처는 403")
    void corsRejectsForeignOrigin() {
        assertThat(mvc.options().uri("/api/alerts/x/ack")
                .header(HttpHeaders.ORIGIN, "http://example.com")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "POST"))
                .hasStatus(403);
    }
}
