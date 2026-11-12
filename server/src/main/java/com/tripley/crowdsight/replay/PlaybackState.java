package com.tripley.crowdsight.replay;

/** 구역 재생 상태. playback 메시지에서는 소문자로 보낸다 (S3). PAUSED는 S7에서 처음 쓴다. */
public enum PlaybackState {
    PLAYING, PAUSED, ENDED
}
