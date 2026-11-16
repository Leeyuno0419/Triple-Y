package com.tripley.crowdsight.api;

import static com.tripley.crowdsight.grade.Grade.ALERT;
import static com.tripley.crowdsight.timeline.TimelineFixtures.MAPPER;
import static org.assertj.core.api.Assertions.assertThat;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneId;
import java.util.List;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;

import com.tripley.crowdsight.alert.Alert;
import com.tripley.crowdsight.alert.AlertEvent;
import com.tripley.crowdsight.alert.AlertLogWriter;
import com.tripley.crowdsight.alert.AlertReason;
import com.tripley.crowdsight.alert.AlertStore;
import com.tripley.crowdsight.config.CrowdsightProperties;
import com.tripley.crowdsight.config.TestProperties;
import com.tripley.crowdsight.replay.ZoneRegistry;
import com.tripley.crowdsight.timeline.TimelineLoader;

class AlertControllerTest {

    private static final Clock FIXED = Clock.fixed(Instant.parse("2026-11-18T05:02:36.910Z"), ZoneId.of("Asia/Seoul"));
    private static final String ACKED_TS = "2026-11-18T14:02:36.910+09:00";
    private static final String SENT_TS = "2026-11-18T14:02:31.512+09:00";
    private static final String LOG_LINE = "{\"alert_id\":\"a-20261118-0001\",\"zone_id\":\"zone-test\",\"t\":3,"
            + "\"level\":\"ALERT\",\"reason\":\"GRADE_UP\",\"sent_at\":\"2026-11-18T14:02:31.512+09:00\","
            + "\"acked_at\":\"2026-11-18T14:02:36.910+09:00\"}";

    @TempDir
    Path dir;

    private Path logFile;
    private AlertStore store;
    private AlertLogWriter writer;
    private ZoneRegistry zones;
    private AlertController controller;

    @BeforeEach
    void setUp() {
        logFile = dir.resolve("alerts.jsonl");
        CrowdsightProperties props = TestProperties.alertLog(logFile.toString());
        store = new AlertStore(props, FIXED);
        writer = new AlertLogWriter(props, MAPPER);
        zones = new ZoneRegistry(new TimelineLoader(MAPPER, props), props);
        controller = new AlertController(store, writer, zones, FIXED);
    }

    private Alert issue() {
        return store.issue("zone-test", 3, SENT_TS,
                new AlertEvent(ALERT, AlertReason.GRADE_UP, "구역 등급이 주의 → 경계로 올랐다", 4.3, List.of("c-0000")));
    }

    private List<String> logLines() throws IOException {
        return Files.readAllLines(logFile, StandardCharsets.UTF_8);
    }

    @Test
    @DisplayName("처음 확인하면 고정 시각을 돌려주고 기록 한 줄을 쓴다")
    void ackReturnsAckedAtAndWritesLog() throws IOException {
        Alert alert = issue();

        ResponseEntity<AckResponse> response = controller.ack(alert.alertId());

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(response.getBody()).isEqualTo(new AckResponse(alert.alertId(), ACKED_TS));
        assertThat(logLines()).containsExactly(LOG_LINE);
    }

    @Test
    @DisplayName("다시 확인하면 처음 시각이고 기록을 더하지 않는다")
    void secondAckReturnsFirstTimeWithoutNewLine() throws IOException {
        Alert alert = issue();
        controller.ack(alert.alertId());
        AlertController later = new AlertController(store, writer, zones,
                Clock.fixed(Instant.parse("2026-11-18T05:02:40Z"), ZoneId.of("Asia/Seoul")));

        ResponseEntity<AckResponse> response = later.ack(alert.alertId());

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(response.getBody().ackedAt()).isEqualTo(ACKED_TS);
        assertThat(logLines()).hasSize(1);
    }

    @Test
    @DisplayName("없는 알림이면 404이고 기록 파일을 만들지 않는다")
    void unknownAlertIs404() {
        ResponseEntity<AckResponse> response = controller.ack("a-20261118-9999");

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.NOT_FOUND);
        assertThat(response.getBody()).isNull();
        assertThat(Files.notExists(logFile)).isTrue();
    }

    @Test
    @DisplayName("미확인만 고르면 확인한 알림이 빠진다")
    void listUnackedExcludesAcked() {
        Alert first = issue();
        Alert second = issue();
        controller.ack(first.alertId());

        ResponseEntity<List<AlertView>> response = controller.alerts("zone-test", true);

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(response.getBody()).singleElement().satisfies(view -> {
            assertThat(view.alertId()).isEqualTo(second.alertId());
            assertThat(view.ackedAt()).isNull();
            assertThat(view.type()).isEqualTo("alert");
        });
    }

    @Test
    @DisplayName("전체 목록은 확인 시각을 담아 발급 순으로 준다")
    void listAllIncludesAckedAt() {
        Alert first = issue();
        Alert second = issue();
        controller.ack(first.alertId());

        List<AlertView> body = controller.alerts("zone-test", false).getBody();

        assertThat(body).extracting(AlertView::alertId).containsExactly(first.alertId(), second.alertId());
        assertThat(body).extracting(AlertView::ackedAt).containsExactly(ACKED_TS, null);
    }

    @Test
    @DisplayName("없는 구역이면 404")
    void listUnknownZoneIs404() {
        assertThat(controller.alerts("zone-nope", false).getStatusCode()).isEqualTo(HttpStatus.NOT_FOUND);
    }

    @Test
    @DisplayName("알림이 없는 구역은 빈 목록")
    void listEmptyZoneIsEmptyArray() {
        ResponseEntity<List<AlertView>> response = controller.alerts("zone-test", true);

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(response.getBody()).isEmpty();
    }
}
