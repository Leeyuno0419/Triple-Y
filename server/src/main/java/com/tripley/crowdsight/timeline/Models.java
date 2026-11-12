package com.tripley.crowdsight.timeline;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;

/** 사용한 모델·방법 이름. 판정에 쓰지 않고 hello.meta로 전달만 한다. */
@JsonIgnoreProperties(ignoreUnknown = true)
public record Models(String counter, String flow, String predictor) {
}
