package com.tripley.crowdsight.grade;

import java.util.Objects;

/**
 * 셀 하나의 불안정 판정 (api-spec 4.3). pressure가 기준을 seconds초 연속 넘으면(초과) 불안정이다.
 * pressure가 null(관측 없음)이거나 기준 이하이면 연속을 0으로 되돌린다. 조건이 깨진 초에 바로 false가 된다.
 * 심각 등급이 얼마나 남는지는 GradeHysteresis 내림 규칙이 정한다 (별도 유지 타이머 없음).
 * 스레드 규칙: 재생 스레드 하나만 부른다. 잠금 없음.
 */
public final class InstabilityTracker {

    private final double threshold;
    private final int seconds;
    private int streak;   // 기준을 넘은 연속 초. seconds에서 멈춘다

    /** @param settings 불안정 설정 (값 검사는 InstabilitySettings가 한다) */
    public InstabilityTracker(InstabilitySettings settings) {
        Objects.requireNonNull(settings, "settings");
        this.threshold = settings.pressure();
        this.seconds = settings.seconds();
    }

    /** 이번 초의 pressure를 반영하고 불안정이면 true를 돌려준다. */
    public boolean update(Double pressure) {
        if (pressure != null && pressure > threshold) {
            if (streak < seconds) {
                streak++;
            }
        } else {
            streak = 0;
        }
        return streak >= seconds;
    }

    /** 연속을 0으로 되돌린다 (반복·이동). */
    public void reset() {
        streak = 0;
    }
}
