package com.tripley.crowdsight.ws.message;

import com.tripley.crowdsight.grade.DensityThresholds;

/**
 * hello.thresholds (api-spec 3.1). 표시용(범례·그래프 기준선)이고 판정은 서버가 한다.
 *
 * @param density     밀도 등급 기준 (crowdsight.grade.density)
 * @param pressure    군중 압력 기준 (crowdsight.instability.pressure)
 * @param inflowRatio 유입 비율 5초 평균 기준 (crowdsight.inflow.ratio). JSON 키 inflow_ratio
 */
public record ThresholdsView(DensityThresholds density, double pressure, double inflowRatio) {
}
