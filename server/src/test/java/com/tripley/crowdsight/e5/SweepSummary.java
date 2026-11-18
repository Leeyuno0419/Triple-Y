package com.tripley.crowdsight.e5;

import java.util.List;
import java.util.Objects;
import java.util.stream.Collectors;
import java.util.stream.Stream;

import com.tripley.crowdsight.alert.AlertEvent;
import com.tripley.crowdsight.alert.AlertReason;
import com.tripley.crowdsight.grade.Grade;
import com.tripley.crowdsight.replay.ZoneStep;

/**
 * 재생 결과 요약 (제안 P6). 첫 알림 초는 그 알림이 없으면 null이다(없을 수 있는 정수라 Integer).
 *
 * @param nInstability      INSTABILITY 알림 수
 * @param nGradeUp          GRADE_UP 알림 수
 * @param nInflow           INFLOW 알림 수
 * @param firstInstabilityT 첫 INSTABILITY 초
 * @param firstGradeUpT     첫 GRADE_UP 초
 * @param firstInflowT      첫 INFLOW 초
 * @param unstableS         판정 대상 셀 중 unstable이 1개 이상인 초 수 (경보 시간 a)
 * @param criticalS         구역 등급이 CRITICAL인 초 수 (히스테리시스 꼬리 포함, 경보 시간 b)
 * @param inflowOnS         유입 경보가 켜진 초 수 (끔 꼬리 포함)
 */
record SweepSummary(int nInstability, int nGradeUp, int nInflow, Integer firstInstabilityT, Integer firstGradeUpT,
                    Integer firstInflowT, int unstableS, int criticalS, int inflowOnS) {

    static final String HEADER = "n_instability,n_grade_up,n_inflow,first_instability_t,first_grade_up_t,"
            + "first_inflow_t,unstable_s,critical_s,inflow_on_s";

    /** 초별 재생 결과에서 만든다. */
    static SweepSummary of(List<ZoneStep> steps) {
        int unstable = 0;
        int critical = 0;
        int inflowOn = 0;
        for (ZoneStep step : steps) {
            if (step.evaluation().cells().stream().anyMatch(c -> c.eligible() && c.unstable())) {
                unstable++;
            }
            if (step.evaluation().zoneGrade() == Grade.CRITICAL) {
                critical++;
            }
            if (step.evaluation().inflowAlert()) {
                inflowOn++;
            }
        }
        return new SweepSummary(count(steps, AlertReason.INSTABILITY), count(steps, AlertReason.GRADE_UP),
                count(steps, AlertReason.INFLOW), first(steps, AlertReason.INSTABILITY),
                first(steps, AlertReason.GRADE_UP), first(steps, AlertReason.INFLOW), unstable, critical, inflowOn);
    }

    /** HEADER 순서의 CSV 값 (null은 빈칸). */
    String toCsv() {
        return Stream.of(nInstability, nGradeUp, nInflow, firstInstabilityT, firstGradeUpT, firstInflowT, unstableS,
                        criticalS, inflowOnS)
                .map(v -> Objects.toString(v, ""))
                .collect(Collectors.joining(","));
    }

    private static int count(List<ZoneStep> steps, AlertReason reason) {
        return (int) steps.stream().flatMap(s -> s.alerts().stream()).filter(a -> a.reason() == reason).count();
    }

    private static Integer first(List<ZoneStep> steps, AlertReason reason) {
        for (ZoneStep step : steps) {
            for (AlertEvent alert : step.alerts()) {
                if (alert.reason() == reason) {
                    return step.evaluation().t();
                }
            }
        }
        return null;
    }
}
