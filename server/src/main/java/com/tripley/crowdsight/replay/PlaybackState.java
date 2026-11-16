package com.tripley.crowdsight.replay;

/** 구역 재생 상태. playback 메시지에서는 소문자로 보낸다. 실시간 CCTV처럼 재생하므로 화면이 바꾸지 않는다. */
public enum PlaybackState {
    PLAYING, ENDED
}
