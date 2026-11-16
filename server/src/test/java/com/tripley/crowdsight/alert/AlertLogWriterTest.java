package com.tripley.crowdsight.alert;

import static com.tripley.crowdsight.grade.Grade.ALERT;
import static com.tripley.crowdsight.timeline.TimelineFixtures.MAPPER;
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatNoException;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import com.tripley.crowdsight.config.TestProperties;

class AlertLogWriterTest {

    private static final String SENT_TS = "2026-11-18T14:02:31.512+09:00";
    private static final String ACKED_TS = "2026-11-18T14:02:36.910+09:00";

    @TempDir
    Path dir;

    private static AlertAck ack(String alertId) {
        return new AlertAck(new Alert(alertId, "zone-test", 3, SENT_TS, ALERT, AlertReason.GRADE_UP,
                "구역 등급이 주의 → 경계로 올랐다", 4.3, List.of("c-0000")), ACKED_TS, true);
    }

    private static AlertLogWriter writer(Path path) {
        return new AlertLogWriter(TestProperties.alertLog(path.toString()), MAPPER);
    }

    @Test
    @DisplayName("폴더가 없어도 만들고 JSON 한 줄을 쓴다")
    void appendCreatesFileAndWritesOneLine() throws IOException {
        Path path = dir.resolve("logs").resolve("alerts.jsonl");

        writer(path).append(ack("a-20261118-0001"));

        assertThat(Files.readString(path, StandardCharsets.UTF_8)).isEqualTo("{\"alert_id\":\"a-20261118-0001\","
                + "\"zone_id\":\"zone-test\",\"t\":3,\"level\":\"ALERT\",\"reason\":\"GRADE_UP\","
                + "\"sent_at\":\"2026-11-18T14:02:31.512+09:00\",\"acked_at\":\"2026-11-18T14:02:36.910+09:00\"}\n");
    }

    @Test
    @DisplayName("덧붙이고 앞 줄을 지우지 않는다")
    void appendKeepsEarlierLines() throws IOException {
        Path path = dir.resolve("alerts.jsonl");
        Files.writeString(path, "{\"old\":1}\n", StandardCharsets.UTF_8);
        AlertLogWriter writer = writer(path);

        writer.append(ack("a-20261118-0001"));
        writer.append(ack("a-20261118-0002"));

        List<String> lines = Files.readAllLines(path, StandardCharsets.UTF_8);
        assertThat(lines).hasSize(3);
        assertThat(lines.get(0)).isEqualTo("{\"old\":1}");
        assertThat(MAPPER.readTree(lines.get(2)).get("alert_id").asString()).isEqualTo("a-20261118-0002");
    }

    @Test
    @DisplayName("줄 끝은 LF이고 CR이 없다")
    void appendUsesLfOnly() throws IOException {
        Path path = dir.resolve("alerts.jsonl");
        AlertLogWriter writer = writer(path);

        writer.append(ack("a-20261118-0001"));
        writer.append(ack("a-20261118-0002"));

        String content = Files.readString(path, StandardCharsets.UTF_8);
        assertThat(content).doesNotContain("\r");
        assertThat(content.chars().filter(c -> c == '\n').count()).isEqualTo(2);
    }

    @Test
    @DisplayName("쓰지 못해도 예외를 내지 않는다")
    void appendFailureDoesNotThrow() throws IOException {
        Path blocker = Files.writeString(dir.resolve("blocker"), "x", StandardCharsets.UTF_8);
        AlertLogWriter writer = writer(blocker.resolve("alerts.jsonl"));

        assertThatNoException().isThrownBy(() -> writer.append(ack("a-20261118-0001")));
        assertThat(blocker).isRegularFile();
    }
}
