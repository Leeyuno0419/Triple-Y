package com.tripley.crowdsight.grade;

/** 밀도 → 등급 변환. 상태가 없어 여러 스레드에서 불러도 된다. */
public final class GradeRule {

    private GradeRule() {
    }

    /** 밀도의 조건 등급. 기준값 이상이면 그 등급이다 (3.0 → CAUTION, 2.99 → NORMAL). */
    public static Grade ofDensity(double density, DensityThresholds th) {
        if (density >= th.critical()) {
            return Grade.CRITICAL;
        }
        if (density >= th.alert()) {
            return Grade.ALERT;
        }
        if (density >= th.caution()) {
            return Grade.CAUTION;
        }
        return Grade.NORMAL;
    }

    /** 예측 등급 (grade_pred_60s). 히스테리시스 없이 바로 변환한다. 예측이 null이면 null. */
    public static Grade ofPrediction(Double densityPred60s, DensityThresholds th) {
        return densityPred60s == null ? null : ofDensity(densityPred60s, th);
    }
}
