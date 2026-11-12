package com.tripley.crowdsight.timeline;

import java.util.List;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;

/** 타임라인 meta (파일당 1번). 이름 변환은 전역 SNAKE_CASE. */
@JsonIgnoreProperties(ignoreUnknown = true)
public record Meta(String zoneId, String cameraId, String videoId, int durationS, int intervalS,
                   double cellSizeM, Models models, Prediction prediction, List<CellMeta> cells) {
}
