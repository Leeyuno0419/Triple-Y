package com.tripley.crowdsight.alert;

/** 알림 이유 (api-spec 3.3). JSON에는 이름 그대로 나간다. */
public enum AlertReason {
    /** 구역 등급이 경계·심각으로 오름. */
    GRADE_UP,
    /** 유입 경보가 켜짐. */
    INFLOW,
    /** 판정 대상 셀 중 하나라도 불안정이 됨 (구역 단위). */
    INSTABILITY
}
