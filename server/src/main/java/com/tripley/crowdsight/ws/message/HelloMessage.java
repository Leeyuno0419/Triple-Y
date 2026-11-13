package com.tripley.crowdsight.ws.message;

import java.util.List;

import tools.jackson.databind.JsonNode;

/**
 * 접속 직후 1번 보내는 메시지 (api-spec 3.1).
 *
 * @param type          "hello"
 * @param schemaVersion API 메시지 버전 (타임라인 파일 버전과 별개)
 * @param zoneId        구역 ID
 * @param meta          타임라인 meta 원본 트리 그대로 (모르는 키 포함)
 * @param playback      지금 재생 상태
 * @param thresholds    표시용 기준값 (density, pressure, inflow_ratio)
 * @param unackedAlerts 미확인 알림 (오래된 것부터, api-spec 3.1)
 */
public record HelloMessage(String type, String schemaVersion, String zoneId, JsonNode meta, PlaybackView playback,
                           ThresholdsView thresholds, List<AlertMessage> unackedAlerts) {

    public static final String TYPE = "hello";

    public HelloMessage {
        unackedAlerts = List.copyOf(unackedAlerts);
    }

    /** type을 "hello"로 채운다. */
    public HelloMessage(String schemaVersion, String zoneId, JsonNode meta, PlaybackView playback,
                        ThresholdsView thresholds, List<AlertMessage> unackedAlerts) {
        this(TYPE, schemaVersion, zoneId, meta, playback, thresholds, unackedAlerts);
    }
}
