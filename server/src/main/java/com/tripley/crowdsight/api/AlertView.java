package com.tripley.crowdsight.api;

import java.util.List;

import com.tripley.crowdsight.alert.Alert;
import com.tripley.crowdsight.alert.AlertReason;
import com.tripley.crowdsight.alert.StoredAlert;
import com.tripley.crowdsight.grade.Grade;

/**
 * GET /api/zones/{zone_id}/alerts 원소. alert 메시지(api-spec 3.3)와 같은 키에 acked_at을 더한다.
 *
 * @param type    "alert" (화면이 alert 메시지와 같은 파서를 쓰도록)
 * @param alertId 알림 ID
 * @param zoneId  구역 ID
 * @param t       알림이 생긴 프레임 t
 * @param frameTs 보낸 시각
 * @param level   알림 등급
 * @param reason  알림 이유
 * @param message 한국어 문구
 * @param value   최대 밀도·유입 5초 평균·최대 압력
 * @param cellIds 관련 셀 (meta 순서)
 * @param ackedAt 처음 확인한 시각. 미확인이면 null
 */
public record AlertView(String type, String alertId, String zoneId, int t, String frameTs, Grade level,
                        AlertReason reason, String message, Double value, List<String> cellIds, String ackedAt) {

    public static final String TYPE = "alert";

    public AlertView {
        cellIds = List.copyOf(cellIds);
    }

    /** 보관 알림에서 만든다. */
    public static AlertView of(StoredAlert stored) {
        Alert a = stored.alert();
        return new AlertView(TYPE, a.alertId(), a.zoneId(), a.t(), a.frameTs(), a.level(), a.reason(), a.message(),
                a.value(), a.cellIds(), stored.ackedAt());
    }
}
