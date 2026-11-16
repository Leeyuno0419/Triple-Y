package com.tripley.crowdsight.ws.message;

import java.util.List;

import com.tripley.crowdsight.alert.AlertReason;
import com.tripley.crowdsight.grade.Grade;

/**
 * 알림 메시지 (api-spec 3.3). 사건이 생긴 초에 그 초 zone_state 다음으로 보내고, hello.unacked_alerts에도 담는다.
 *
 * @param type    "alert"
 * @param alertId 알림 ID
 * @param zoneId  구역 ID
 * @param t       같은 초 zone_state의 t
 * @param frameTs 같은 초 zone_state의 frame_ts
 * @param level   알림 등급
 * @param reason  GRADE_UP·INFLOW·INSTABILITY
 * @param message 한국어 문구
 * @param value   최대 밀도·유입 5초 평균·최대 압력
 * @param cellIds 관련 셀 (meta 순서). INFLOW는 빈 배열
 */
public record AlertMessage(String type, String alertId, String zoneId, int t, String frameTs, Grade level,
                           AlertReason reason, String message, Double value, List<String> cellIds) {

    public static final String TYPE = "alert";

    public AlertMessage {
        cellIds = List.copyOf(cellIds);
    }

    /** type을 "alert"로 채운다. */
    public AlertMessage(String alertId, String zoneId, int t, String frameTs, Grade level, AlertReason reason,
                        String message, Double value, List<String> cellIds) {
        this(TYPE, alertId, zoneId, t, frameTs, level, reason, message, value, cellIds);
    }
}
