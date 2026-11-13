package com.tripley.crowdsight.alert;

import java.util.ArrayList;
import java.util.List;

import com.tripley.crowdsight.grade.CellEvaluation;
import com.tripley.crowdsight.grade.Grade;
import com.tripley.crowdsight.grade.ZoneEvaluation;

/**
 * 구역 1개의 알림 사건 판정 (api-spec 3.3). 매 초 판정 결과를 받아 새로 생긴 사건만 돌려준다 (올라가는 순간만).
 * GRADE_UP: 구역 등급이 경계 이상이고 이번 사건에서 보낸 가장 높은 단계보다 높을 때. 경계 아래로 내려가면 사건 끝.
 * INSTABILITY: 판정 대상 셀 중 불안정 셀이 없다가 생긴 초. 모두 풀리기 전에는 다시 보내지 않는다.
 * INFLOW: 유입 경보가 꺼져 있다가 켜진 초.
 * 한 초에 여러 개면 INSTABILITY → GRADE_UP → INFLOW 순서다. 주의로 오르는 것은 알림이 없다.
 * 스레드 규칙: detect·reset은 재생 스레드 하나만 부른다 (ZoneRuntime 안). 잠금 없음.
 */
public final class AlertDetector {

    private Grade lastGrade = Grade.NORMAL;   // 직전 초 구역 등급 (GRADE_UP 문구)
    private Grade sentPeak;                   // 이번 사건에서 보낸 가장 높은 GRADE_UP 등급. 사건이 없으면 null
    private boolean lastUnstable;             // 직전 초에 판정 대상 불안정 셀이 있었는지
    private boolean lastInflow;               // 직전 초 유입 경보

    /** 이번 초 판정 결과에서 새로 생긴 알림 사건. 없으면 빈 목록. */
    public List<AlertEvent> detect(ZoneEvaluation eval) {
        List<AlertEvent> events = new ArrayList<>(3);

        List<CellEvaluation> unstable = eval.cells().stream().filter(c -> c.eligible() && c.unstable()).toList();
        if (!unstable.isEmpty() && !lastUnstable) {
            events.add(instability(unstable));
        }
        lastUnstable = !unstable.isEmpty();

        Grade grade = eval.zoneGrade();
        if (grade.compareTo(Grade.ALERT) < 0) {
            sentPeak = null;                                  // 경계 아래: 사건 끝
        } else if (sentPeak == null || grade.compareTo(sentPeak) > 0) {
            events.add(gradeUp(eval, lastGrade, grade));
            sentPeak = grade;
        }
        lastGrade = grade;

        if (eval.inflowAlert() && !lastInflow) {
            events.add(inflow(eval.inflowAvg()));
        }
        lastInflow = eval.inflowAlert();

        return List.copyOf(events);
    }

    /** 사건 상태를 처음으로 되돌린다 (첫 프레임·반복·이동). 그래서 반복할 때마다 같은 알림이 다시 생긴다. */
    public void reset() {
        lastGrade = Grade.NORMAL;
        sentPeak = null;
        lastUnstable = false;
        lastInflow = false;
    }

    private static AlertEvent gradeUp(ZoneEvaluation eval, Grade from, Grade to) {
        List<String> cellIds = eval.cells().stream()
                .filter(c -> c.eligible() && c.grade().compareTo(to) >= 0)
                .map(CellEvaluation::cellId)
                .toList();
        String particle = to == Grade.CRITICAL ? "으로" : "로";   // 심각(받침 있음)·경계(받침 없음)만 온다
        String message = "구역 등급이 " + from.label() + " → " + to.label() + particle + " 올랐다";
        return new AlertEvent(to, AlertReason.GRADE_UP, message, eval.maxDensity(), cellIds);
    }

    private static AlertEvent instability(List<CellEvaluation> unstable) {
        List<String> cellIds = unstable.stream().map(CellEvaluation::cellId).toList();
        double maxPressure = unstable.stream()
                .mapToDouble(c -> c.state().pressure())   // unstable이면 pressure는 기준을 넘은 non-null 값
                .max()
                .orElseThrow();
        String message = "셀 " + String.join(", ", cellIds) + "에서 군중 불안정이 감지됐다";
        return new AlertEvent(Grade.CRITICAL, AlertReason.INSTABILITY, message, maxPressure, cellIds);
    }

    private static AlertEvent inflow(Double average) {
        Double value = average == null ? null : Math.round(average * 1000) / 1000.0;   // 소수 3자리
        return new AlertEvent(Grade.CAUTION, AlertReason.INFLOW, "구역으로 들어오는 인원이 몰린다", value, List.of());
    }
}
