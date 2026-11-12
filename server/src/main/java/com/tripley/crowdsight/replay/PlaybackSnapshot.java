package com.tripley.crowdsight.replay;

/**
 * 재생 상태 한 시점. hello.playback·playback 메시지용 (S3).
 *
 * @param state     재생 상태
 * @param t         마지막으로 준 프레임 (시작 전 0)
 * @param loop      끝에서 처음으로 돌아가는지
 * @param durationS 타임라인 길이(초)
 */
public record PlaybackSnapshot(PlaybackState state, int t, boolean loop, int durationS) {
}
