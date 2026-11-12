package com.tripley.crowdsight.grade;

/**
 * 밀도 등급 기준(명/㎡). 값 이상이면 그 등급이다 (api-spec 4.1). crowdsight.grade.density로 바인딩한다.
 * S3 hello.thresholds.density로도 그대로 보낸다.
 *
 * @param caution  주의 기준
 * @param alert    경계 기준
 * @param critical 심각 기준
 */
public record DensityThresholds(double caution, double alert, double critical) {

    public DensityThresholds {
        if (!(0 < caution && caution < alert && alert < critical)) {   // NaN도 여기서 거부
            throw new IllegalArgumentException("밀도 기준은 0 < caution < alert < critical 이어야 합니다: caution="
                    + caution + ", alert=" + alert + ", critical=" + critical);
        }
    }
}
