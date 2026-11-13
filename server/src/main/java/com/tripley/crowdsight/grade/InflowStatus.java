package com.tripley.crowdsight.grade;

/**
 * 한 초의 유입 판정 결과.
 *
 * @param average 최근 windowSeconds초 inflow_ratio 평균. 창이 덜 찼거나 non-null 값이 minSamples개 미만이면 null
 * @param on      유입 경보가 켜져 있는지
 */
public record InflowStatus(Double average, boolean on) {
}
