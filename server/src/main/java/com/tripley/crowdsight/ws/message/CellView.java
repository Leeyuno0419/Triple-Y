package com.tripley.crowdsight.ws.message;

import com.fasterxml.jackson.annotation.JsonProperty;
import com.tripley.crowdsight.grade.Grade;

/**
 * zone_state.cells[]. 측정·예측 값은 타임라인 그대로(null 포함), 서버는 grade·grade_pred_60s만 더한다.
 *
 * @param cellId         셀 ID
 * @param grade          셀 등급 (히스테리시스 거침)
 * @param density        밀도
 * @param vx             x 속도
 * @param vy             y 속도
 * @param speedVar       속도 분산
 * @param pressure       군중 압력
 * @param counterflow    역류 비율
 * @param densityPred60s 60초 뒤 예측 밀도
 * @param gradePred60s   예측 밀도의 등급
 */
public record CellView(String cellId, Grade grade, Double density, Double vx, Double vy, Double speedVar,
                       Double pressure, Double counterflow,
                       @JsonProperty("density_pred_60s") Double densityPred60s,
                       @JsonProperty("grade_pred_60s") Grade gradePred60s) {
}
