package com.tripley.crowdsight.alert;

import java.util.List;
import java.util.Objects;

import com.tripley.crowdsight.grade.Grade;

/**
 * 한 초에 새로 생긴 알림 사건. ID·frame_ts·구역은 아직 없다 (AlertStore.issue가 붙인다).
 *
 * @param level   알림 등급 (GRADE_UP: 오른 등급, INFLOW: CAUTION, INSTABILITY: CRITICAL)
 * @param reason  알림 이유
 * @param message 화면에 보일 한국어 문구
 * @param value   GRADE_UP: 최대 밀도, INFLOW: 유입 비율 5초 평균(소수 3자리), INSTABILITY: 불안정 셀 최대 압력.
 *                방어용으로 null일 수 있다
 * @param cellIds 관련 판정 대상 셀 (meta 순서). INFLOW는 빈 목록
 */
public record AlertEvent(Grade level, AlertReason reason, String message, Double value, List<String> cellIds) {

    public AlertEvent {
        Objects.requireNonNull(level, "level");
        Objects.requireNonNull(reason, "reason");
        Objects.requireNonNull(message, "message");
        cellIds = List.copyOf(cellIds);
    }
}
