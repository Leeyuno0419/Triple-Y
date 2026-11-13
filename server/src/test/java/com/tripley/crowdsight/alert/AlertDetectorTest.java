package com.tripley.crowdsight.alert;

import static com.tripley.crowdsight.grade.Grade.ALERT;
import static com.tripley.crowdsight.grade.Grade.CAUTION;
import static com.tripley.crowdsight.grade.Grade.CRITICAL;
import static com.tripley.crowdsight.grade.Grade.NORMAL;
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.tuple;

import java.util.ArrayList;
import java.util.List;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import com.tripley.crowdsight.config.TestProperties;
import com.tripley.crowdsight.grade.CellEvaluation;
import com.tripley.crowdsight.grade.Grade;
import com.tripley.crowdsight.grade.ZoneEvaluation;
import com.tripley.crowdsight.grade.ZoneGrader;
import com.tripley.crowdsight.timeline.CellMeta;
import com.tripley.crowdsight.timeline.CellState;
import com.tripley.crowdsight.timeline.Frame;

class AlertDetectorTest {

    private static final List<CellMeta> ONE = List.of(new CellMeta("c-0000", 0, 0, 4.0, List.of()));

    private final AlertDetector detector = new AlertDetector();

    /** 판정 대상 셀. pressure는 unstable일 때만 의미가 있다. */
    private static CellEvaluation cell(String id, Grade grade, boolean eligible, boolean unstable, double density,
                                       Double pressure) {
        return new CellEvaluation(id, grade, null, eligible, unstable,
                new CellState(id, density, null, null, null, pressure, null, null));
    }

    private static ZoneEvaluation eval(int t, Grade zoneGrade, Double maxDensity, Double inflowAvg,
                                       boolean inflowAlert, CellEvaluation... cells) {
        return new ZoneEvaluation(t, zoneGrade, maxDensity, inflowAvg, inflowAlert, List.of(cells));
    }

    /** 구역 등급만 바꾸며 detect를 부르고 초마다 사건 목록을 모은다 (셀 없음, max_density 4.5). */
    private List<List<AlertEvent>> runGrades(Grade... grades) {
        List<List<AlertEvent>> results = new ArrayList<>();
        for (int t = 0; t < grades.length; t++) {
            results.add(detector.detect(eval(t, grades[t], 4.5, null, false)));
        }
        return results;
    }

    /** 초마다 사건 수가 1개 이상인 초 번호. */
    private static List<Integer> ticksWithEvents(List<List<AlertEvent>> results) {
        List<Integer> ticks = new ArrayList<>();
        for (int t = 0; t < results.size(); t++) {
            if (!results.get(t).isEmpty()) {
                ticks.add(t);
            }
        }
        return ticks;
    }

    @Test
    @DisplayName("경계 이상으로 오르고 사건 최고 단계를 넘을 때만 GRADE_UP을 보낸다")
    void gradeUpRules() {
        List<List<AlertEvent>> results = runGrades(NORMAL, CAUTION, ALERT, CRITICAL, ALERT, CRITICAL, CAUTION, ALERT);

        assertThat(ticksWithEvents(results)).containsExactly(2, 3, 7);
        assertThat(results.get(2)).extracting(AlertEvent::reason, AlertEvent::level)
                .containsExactly(tuple(AlertReason.GRADE_UP, ALERT));
        assertThat(results.get(3)).extracting(AlertEvent::reason, AlertEvent::level)
                .containsExactly(tuple(AlertReason.GRADE_UP, CRITICAL));
        assertThat(results.get(7)).extracting(AlertEvent::reason, AlertEvent::level)
                .containsExactly(tuple(AlertReason.GRADE_UP, ALERT));
    }

    @Test
    @DisplayName("문구는 직전 등급 → 지금 등급이다")
    void gradeUpMessages() {
        List<List<AlertEvent>> results = runGrades(NORMAL, CAUTION, ALERT, CRITICAL, ALERT, CRITICAL, CAUTION, ALERT);

        assertThat(results.get(2).get(0).message()).isEqualTo("구역 등급이 주의 → 경계로 올랐다");
        assertThat(results.get(3).get(0).message()).isEqualTo("구역 등급이 경계 → 심각으로 올랐다");
        assertThat(results.get(7).get(0).message()).isEqualTo("구역 등급이 주의 → 경계로 올랐다");
    }

    @Test
    @DisplayName("정상에서 심각으로 바로 오르면 심각 하나만 보낸다")
    void gradeUpJumpFromNormal() {
        List<List<AlertEvent>> results = runGrades(NORMAL, CRITICAL, ALERT);

        assertThat(ticksWithEvents(results)).containsExactly(1);
        assertThat(results.get(1)).hasSize(1);
        assertThat(results.get(1).get(0).level()).isEqualTo(CRITICAL);
        assertThat(results.get(1).get(0).message()).isEqualTo("구역 등급이 정상 → 심각으로 올랐다");
    }

    @Test
    @DisplayName("주의로 오르는 것은 알림이 없다")
    void noAlertForCaution() {
        assertThat(runGrades(NORMAL, CAUTION, CAUTION, NORMAL, CAUTION)).allSatisfy(e -> assertThat(e).isEmpty());
    }

    @Test
    @DisplayName("GRADE_UP 값은 최대 밀도, 셀은 등급이 level 이상인 판정 대상 셀이다")
    void gradeUpPayload() {
        detector.detect(eval(0, CAUTION, 3.5, null, false));
        List<AlertEvent> events = detector.detect(eval(1, ALERT, 4.3, null, false,
                cell("c-0000", ALERT, true, false, 4.3, null),
                cell("c-0001", CAUTION, true, false, 3.5, null),
                cell("c-0102", CRITICAL, false, false, 6.0, null)));

        assertThat(events).containsExactly(new AlertEvent(ALERT, AlertReason.GRADE_UP,
                "구역 등급이 주의 → 경계로 올랐다", 4.3, List.of("c-0000")));
    }

    @Test
    @DisplayName("심각 알림의 셀은 심각인 셀만이다")
    void gradeUpCellsAtOrAboveLevel() {
        List<AlertEvent> events = detector.detect(eval(0, CRITICAL, 5.5, null, false,
                cell("c-0000", ALERT, true, false, 4.5, null),
                cell("c-0001", CRITICAL, true, false, 5.5, null)));

        assertThat(events).hasSize(1);
        assertThat(events.get(0).cellIds()).containsExactly("c-0001");
        assertThat(events.get(0).value()).isEqualTo(5.5);
    }

    @Test
    @DisplayName("판정 대상 불안정 셀이 처음 생긴 초에만 INSTABILITY를 보낸다")
    void instabilityEdge() {
        boolean[] first = {false, false, true, true};
        boolean[] second = {false, false, false, true};
        List<List<AlertEvent>> results = new ArrayList<>();
        for (int t = 0; t < 4; t++) {
            results.add(detector.detect(eval(t, NORMAL, 1.0, null, false,
                    cell("c-0000", NORMAL, true, first[t], 1.0, 0.03),
                    cell("c-0001", NORMAL, true, second[t], 1.0, 0.03))));
        }

        assertThat(ticksWithEvents(results)).containsExactly(2);
        assertThat(results.get(2)).containsExactly(new AlertEvent(CRITICAL, AlertReason.INSTABILITY,
                "셀 c-0000에서 군중 불안정이 감지됐다", 0.03, List.of("c-0000")));
    }

    @Test
    @DisplayName("같은 초에 여러 셀이 불안정이면 모두 담고 최대 압력을 값으로 한다")
    void instabilityPayload() {
        List<AlertEvent> events = detector.detect(eval(0, NORMAL, 1.0, null, false,
                cell("c-0000", NORMAL, true, true, 1.0, 0.03),
                cell("c-0001", NORMAL, true, true, 1.0, 0.05)));

        assertThat(events).hasSize(1);
        assertThat(events.get(0).cellIds()).containsExactly("c-0000", "c-0001");
        assertThat(events.get(0).value()).isEqualTo(0.05);
        assertThat(events.get(0).message()).isEqualTo("셀 c-0000, c-0001에서 군중 불안정이 감지됐다");
    }

    @Test
    @DisplayName("판정 대상이 아닌 셀의 불안정은 알리지 않는다")
    void instabilityIgnoresSmallCells() {
        List<List<AlertEvent>> results = new ArrayList<>();
        for (int t = 0; t < 3; t++) {
            results.add(detector.detect(eval(t, NORMAL, null, null, false,
                    cell("c-0102", NORMAL, false, true, 1.0, 0.03))));
        }

        assertThat(results).allSatisfy(e -> assertThat(e).isEmpty());
    }

    @Test
    @DisplayName("불안정이 모두 풀린 뒤 다시 생기면 다시 보낸다")
    void instabilityResendsAfterRelease() {
        boolean[] unstable = {true, false, true};
        List<List<AlertEvent>> results = new ArrayList<>();
        for (int t = 0; t < 3; t++) {
            results.add(detector.detect(eval(t, NORMAL, 1.0, null, false,
                    cell("c-0000", NORMAL, true, unstable[t], 1.0, 0.03))));
        }

        assertThat(ticksWithEvents(results)).containsExactly(0, 2);
    }

    @Test
    @DisplayName("유입 경보가 켜진 초에만 INFLOW를 보낸다")
    void inflowEdge() {
        boolean[] alert = {false, false, false, false, true, true};
        List<List<AlertEvent>> results = new ArrayList<>();
        for (int t = 0; t < 6; t++) {
            Double avg = t >= 4 ? 0.6599999999999999 : null;
            results.add(detector.detect(eval(t, NORMAL, 1.0, avg, alert[t])));
        }

        assertThat(ticksWithEvents(results)).containsExactly(4);
        assertThat(results.get(4)).containsExactly(new AlertEvent(CAUTION, AlertReason.INFLOW,
                "구역으로 들어오는 인원이 몰린다", 0.66, List.of()));
    }

    @Test
    @DisplayName("INFLOW 값은 소수 3자리로 반올림한다")
    void inflowValueRounded() {
        List<AlertEvent> events = detector.detect(eval(0, NORMAL, 1.0, 0.775000000000001, true));

        assertThat(events.get(0).value()).isEqualTo(0.775);
    }

    @Test
    @DisplayName("유입 경보가 꺼졌다가 다시 켜지면 다시 보낸다")
    void inflowResendsAfterOff() {
        boolean[] alert = {true, false, true};
        List<List<AlertEvent>> results = new ArrayList<>();
        for (int t = 0; t < 3; t++) {
            results.add(detector.detect(eval(t, NORMAL, 1.0, 0.8, alert[t])));
        }

        assertThat(ticksWithEvents(results)).containsExactly(0, 2);
    }

    @Test
    @DisplayName("한 초에 여러 알림이면 불안정, 등급, 유입 순서다")
    void sameTickOrder() {
        List<AlertEvent> events = detector.detect(eval(0, CRITICAL, 5.5, 0.8, true,
                cell("c-0000", CRITICAL, true, true, 5.5, 0.03)));

        assertThat(events).extracting(AlertEvent::reason)
                .containsExactly(AlertReason.INSTABILITY, AlertReason.GRADE_UP, AlertReason.INFLOW);
    }

    @Test
    @DisplayName("초기화하면 같은 사건을 다시 보낸다")
    void resetStartsNewIncident() {
        ZoneEvaluation same = eval(0, ALERT, 4.5, 0.8, true, cell("c-0000", ALERT, true, true, 4.5, 0.03));

        List<AlertEvent> before = detector.detect(same);
        detector.reset();
        List<AlertEvent> after = detector.detect(same);

        assertThat(before).hasSize(3);
        assertThat(after).hasSize(3);
        assertThat(after.get(1).message()).isEqualTo("구역 등급이 정상 → 경계로 올랐다");
    }

    @Test
    @DisplayName("불안정은 INSTABILITY 다음 초에 심각 GRADE_UP을 만든다")
    void instabilityThenCriticalGradeUp() {
        ZoneGrader grader = TestProperties.grader(ONE);
        List<List<AlertEvent>> results = new ArrayList<>();
        for (int t = 0; t < 4; t++) {
            Frame frame = new Frame(t, null, null,
                    List.of(new CellState("c-0000", 1.0, null, null, null, 0.03, null, null)));
            results.add(detector.detect(grader.evaluate(frame)));
        }

        assertThat(ticksWithEvents(results)).containsExactly(2, 3);
        assertThat(results.get(2)).containsExactly(new AlertEvent(CRITICAL, AlertReason.INSTABILITY,
                "셀 c-0000에서 군중 불안정이 감지됐다", 0.03, List.of("c-0000")));
        assertThat(results.get(3)).containsExactly(new AlertEvent(CRITICAL, AlertReason.GRADE_UP,
                "구역 등급이 정상 → 심각으로 올랐다", 1.0, List.of("c-0000")));
    }
}
