package com.tripley.crowdsight.ws;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneId;
import java.time.ZoneOffset;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

class FrameTimestampsTest {

    private static final ZoneId SEOUL = ZoneId.of("Asia/Seoul");

    private static String at(String instant, ZoneId zone) {
        return FrameTimestamps.now(Clock.fixed(Instant.parse(instant), zone));
    }

    @Test
    @DisplayName("밀리초 3자리와 +09:00을 붙인다")
    void formatsMillisAndOffset() {
        assertThat(at("2026-11-18T05:02:31.512Z", SEOUL)).isEqualTo("2026-11-18T14:02:31.512+09:00");
    }

    @Test
    @DisplayName("밀리초가 0이면 .000으로 적는다")
    void padsWholeSecond() {
        assertThat(at("2026-11-18T05:02:31Z", SEOUL)).isEqualTo("2026-11-18T14:02:31.000+09:00");
    }

    @Test
    @DisplayName("밀리초 아래는 버린다")
    void truncatesBelowMillis() {
        assertThat(at("2026-11-18T05:02:31.512999999Z", SEOUL)).isEqualTo("2026-11-18T14:02:31.512+09:00");
    }

    @Test
    @DisplayName("시간대 기준으로 날짜가 넘어간다")
    void rollsDateInZone() {
        assertThat(at("2026-11-18T15:30:00.007Z", SEOUL)).isEqualTo("2026-11-19T00:30:00.007+09:00");
    }

    @Test
    @DisplayName("오프셋 0이면 Z로 적는다")
    void utcWritesZ() {
        assertThat(at("2026-11-18T05:02:31.512Z", ZoneOffset.UTC)).isEqualTo("2026-11-18T05:02:31.512Z");
    }
}
