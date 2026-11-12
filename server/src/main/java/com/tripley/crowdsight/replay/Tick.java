package com.tripley.crowdsight.replay;

import com.tripley.crowdsight.timeline.Frame;

/**
 * tick 한 번의 결과.
 *
 * @param frame         이번에 재생한 프레임
 * @param discontinuity 첫 프레임·반복·이동(S7) 직후. 판정 상태를 초기화한다 (S2)
 * @param wrapped       반복으로 0으로 돌아옴. playback(playing, 0)을 먼저 보낸다 (S3)
 */
public record Tick(Frame frame, boolean discontinuity, boolean wrapped) {
}
