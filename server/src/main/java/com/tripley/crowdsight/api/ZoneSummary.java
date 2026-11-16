package com.tripley.crowdsight.api;

import com.tripley.crowdsight.timeline.Meta;
import com.tripley.crowdsight.timeline.ZoneTimeline;

/**
 * GET /api/zones 원소. 카메라 한 대 = 구역 하나 (실시간 CCTV 흉내).
 *
 * @param zoneId   구역 ID
 * @param cameraId 카메라 ID (CLAUDE.md: API에 처음부터 zone_id·camera_id)
 * @param videoId  영상(피드) ID. 화면이 영상 파일을 찾는다 (api-spec 6절)
 */
public record ZoneSummary(String zoneId, String cameraId, String videoId) {

    /** 타임라인 meta에서 만든다. */
    public static ZoneSummary of(ZoneTimeline timeline) {
        Meta m = timeline.meta();
        return new ZoneSummary(m.zoneId(), m.cameraId(), m.videoId());
    }
}
