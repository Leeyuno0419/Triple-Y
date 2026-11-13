package com.tripley.crowdsight.grade;

/**
 * 셀 불안정 판정 설정 (api-spec 4.3). crowdsight.instability.*로 바인딩한다.
 * hello.thresholds.pressure로도 그대로 보낸다.
 *
 * @param pressure 군중 압력 기준(1/s²). 이 값을 넘어야(초과) 그 초를 센다
 * @param seconds  기준을 연속으로 넘어야 하는 초 (1 이상)
 */
public record InstabilitySettings(double pressure, int seconds) {

    public InstabilitySettings {
        if (!(pressure > 0)) {   // NaN도 거부
            throw new IllegalArgumentException("pressure 는 0보다 커야 합니다: " + pressure);
        }
        if (seconds < 1) {
            throw new IllegalArgumentException("seconds 는 1 이상이어야 합니다: " + seconds);
        }
    }
}
