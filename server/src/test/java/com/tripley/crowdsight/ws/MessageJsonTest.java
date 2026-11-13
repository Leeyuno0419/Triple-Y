package com.tripley.crowdsight.ws;

import static com.tripley.crowdsight.timeline.TimelineFixtures.MAPPER;
import static com.tripley.crowdsight.timeline.TimelineFixtures.timelineOf;
import static com.tripley.crowdsight.ws.MessageFactoryTest.FIXED;
import static com.tripley.crowdsight.ws.MessageFactoryTest.FIXED_TS;
import static com.tripley.crowdsight.ws.MessageFactoryTest.fixtureRuntime;
import static com.tripley.crowdsight.ws.MessageFactoryTest.fixtureTimeline;
import static com.tripley.crowdsight.ws.MessageFactoryTest.tickTimes;
import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import com.tripley.crowdsight.config.TestProperties;
import com.tripley.crowdsight.grade.ZoneGrader;
import com.tripley.crowdsight.replay.ZonePlayer;
import com.tripley.crowdsight.replay.ZoneRuntime;
import com.tripley.crowdsight.timeline.ZoneTimeline;
import com.tripley.crowdsight.ws.message.PlaybackMessage;

import tools.jackson.databind.JsonNode;

/** 메시지 JSON이 api-spec 3절 키·계획 7장 예시와 같은지 (Boot와 같은 SNAKE_CASE 매퍼). */
class MessageJsonTest {

    private static final String HELLO_SAMPLE = """
            {
              "type": "hello",
              "schema_version": "0.2",
              "zone_id": "zone-test",
              "meta": {
                "zone_id": "zone-test",
                "camera_id": "cam-test",
                "video_id": "TEST_001",
                "duration_s": 5,
                "interval_s": 1,
                "cell_size_m": 2.0,
                "models": { "counter": "fixture", "flow": "fixture", "predictor": "fixture" },
                "prediction": { "history_s": 2, "horizon_s": 60 },
                "cells": [
                  { "cell_id": "c-0000", "row": 0, "col": 0, "walkable_area_m2": 4.0,
                    "image_polygon": [[0.0, 0.0], [0.5, 0.0], [0.5, 0.5], [0.0, 0.5]] },
                  { "cell_id": "c-0001", "row": 0, "col": 1, "walkable_area_m2": 4.0,
                    "image_polygon": [[0.5, 0.0], [1.0, 0.0], [1.0, 0.5], [0.5, 0.5]] },
                  { "cell_id": "c-0102", "row": 1, "col": 2, "walkable_area_m2": 1.5,
                    "image_polygon": [[0.5, 0.5], [1.0, 0.5], [1.0, 1.0], [0.5, 1.0]] }
                ]
              },
              "playback": { "state": "playing", "t": 2, "loop": true, "duration_s": 5 },
              "thresholds": { "density": { "caution": 3.0, "alert": 4.0, "critical": 5.0 } },
              "unacked_alerts": []
            }
            """;

    private static final String ZONE_STATE_T0_SAMPLE = """
            {
              "type": "zone_state",
              "zone_id": "zone-test",
              "t": 0,
              "frame_ts": "2026-11-18T14:02:31.512+09:00",
              "zone": { "grade": "NORMAL", "max_density": 1.25, "inflow_ratio": null, "inflow_alert": false,
                        "count": 6.5 },
              "cells": [
                { "cell_id": "c-0000", "grade": "NORMAL", "density": 1.25, "vx": 0.1, "vy": 0.0, "speed_var": 0.004,
                  "pressure": 0.005, "counterflow": null, "density_pred_60s": null, "grade_pred_60s": null },
                { "cell_id": "c-0001", "grade": "NORMAL", "density": 0.0, "vx": null, "vy": null, "speed_var": null,
                  "pressure": 0.0, "counterflow": null, "density_pred_60s": null, "grade_pred_60s": null },
                { "cell_id": "c-0102", "grade": "NORMAL", "density": 1.0, "vx": 0.05, "vy": -0.02, "speed_var": 0.002,
                  "pressure": 0.002, "counterflow": null, "density_pred_60s": null, "grade_pred_60s": null }
              ]
            }
            """;

    private static final String ZONE_STATE_T4_SAMPLE = """
            {
              "type": "zone_state",
              "zone_id": "zone-test",
              "t": 4,
              "frame_ts": "2026-11-18T14:02:31.512+09:00",
              "zone": { "grade": "CAUTION", "max_density": 4.2, "inflow_ratio": 0.65, "inflow_alert": false,
                        "count": null },
              "cells": [
                { "cell_id": "c-0000", "grade": "CAUTION", "density": 4.2, "vx": 0.3, "vy": -0.1, "speed_var": 0.012,
                  "pressure": 0.0504, "counterflow": 0.25, "density_pred_60s": 4.6, "grade_pred_60s": "ALERT" },
                { "cell_id": "c-0001", "grade": "NORMAL", "density": 1.5, "vx": 0.2, "vy": 0.0, "speed_var": 0.006,
                  "pressure": 0.009, "counterflow": null, "density_pred_60s": 1.6, "grade_pred_60s": "NORMAL" },
                { "cell_id": "c-0102", "grade": "ALERT", "density": 5.5, "vx": 0.2, "vy": 0.1, "speed_var": 0.006,
                  "pressure": 0.033, "counterflow": null, "density_pred_60s": 5.9, "grade_pred_60s": "CRITICAL" }
              ]
            }
            """;

    private static final String PLAYBACK_SAMPLE = """
            { "type": "playback", "zone_id": "zone-test", "state": "playing", "t": 0, "loop": true }
            """;

    private final MessageFactory messages = new MessageFactory(FIXED, TestProperties.replay(1000, true));
    private ZoneRuntime runtime;

    private static String json(Object message) {
        return MAPPER.writeValueAsString(message);
    }

    private static JsonNode tree(Object message) {
        return MAPPER.readTree(json(message));
    }

    @BeforeEach
    void setUp() {
        runtime = fixtureRuntime(fixtureTimeline());
    }

    private String zoneStateJson(int ticks) {
        return json(messages.zoneState("zone-test", tickTimes(runtime, ticks), FIXED_TS));
    }

    @Test
    @DisplayName("hello 키는 api-spec 3.1과 같다")
    void helloKeys() {
        JsonNode root = tree(messages.hello(runtime));

        assertThat(root.propertyNames()).containsExactlyInAnyOrder("type", "schema_version", "zone_id", "meta",
                "playback", "thresholds", "unacked_alerts");
        assertThat(root.get("playback").propertyNames())
                .containsExactlyInAnyOrder("state", "t", "loop", "duration_s");
        assertThat(root.get("thresholds").propertyNames()).containsExactly("density");
        assertThat(root.get("thresholds").get("density").propertyNames())
                .containsExactlyInAnyOrder("caution", "alert", "critical");
        assertThat(root.get("unacked_alerts").isArray()).isTrue();
        assertThat(root.get("unacked_alerts").size()).isZero();
    }

    @Test
    @DisplayName("hello 출력이 7.1절 예시와 같다")
    void helloMatchesSample() {
        tickTimes(runtime, 3);

        assertThat(tree(messages.hello(runtime))).isEqualTo(MAPPER.readTree(HELLO_SAMPLE));
    }

    @Test
    @DisplayName("meta의 모르는 키도 그대로 보낸다")
    void helloMetaPassthrough() {
        ZoneTimeline base = timelineOf(5);
        ZoneTimeline withExtra = new ZoneTimeline(base.schemaVersion(), base.meta(), base.frames(),
                MAPPER.readTree("{\"foo\":1,\"zone_id\":\"zone-test\"}"), base.source());
        ZoneRuntime extra = new ZoneRuntime(new ZonePlayer(withExtra, true),
                new ZoneGrader(List.of(), TestProperties.GRADE));

        assertThat(tree(messages.hello(extra)).get("meta").get("foo").asInt()).isEqualTo(1);
    }

    @Test
    @DisplayName("zone_state·zone·cells 키는 api-spec 3.2와 같다")
    void zoneStateKeys() {
        JsonNode root = MAPPER.readTree(zoneStateJson(5));

        assertThat(root.propertyNames())
                .containsExactlyInAnyOrder("type", "zone_id", "t", "frame_ts", "zone", "cells");
        assertThat(root.get("zone").propertyNames())
                .containsExactlyInAnyOrder("grade", "max_density", "inflow_ratio", "inflow_alert", "count");
        for (JsonNode cell : root.get("cells").values()) {
            assertThat(cell.propertyNames()).containsExactlyInAnyOrder("cell_id", "grade", "density", "vx", "vy",
                    "speed_var", "pressure", "counterflow", "density_pred_60s", "grade_pred_60s");
            assertThat(cell.has("density_pred60s")).isFalse();
        }
    }

    @Test
    @DisplayName("null 값도 키를 빼지 않는다")
    void zoneStateKeepsNullKeys() {
        String json = zoneStateJson(1);

        assertThat(json).contains("\"inflow_ratio\":null", "\"vx\":null", "\"grade_pred_60s\":null");
        JsonNode cell = MAPPER.readTree(json).get("cells").get(1);
        assertThat(cell.has("counterflow")).isTrue();
        assertThat(cell.get("counterflow").isNull()).isTrue();
    }

    @Test
    @DisplayName("zone_state 출력이 7.2·7.3절 예시와 같다")
    void zoneStateMatchesSamples() {
        String t0 = zoneStateJson(1);
        String t4 = json(messages.zoneState("zone-test", tickTimes(runtime, 4), FIXED_TS));

        assertThat(MAPPER.readTree(t0)).isEqualTo(MAPPER.readTree(ZONE_STATE_T0_SAMPLE));
        assertThat(MAPPER.readTree(t4)).isEqualTo(MAPPER.readTree(ZONE_STATE_T4_SAMPLE));
        assertThat(t0).startsWith("{\"type\":\"zone_state\",\"zone_id\":\"zone-test\",\"t\":");
    }

    @Test
    @DisplayName("playback 키는 api-spec 3.4와 같다")
    void playbackKeys() {
        JsonNode root = tree(new PlaybackMessage("zone-test", "playing", 0, true));

        assertThat(root).isEqualTo(MAPPER.readTree(PLAYBACK_SAMPLE));
        assertThat(root.propertyNames()).containsExactlyInAnyOrder("type", "zone_id", "state", "t", "loop");
    }
}
