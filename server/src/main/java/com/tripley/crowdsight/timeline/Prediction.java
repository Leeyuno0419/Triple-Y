package com.tripley.crowdsight.timeline;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;

/** 예측 입력 기간과 예측 시점(초). */
@JsonIgnoreProperties(ignoreUnknown = true)
public record Prediction(int historyS, int horizonS) {
}
