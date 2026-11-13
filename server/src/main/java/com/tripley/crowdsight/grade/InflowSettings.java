package com.tripley.crowdsight.grade;

/**
 * 구역 유입 경보 설정 (api-spec 4.4, 결정 6, 결정 기록 8). crowdsight.inflow.*로 바인딩한다.
 * hello.thresholds.inflow_ratio로 ratio를 보낸다.
 *
 * @param ratio         5초 평균이 이 값을 넘으면(초과) 경보 조건. 0 이상 1 미만
 * @param windowSeconds 평균 창(초, 1 이상). 시작·초기화 뒤 이 개수만큼 관측이 쌓여야 평균을 낸다
 * @param minSamples    창 안 non-null 값이 이 개수 이상일 때만 평균 (1 이상 windowSeconds 이하)
 * @param offSeconds    켜진 뒤 조건이 이 초만큼 연속 거짓이면 끈다 (1 이상)
 * @param minCount      구역 인원 count가 이 값 이상일 때만 켠다 (0 이상)
 */
public record InflowSettings(double ratio, int windowSeconds, int minSamples, int offSeconds, double minCount) {

    public InflowSettings {
        if (!(ratio >= 0 && ratio < 1)) {
            throw new IllegalArgumentException("ratio 는 0 이상 1 미만이어야 합니다: " + ratio);
        }
        if (windowSeconds < 1) {
            throw new IllegalArgumentException("window-seconds 는 1 이상이어야 합니다: " + windowSeconds);
        }
        if (minSamples < 1 || minSamples > windowSeconds) {
            throw new IllegalArgumentException("min-samples 는 1 이상 window-seconds 이하여야 합니다: min-samples="
                    + minSamples + ", window-seconds=" + windowSeconds);
        }
        if (offSeconds < 1) {
            throw new IllegalArgumentException("off-seconds 는 1 이상이어야 합니다: " + offSeconds);
        }
        if (!(minCount >= 0)) {
            throw new IllegalArgumentException("min-count 는 0 이상이어야 합니다: " + minCount);
        }
    }
}
