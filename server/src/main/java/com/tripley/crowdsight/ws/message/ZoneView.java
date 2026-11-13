package com.tripley.crowdsight.ws.message;

import com.tripley.crowdsight.grade.Grade;

/**
 * zone_state.zone. inflowRatio·count는 타임라인 값 그대로, inflowAlert는 5초 평균 판정 (api-spec 4.4).
 *
 * @param grade       구역 등급
 * @param maxDensity  판정 대상 셀 밀도의 최댓값. 없으면 null
 * @param inflowRatio 유입 비율 (타임라인 값, null 가능)
 * @param inflowAlert 유입 경보 (ZoneEvaluation.inflowAlert)
 * @param count       인원 (타임라인 값, null 가능)
 */
public record ZoneView(Grade grade, Double maxDensity, Double inflowRatio, boolean inflowAlert, Double count) {
}
