package com.tripley.crowdsight.ws.message;

/**
 * 재생 상태가 바뀔 때 보내는 메시지 (api-spec 3.4). 반복으로 0이면 state playing, t 0.
 *
 * @param type   "playback"
 * @param zoneId 구역 ID
 * @param state  playing·paused·ended
 * @param t      재생 위치
 * @param loop   끝에서 처음으로 돌아가는지
 */
public record PlaybackMessage(String type, String zoneId, String state, int t, boolean loop) {

    public static final String TYPE = "playback";

    /** type을 "playback"으로 채운다. */
    public PlaybackMessage(String zoneId, String state, int t, boolean loop) {
        this(TYPE, zoneId, state, t, loop);
    }
}
