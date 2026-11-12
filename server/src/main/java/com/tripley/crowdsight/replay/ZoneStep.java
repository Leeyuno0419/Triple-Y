package com.tripley.crowdsight.replay;

import com.tripley.crowdsight.grade.ZoneEvaluation;

/**
 * 구역 1개의 tick 한 번 결과.
 *
 * @param tick       재생 결과. S3가 wrapped(→ playback)와 통과 필드(inflow_ratio·count)에 쓴다
 * @param evaluation 이번 프레임 판정
 */
public record ZoneStep(Tick tick, ZoneEvaluation evaluation) {
}
