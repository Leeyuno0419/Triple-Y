package com.tripley.crowdsight.alert;

import java.util.List;

import com.tripley.crowdsight.grade.Grade;

/**
 * 발급한 알림 (api-spec 3.3). alert 메시지와 hello.unacked_alerts의 원본이다. 확인 기록(crowdsight.alert-log)의 sent_at은 frameTs다.
 *
 * @param alertId 알림 ID (a-yyyyMMdd-NNNN)
 * @param zoneId  구역 ID
 * @param t       알림이 생긴 프레임 t (같은 초 zone_state의 t)
 * @param frameTs 보낸 시각 (같은 초 zone_state의 frame_ts)
 * @param level   알림 등급
 * @param reason  알림 이유
 * @param message 한국어 문구
 * @param value   AlertEvent.value
 * @param cellIds 관련 셀 (meta 순서)
 */
public record Alert(String alertId, String zoneId, int t, String frameTs, Grade level, AlertReason reason,
                    String message, Double value, List<String> cellIds) {

    public Alert {
        cellIds = List.copyOf(cellIds);
    }
}
