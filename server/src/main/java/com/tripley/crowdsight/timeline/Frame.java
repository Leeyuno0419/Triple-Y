package com.tripley.crowdsight.timeline;

import java.util.List;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;

/** 1초 프레임. v0.1 파일이면 count는 null로 읽는다. */
@JsonIgnoreProperties(ignoreUnknown = true)
public record Frame(int t, Double inflowRatio, Double count, List<CellState> cells) {
}
