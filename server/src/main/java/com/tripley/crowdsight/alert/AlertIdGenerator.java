package com.tripley.crowdsight.alert;

import java.time.Clock;
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.util.Locale;
import java.util.Objects;
import java.util.concurrent.atomic.AtomicLong;

/**
 * 알림 ID a-yyyyMMdd-NNNN (api-spec 3.3). 번호는 서버 시작부터 구역 공통으로 1씩 늘고 날짜가 바뀌어도 이어진다.
 * 날짜는 주입한 Clock의 시간대 날짜다. 9999 다음은 5자리가 된다.
 * 스레드 규칙: AtomicLong이라 여러 스레드에서 불러도 번호가 겹치지 않는다.
 */
final class AlertIdGenerator {

    private static final DateTimeFormatter DATE = DateTimeFormatter.ofPattern("uuuuMMdd");

    private final Clock clock;
    private final AtomicLong sequence = new AtomicLong();

    AlertIdGenerator(Clock clock) {
        this.clock = Objects.requireNonNull(clock, "clock");
    }

    /** 다음 알림 ID. */
    String next() {
        return "a-" + LocalDate.now(clock).format(DATE) + "-"
                + String.format(Locale.ROOT, "%04d", sequence.incrementAndGet());
    }
}
