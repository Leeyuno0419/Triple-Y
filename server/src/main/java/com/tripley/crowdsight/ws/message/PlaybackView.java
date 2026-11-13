package com.tripley.crowdsight.ws.message;

/**
 * hello.playback (api-spec 3.1).
 *
 * @param state     playing·paused·ended
 * @param t         마지막으로 준 프레임 (시작 전 0)
 * @param loop      끝에서 처음으로 돌아가는지
 * @param durationS 타임라인 길이(초)
 */
public record PlaybackView(String state, int t, boolean loop, int durationS) {
}
