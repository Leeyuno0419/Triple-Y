package com.tripley.crowdsight.ws;

import static org.assertj.core.api.Assertions.assertThat;

import java.net.URI;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;
import org.junit.jupiter.params.provider.ValueSource;

class ZoneWebSocketHandlerTest {

    @ParameterizedTest
    @CsvSource({"/ws/zones/zone-test,zone-test", "/ws/zones/zone-e04-039,zone-e04-039"})
    @DisplayName("경로에서 구역 ID를 꺼낸다")
    void parsesZoneId(String path, String expected) {
        assertThat(ZoneWebSocketHandler.zoneIdOf(URI.create("ws://localhost:8080" + path))).contains(expected);
    }

    @ParameterizedTest
    @ValueSource(strings = {"/ws/zones/", "/ws/other/zone-test", "/ws/zones"})
    @DisplayName("구역 ID가 없거나 다른 경로면 빈 값")
    void emptyForOtherPaths(String path) {
        assertThat(ZoneWebSocketHandler.zoneIdOf(URI.create("ws://localhost:8080" + path))).isEmpty();
        assertThat(ZoneWebSocketHandler.zoneIdOf(null)).isEmpty();
    }
}
