package com.tripley.crowdsight.alert;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneId;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

class AlertIdGeneratorTest {

    private static final Clock FIXED = Clock.fixed(Instant.parse("2026-11-18T05:02:31.512Z"),
            ZoneId.of("Asia/Seoul"));

    @Test
    @DisplayName("ID는 a-날짜-4자리 번호이고 1부터 늘어난다")
    void formatAndSequence() {
        AlertIdGenerator ids = new AlertIdGenerator(FIXED);

        assertThat(ids.next()).isEqualTo("a-20261118-0001");
        assertThat(ids.next()).isEqualTo("a-20261118-0002");
    }

    @Test
    @DisplayName("날짜는 시계 시간대 기준이다")
    void dateUsesClockZone() {
        Clock lateUtc = Clock.fixed(Instant.parse("2026-11-17T15:30:00Z"), ZoneId.of("Asia/Seoul"));

        assertThat(new AlertIdGenerator(lateUtc).next()).isEqualTo("a-20261118-0001");
    }

    @Test
    @DisplayName("9999 다음은 5자리 번호다")
    void widensAfter9999() {
        AlertIdGenerator ids = new AlertIdGenerator(FIXED);
        String last = null;
        for (int i = 0; i < 10000; i++) {
            last = ids.next();
        }

        assertThat(last).isEqualTo("a-20261118-10000");
    }
}
