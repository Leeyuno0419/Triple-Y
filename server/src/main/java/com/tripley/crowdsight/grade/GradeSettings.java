package com.tripley.crowdsight.grade;

/**
 * 등급 판정 설정. crowdsight.grade.*로 바인딩한다 (CrowdsightProperties.grade).
 *
 * @param density           밀도 등급 기준
 * @param upSeconds         올림에 필요한 연속 관측 수 (1 이상)
 * @param downSeconds       한 단계 내림에 필요한 연속 관측 수 (1 이상)
 * @param minWalkableAreaM2 구역 등급·max_density 판정 대상 셀의 최소 보행 면적(㎡, 0 이상). 이상이면 대상
 */
public record GradeSettings(DensityThresholds density, int upSeconds, int downSeconds, double minWalkableAreaM2) {

    public GradeSettings {
        if (density == null) {
            throw new IllegalArgumentException("density(밀도 등급 기준)가 없습니다.");
        }
        if (upSeconds < 1) {
            throw new IllegalArgumentException("up-seconds 는 1 이상이어야 합니다: " + upSeconds);
        }
        if (downSeconds < 1) {
            throw new IllegalArgumentException("down-seconds 는 1 이상이어야 합니다: " + downSeconds);
        }
        if (!(minWalkableAreaM2 >= 0)) {
            throw new IllegalArgumentException("min-walkable-area-m2 는 0 이상이어야 합니다: " + minWalkableAreaM2);
        }
    }
}
