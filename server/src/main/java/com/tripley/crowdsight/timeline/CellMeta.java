package com.tripley.crowdsight.timeline;

import java.util.List;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;

/** 셀 고정 정보. imagePolygon은 0~1 좌표 4개. */
@JsonIgnoreProperties(ignoreUnknown = true)
public record CellMeta(String cellId, int row, int col, double walkableAreaM2, List<List<Double>> imagePolygon) {
}
