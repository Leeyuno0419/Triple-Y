package com.tripley.crowdsight.alert;

import com.tripley.crowdsight.grade.Grade;

/**
 * 확인 기록 파일(crowdsight.alert-log) 한 줄 (api-spec 4.5). 키 순서는 성분 순서다.
 * 셀·구역 집계와 ID·시각만 담는다 (CLAUDE.md 데이터 규칙).
 *
 * @param alertId 알림 ID
 * @param zoneId  구역 ID
 * @param t       알림이 생긴 프레임 t
 * @param level   알림 등급
 * @param reason  알림 이유
 * @param sentAt  알림을 보낸 시각 (Alert.frameTs)
 * @param ackedAt 처음 확인한 시각
 */
public record AlertLogLine(String alertId, String zoneId, int t, Grade level, AlertReason reason, String sentAt,
                           String ackedAt) {

    /** 확인 결과에서 만든다. */
    public static AlertLogLine of(AlertAck ack) {
        Alert a = ack.alert();
        return new AlertLogLine(a.alertId(), a.zoneId(), a.t(), a.level(), a.reason(), a.frameTs(), ack.ackedAt());
    }
}
