package com.tripley.crowdsight.ws.message;

import com.tripley.crowdsight.grade.DensityThresholds;

/**
 * hello.thresholds. S4가 pressure·inflowRatio 성분을 더한다.
 *
 * @param density 밀도 등급 기준 (crowdsight.grade.density)
 */
public record ThresholdsView(DensityThresholds density) {
}
