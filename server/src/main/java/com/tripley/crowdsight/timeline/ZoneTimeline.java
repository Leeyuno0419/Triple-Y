package com.tripley.crowdsight.timeline;

import java.nio.file.Path;
import java.util.List;

import tools.jackson.databind.JsonNode;

/**
 * 구역 1개의 검증된 타임라인. 만든 뒤 바꾸지 않는다 (metaJson도 읽기만 한다).
 *
 * @param schemaVersion 파일의 schema_version. "0.1"이면 count·counterflow는 null로 읽었다
 * @param meta          고정 정보
 * @param frames        t=0부터 1초마다 1개. 개수 = duration_s
 * @param metaJson      원본 meta 트리. S3에서 hello.meta로 그대로 보낸다 (모르는 키 포함, api-spec 3.1)
 * @param source        읽은 파일의 절대 경로
 */
public record ZoneTimeline(String schemaVersion, Meta meta, List<Frame> frames, JsonNode metaJson, Path source) {

    public ZoneTimeline {
        frames = List.copyOf(frames);
    }

    /** 구역 ID (meta.zone_id). */
    public String zoneId() {
        return meta.zoneId();
    }

    /** 프레임 수(초). */
    public int durationS() {
        return frames.size();
    }
}
