package com.tripley.crowdsight.ws;

import java.time.Clock;
import java.time.ZonedDateTime;
import java.time.format.DateTimeFormatter;

/** frame_ts 형식: ISO 8601, 밀리초 3자리, 오프셋 (예: 2026-11-18T14:02:31.512+09:00, api-spec 1절). */
public final class FrameTimestamps {

    private static final DateTimeFormatter FORMAT = DateTimeFormatter.ofPattern("uuuu-MM-dd'T'HH:mm:ss.SSSXXX");

    private FrameTimestamps() {
    }

    /** clock의 지금 시각을 clock의 시간대로 적는다. 밀리초 아래는 버린다. 오프셋이 0이면 Z로 적는다. */
    public static String now(Clock clock) {
        return FORMAT.format(ZonedDateTime.now(clock));
    }
}
