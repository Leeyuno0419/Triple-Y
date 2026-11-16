package com.tripley.crowdsight.replay;

/**
 * tick 결과를 화면으로 내보내는 곳. ws 패키지가 구현한다.
 * replay가 ws에 의존하지 않도록 인터페이스를 여기 둔다 (의존 방향 ws → replay).
 * 스레드 규칙: ReplayScheduler의 재생 작업에서만 부른다. 한 tick 안에서는 playback → zoneState 순서다.
 */
public interface ZoneBroadcaster {

    /** 재생 상태가 바뀌었다 (반복으로 0, 끝). */
    void playback(String zoneId, PlaybackSnapshot snapshot);

    /** 한 초 판정 결과와 그 초 알림(step.alerts()). 구현은 같은 frame_ts로 zone_state 다음 alert를 보낸다. */
    void zoneState(String zoneId, ZoneStep step);
}
