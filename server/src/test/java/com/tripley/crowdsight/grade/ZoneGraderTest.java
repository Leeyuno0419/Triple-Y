package com.tripley.crowdsight.grade;

import static com.tripley.crowdsight.grade.Grade.ALERT;
import static com.tripley.crowdsight.grade.Grade.CAUTION;
import static com.tripley.crowdsight.grade.Grade.CRITICAL;
import static com.tripley.crowdsight.grade.Grade.NORMAL;
import static com.tripley.crowdsight.timeline.TimelineFixtures.MAPPER;
import static com.tripley.crowdsight.timeline.TimelineFixtures.fixturePath;
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.util.ArrayList;
import java.util.List;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import com.tripley.crowdsight.config.TestProperties;
import com.tripley.crowdsight.timeline.CellMeta;
import com.tripley.crowdsight.timeline.CellState;
import com.tripley.crowdsight.timeline.Frame;
import com.tripley.crowdsight.timeline.TimelineLoader;
import com.tripley.crowdsight.timeline.ZoneTimeline;

class ZoneGraderTest {

    /** fixture와 같은 기본 meta: c-0000(4.0), c-0001(4.0), c-0102(1.5). */
    private static final List<CellMeta> METAS = List.of(meta("c-0000", 4.0), meta("c-0001", 4.0),
            meta("c-0102", 1.5));

    /** 셀 meta. row·col은 id(c-RRCC)에서 읽고 imagePolygon은 비운다. */
    private static CellMeta meta(String id, double area) {
        int row = Integer.parseInt(id.substring(2, 4));
        int col = Integer.parseInt(id.substring(4, 6));
        return new CellMeta(id, row, col, area, List.of());
    }

    /** metas 순서의 셀로 프레임을 만든다. preds가 null이면 예측은 모두 null. */
    private static Frame frame(int t, List<CellMeta> metas, Double[] densities, Double[] preds) {
        List<CellState> cells = new ArrayList<>();
        for (int i = 0; i < metas.size(); i++) {
            Double pred = preds == null ? null : preds[i];
            cells.add(new CellState(metas.get(i).cellId(), densities[i], null, null, null, null, null, pred));
        }
        return new Frame(t, null, null, cells);
    }

    private static Frame frame(int t, List<CellMeta> metas, Double... densities) {
        return frame(t, metas, densities, null);
    }

    private static Double[] densities(Double... values) {
        return values;
    }

    private static ZoneGrader grader(List<CellMeta> metas) {
        return new ZoneGrader(metas, TestProperties.GRADE);
    }

    private static List<Grade> cellGrades(ZoneEvaluation e) {
        return e.cells().stream().map(CellEvaluation::grade).toList();
    }

    private static List<Boolean> eligibles(ZoneEvaluation e) {
        return e.cells().stream().map(CellEvaluation::eligible).toList();
    }

    private static List<Grade> predGrades(ZoneEvaluation e) {
        return e.cells().stream().map(CellEvaluation::gradePred60s).toList();
    }

    @Test
    @DisplayName("2㎡ 미만 셀은 자기 등급만 내고 구역 등급에서 빠진다")
    void smallCellExcluded() {
        ZoneGrader grader = grader(METAS);

        ZoneEvaluation t0 = grader.evaluate(frame(0, METAS, 3.2, 1.0, 6.0));
        ZoneEvaluation t1 = grader.evaluate(frame(1, METAS, 3.4, 1.0, 6.0));

        assertThat(grader.eligibleCount()).isEqualTo(2);
        assertThat(cellGrades(t0)).containsExactly(NORMAL, NORMAL, NORMAL);
        assertThat(t0.zoneGrade()).isEqualTo(NORMAL);
        assertThat(t0.maxDensity()).isEqualTo(3.2);
        assertThat(cellGrades(t1)).containsExactly(CAUTION, NORMAL, CRITICAL);
        assertThat(eligibles(t1)).containsExactly(true, true, false);
        assertThat(t1.zoneGrade()).isEqualTo(CAUTION);
        assertThat(t1.maxDensity()).isEqualTo(3.4);
    }

    @Test
    @DisplayName("면적이 정확히 2㎡인 셀은 판정 대상이다")
    void areaBoundaryIncluded() {
        List<CellMeta> metas = List.of(meta("c-0000", 2.0), meta("c-0001", 1.99));
        ZoneGrader grader = grader(metas);

        grader.evaluate(frame(0, metas, 4.5, 5.5));
        ZoneEvaluation t1 = grader.evaluate(frame(1, metas, 4.5, 5.5));

        assertThat(cellGrades(t1)).containsExactly(ALERT, CRITICAL);
        assertThat(eligibles(t1)).containsExactly(true, false);
        assertThat(t1.zoneGrade()).isEqualTo(ALERT);
        assertThat(t1.maxDensity()).isEqualTo(4.5);
    }

    @Test
    @DisplayName("판정 대상 셀이 없으면 구역은 정상, 최대 밀도는 null이다")
    void noEligibleCells() {
        List<CellMeta> metas = List.of(meta("c-0000", 1.5), meta("c-0001", 1.5));
        ZoneGrader grader = grader(metas);

        grader.evaluate(frame(0, metas, 4.5, 4.5));
        ZoneEvaluation t1 = grader.evaluate(frame(1, metas, 4.5, 4.5));

        assertThat(grader.eligibleCount()).isZero();
        assertThat(cellGrades(t1)).containsExactly(ALERT, ALERT);
        assertThat(t1.zoneGrade()).isEqualTo(NORMAL);
        assertThat(t1.maxDensity()).isNull();
    }

    @Test
    @DisplayName("예측 등급은 히스테리시스 없이 바로 바뀐다")
    void predictionNoHysteresis() {
        ZoneEvaluation t0 = grader(METAS).evaluate(
                frame(0, METAS, densities(1.0, 1.0, 1.0), densities(4.6, 2.99, 5.0)));

        assertThat(predGrades(t0)).containsExactly(ALERT, NORMAL, CRITICAL);
        assertThat(cellGrades(t0)).containsExactly(NORMAL, NORMAL, NORMAL);
    }

    @Test
    @DisplayName("예측이 null이면 예측 등급도 null이다")
    void predictionNull() {
        ZoneEvaluation t0 = grader(METAS).evaluate(
                frame(0, METAS, densities(1.0, 1.0, 1.0), densities(null, 1.0, null)));

        assertThat(predGrades(t0)).containsExactly(null, NORMAL, null);
    }

    @Test
    @DisplayName("셀 결과는 meta 순서이고 원래 값을 그대로 담는다")
    void orderPreserved() {
        List<CellMeta> metas = List.of(meta("c-0102", 1.5), meta("c-0000", 4.0), meta("c-0001", 4.0));
        Frame frame = frame(7, metas, 1.0, 1.0, 1.0);

        ZoneEvaluation e = grader(metas).evaluate(frame);

        assertThat(e.t()).isEqualTo(7);
        assertThat(e.cells()).extracting(CellEvaluation::cellId).containsExactly("c-0102", "c-0000", "c-0001");
        assertThat(eligibles(e)).containsExactly(false, true, true);
        for (int i = 0; i < 3; i++) {
            assertThat(e.cells().get(i).state()).isSameAs(frame.cells().get(i));
        }
    }

    @Test
    @DisplayName("밀도 null은 등급을 유지하고 최대 밀도에서 뺀다")
    void nullDensitySkipped() {
        List<CellMeta> metas = List.of(meta("c-0000", 4.0));
        ZoneGrader grader = grader(metas);

        List<ZoneEvaluation> results = List.of(grader.evaluate(frame(0, metas, 4.5)),
                grader.evaluate(frame(1, metas, densities((Double) null))), grader.evaluate(frame(2, metas, 4.5)));

        assertThat(results).extracting(e -> e.cells().get(0).grade()).containsExactly(NORMAL, NORMAL, ALERT);
        assertThat(results).extracting(ZoneEvaluation::zoneGrade).containsExactly(NORMAL, NORMAL, ALERT);
        assertThat(results).extracting(ZoneEvaluation::maxDensity).containsExactly(4.5, null, 4.5);
    }

    @Test
    @DisplayName("초기화하면 셀 등급이 처음부터 다시 쌓인다")
    void resetRestartsHysteresis() {
        List<CellMeta> metas = List.of(meta("c-0000", 4.0));
        ZoneGrader grader = grader(metas);
        grader.evaluate(frame(0, metas, 4.5));
        ZoneEvaluation second = grader.evaluate(frame(1, metas, 4.5));

        grader.reset();
        ZoneEvaluation afterReset = grader.evaluate(frame(2, metas, 4.5));

        assertThat(second.cells().get(0).grade()).isEqualTo(ALERT);
        assertThat(afterReset.cells().get(0).grade()).isEqualTo(NORMAL);
        assertThat(afterReset.zoneGrade()).isEqualTo(NORMAL);
    }

    @Test
    @DisplayName("셀 수나 순서가 meta와 다르면 거부한다")
    void rejectsMismatchedCells() {
        ZoneGrader grader = grader(METAS);
        Frame tooFew = frame(0, METAS.subList(0, 2), 4.5, 4.5);
        Frame reordered = frame(0, List.of(METAS.get(0), METAS.get(2), METAS.get(1)), 4.5, 4.5, 4.5);

        assertThatThrownBy(() -> grader.evaluate(tooFew))
                .isInstanceOf(IllegalArgumentException.class).hasMessageContaining("셀");
        assertThatThrownBy(() -> grader.evaluate(reordered))
                .isInstanceOf(IllegalArgumentException.class).hasMessageContaining("셀");

        ZoneEvaluation next = grader.evaluate(frame(1, METAS, 4.5, 4.5, 4.5));
        assertThat(cellGrades(next)).containsExactly(NORMAL, NORMAL, NORMAL);
    }

    @Test
    @DisplayName("fixture 5초를 판정한다")
    void gradesFixtureTimeline() {
        ZoneTimeline timeline = new TimelineLoader(MAPPER, TestProperties.of(fixturePath().getParent().toString(),
                List.of("valid_v02.json"), 1000, true)).loadAll().get(0);
        ZoneGrader grader = new ZoneGrader(timeline.meta().cells(), TestProperties.GRADE);

        List<ZoneEvaluation> results = timeline.frames().stream().map(grader::evaluate).toList();

        assertThat(results).extracting(ZoneEvaluation::zoneGrade)
                .containsExactly(NORMAL, NORMAL, NORMAL, NORMAL, CAUTION);
        assertThat(results).extracting(ZoneEvaluation::maxDensity).containsExactly(1.25, 1.5, 2.0, 3.2, 4.2);
        assertThat(cellGrades(results.get(3))).containsExactly(NORMAL, NORMAL, NORMAL);
        assertThat(cellGrades(results.get(4))).containsExactly(CAUTION, NORMAL, ALERT);
        assertThat(predGrades(results.get(0))).containsExactly(null, null, null);
        assertThat(predGrades(results.get(3))).containsExactly(CAUTION, NORMAL, ALERT);
        assertThat(predGrades(results.get(4))).containsExactly(ALERT, NORMAL, CRITICAL);
    }
}
