package com.tripley.crowdsight.timeline;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;

/** 초별 셀 상태. density 외의 측정·예측 값은 null(관측 없음)일 수 있다. */
@JsonIgnoreProperties(ignoreUnknown = true)
public record CellState(String cellId, Double density, Double vx, Double vy, Double speedVar,
                        Double pressure, Double counterflow,
                        @JsonProperty("density_pred_60s") Double densityPred60s) {
}
