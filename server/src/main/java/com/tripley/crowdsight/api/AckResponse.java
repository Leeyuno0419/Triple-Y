package com.tripley.crowdsight.api;

/**
 * 알림 확인 응답 (api-spec 4.5).
 *
 * @param alertId 확인한 알림 ID
 * @param ackedAt 처음 확인한 시각 (frame_ts 형식)
 */
public record AckResponse(String alertId, String ackedAt) {
}
