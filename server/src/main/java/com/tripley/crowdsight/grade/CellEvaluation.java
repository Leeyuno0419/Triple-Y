package com.tripley.crowdsight.grade;

import com.tripley.crowdsight.timeline.CellState;

/**
 * 셀 하나의 한 초 판정 결과.
 *
 * @param cellId       셀 ID
 * @param grade        히스테리시스를 거친 셀 등급. 판정 대상이 아닌 작은 셀도 계산한다 (api-spec 3.2)
 * @param gradePred60s density_pred_60s의 등급 (히스테리시스 없음). 예측이 null이면 null
 * @param eligible     판정 대상(walkable_area_m2 ≥ min-walkable-area-m2)인지. 구역 등급·max_density에만 쓴다
 * @param state        타임라인 셀 값 그대로 (S3 zone_state cells[]로 옮김)
 */
public record CellEvaluation(String cellId, Grade grade, Grade gradePred60s, boolean eligible, CellState state) {
}
