package com.tripley.crowdsight.e5;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.assertj.core.api.Assertions.tuple;
import static org.assertj.core.api.Assertions.within;

import java.io.IOException;
import java.net.URISyntaxException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.stream.IntStream;

import org.assertj.core.groups.Tuple;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import com.tripley.crowdsight.alert.AlertReason;
import com.tripley.crowdsight.config.CrowdsightProperties;
import com.tripley.crowdsight.config.TestProperties;
import com.tripley.crowdsight.grade.Grade;
import com.tripley.crowdsight.grade.InflowSettings;
import com.tripley.crowdsight.grade.InstabilitySettings;
import com.tripley.crowdsight.replay.ZoneStep;
import com.tripley.crowdsight.timeline.InvalidTimelineException;
import com.tripley.crowdsight.timeline.TimelineFixtures;

import tools.jackson.databind.node.ObjectNode;

/**
 * E5 실행기 시험. fixture는 e5/e5_sweep_v02.json (계획 7.2절, 40초, 판정 대상 셀 c-0000·작은 셀 c-0102).
 * c-0000 밀도는 불안정 밀도 하한 경계인 3.0이라 기본값에서 불안정이 되고, 불안정이 아닌 초의 관측 등급은 주의다.
 * 기대값은 서버 규칙(InstabilityTracker·GradeHysteresis·InflowMonitor·AlertDetector)으로 손 계산했다.
 */
class E5SweepTest {

    @TempDir
    Path dir;

    private static Path fixture() {
        try {
            return Path.of(E5SweepTest.class.getResource("/e5/e5_sweep_v02.json").toURI());
        } catch (URISyntaxException e) {
            throw new IllegalStateException(e);
        }
    }

    /** c-0000 밀도를 모두 1.0(하한 3.0 아래)으로 바꾼 fixture를 dir에 쓴다. 압력은 그대로다. */
    private Path sparseFixture() throws IOException {
        ObjectNode root = (ObjectNode) TimelineFixtures.MAPPER.readTree(fixture());
        root.get("frames").forEach(f -> ((ObjectNode) f.get("cells").get(0)).put("density", 1.0));
        Path sparse = dir.resolve("e5_sparse.json");
        Files.writeString(sparse, TimelineFixtures.MAPPER.writeValueAsString(root), StandardCharsets.UTF_8);
        return sparse;
    }

    private static List<ZoneStep> replayDefault(Path timeline) {
        return E5Sweep.replay(timeline, TestProperties.GRADE, TestProperties.INSTABILITY, TestProperties.INFLOW);
    }

    /** 알림마다 (t, 사유, 단계, 값, 셀 ID). */
    private static List<Tuple> alertTuples(List<ZoneStep> steps) {
        return steps.stream()
                .flatMap(s -> s.alerts().stream()
                        .map(a -> tuple(s.evaluation().t(), a.reason(), a.level(), a.value(), a.cellIds())))
                .toList();
    }

    @Test
    @DisplayName("기본값으로 끝까지 재생하면 40초와 손 계산한 알림 5개를 순서대로 낸다")
    void replayDefaultGivesHandComputedAlerts() {
        List<ZoneStep> steps = replayDefault(fixture());

        assertThat(steps).extracting(s -> s.evaluation().t())
                .containsExactlyElementsOf(IntStream.range(0, 40).boxed().toList());
        assertThat(alertTuples(steps)).containsExactly(
                tuple(2, AlertReason.INSTABILITY, Grade.CRITICAL, 0.03, List.of("c-0000")),
                tuple(3, AlertReason.GRADE_UP, Grade.CRITICAL, 3.0, List.of("c-0000")),
                tuple(12, AlertReason.INFLOW, Grade.CAUTION, 0.8, List.of()),
                tuple(32, AlertReason.INSTABILITY, Grade.CRITICAL, 0.03, List.of("c-0000")),
                tuple(33, AlertReason.GRADE_UP, Grade.CRITICAL, 3.0, List.of("c-0000")));
    }

    @Test
    @DisplayName("밀도 1.0 셀은 압력이 기준을 넘어도 기본값(하한 3.0)에서 불안정 알림이 없고, 하한 0이면 생긴다")
    void sparseHighPressureCellIsNotUnstableAtDefault() throws IOException {
        Path sparse = sparseFixture();

        List<ZoneStep> byDefault = replayDefault(sparse);
        List<ZoneStep> noFloor = E5Sweep.replay(sparse, TestProperties.GRADE, new InstabilitySettings(0.02, 3, 0.0),
                TestProperties.INFLOW);

        assertThat(alertTuples(byDefault)).containsExactly(
                tuple(12, AlertReason.INFLOW, Grade.CAUTION, 0.8, List.of()));
        assertThat(alertTuples(noFloor)).extracting(t -> t.toList().get(1))
                .containsExactly(AlertReason.INSTABILITY, AlertReason.GRADE_UP, AlertReason.INFLOW,
                        AlertReason.INSTABILITY, AlertReason.GRADE_UP);
    }

    @Test
    @DisplayName("없는 파일이면 서버와 같은 InvalidTimelineException")
    void replayMissingFileThrows() {
        Path missing = dir.resolve("nope.json");

        assertThatThrownBy(() -> replayDefault(missing))
                .isInstanceOf(InvalidTimelineException.class)
                .hasMessageContaining("파일이 없습니다");
    }

    @Test
    @DisplayName("count 키가 빠진 v0.2 파일은 서버 검증기를 거쳐 InvalidTimelineException")
    void replayInvalidTimelineThrows() throws IOException {
        ObjectNode root = (ObjectNode) TimelineFixtures.MAPPER.readTree(fixture());
        ((ObjectNode) root.get("frames").get(5)).remove("count");
        Path broken = dir.resolve("broken.json");
        Files.writeString(broken, TimelineFixtures.MAPPER.writeValueAsString(root), StandardCharsets.UTF_8);

        assertThatThrownBy(() -> replayDefault(broken))
                .isInstanceOf(InvalidTimelineException.class)
                .hasMessageContaining("t=5: count 필드가 없습니다");
    }

    @Test
    @DisplayName("설정은 반복을 끄고 타임라인의 부모 폴더와 파일 이름을 담는다")
    void propsPointAtTimelineWithoutLoop() {
        Path timeline = fixture();

        CrowdsightProperties props = E5Sweep.props(timeline, TestProperties.GRADE, TestProperties.INSTABILITY,
                TestProperties.INFLOW);

        assertThat(props.replay().loop()).isFalse();
        assertThat(Path.of(props.timelineDir())).isEqualTo(timeline.toAbsolutePath().normalize().getParent());
        assertThat(props.timelineFiles()).containsExactly("e5_sweep_v02.json");
        assertThat(props.instability()).isEqualTo(TestProperties.INSTABILITY);
        assertThat(props.inflow()).isEqualTo(TestProperties.INFLOW);
    }

    @Test
    @DisplayName("기본값 요약은 손 계산과 같다 (경보 시간: 불안정 4초, 심각 17초, 유입 13초)")
    void summaryOfDefaultReplay() {
        SweepSummary summary = SweepSummary.of(replayDefault(fixture()));

        assertThat(summary).isEqualTo(new SweepSummary(2, 2, 1, 2, 3, 12, 4, 17, 13));
        assertThat(summary.toCsv()).isEqualTo("2,2,1,2,3,12,4,17,13");
    }

    @Test
    @DisplayName("알림이 없으면 첫 알림 초는 null이고 CSV에서는 빈칸이다")
    void summaryWithoutAlertsHasNullFirstTimes() {
        List<ZoneStep> steps = E5Sweep.replay(fixture(), TestProperties.GRADE, new InstabilitySettings(0.04, 3,
                TestProperties.INSTABILITY.minDensity()),
                new InflowSettings(0.9, 5, 3, 10, 3.0));

        SweepSummary summary = SweepSummary.of(steps);

        assertThat(summary).isEqualTo(new SweepSummary(0, 0, 0, null, null, null, 0, 0, 0));
        assertThat(summary.toCsv()).isEqualTo("0,0,0,,,,0,0,0");
    }

    @Test
    @DisplayName("불안정 격자는 60행(압력×초×밀도 하한)이고 기본 행 1개와 손 계산한 행을 담는다")
    void instabilityRowsCoverGrid() {
        List<String> rows = E5Sweep.instabilityRows(fixture());

        assertThat(rows).hasSize(60);
        assertThat(rows).filteredOn(r -> r.split(",")[3].equals("true"))
                .containsExactly("0.02,3,3.0,true,2,2,1,2,3,12,4,17,13");
        assertThat(rows).contains(
                "0.02,3,0.0,false,2,2,1,2,3,12,4,17,13",
                "0.04,3,3.0,false,0,0,1,,,12,0,0,13",
                "0.02,1,3.0,false,2,2,1,0,1,12,8,21,13",
                "0.02,5,3.0,false,0,0,1,,,12,0,0,13");
    }

    @Test
    @DisplayName("밀도 1.0 셀이면 불안정 격자에서 하한 0 행만 알림이 있고 하한 2.0·3.0 행은 없다")
    void instabilityRowsSeparateDensityFloors() throws IOException {
        List<String> rows = E5Sweep.instabilityRows(sparseFixture());

        assertThat(rows).contains(
                "0.02,3,0.0,false,2,2,1,2,3,12,4,17,13",
                "0.02,3,2.0,false,0,0,1,,,12,0,0,13",
                "0.02,3,3.0,true,0,0,1,,,12,0,0,13");
    }

    @Test
    @DisplayName("유입 격자는 45행이고 기본 행 1개와 손 계산한 행을 담는다")
    void inflowRowsCoverGrid() {
        List<String> rows = E5Sweep.inflowRows(fixture());

        assertThat(rows).hasSize(45);
        assertThat(rows).filteredOn(r -> r.split(",")[5].equals("true"))
                .containsExactly("0.6,5,3,3.0,10,true,2,2,1,2,3,12,4,17,13");
        assertThat(rows).contains(
                "0.6,3,2,3.0,10,false,2,2,1,2,3,11,4,17,13",
                // 창 (10, 6): t15 평균 4.1/6 = 0.683 > 0.6이라 켠다. t16 평균은 수학적으로 4.2/7 = 0.6이지만
                // InflowMonitor가 원형 버퍼 순서로 0.8×5 + 0.1 + 0.1을 더하면 4.199999999999999가 되어
                // 0.5999999999999999 > 0.6은 거짓이다(수학값 0.6도 초과가 아니라 결과는 같지만, 합이 반올림으로
                // 0.6을 넘었다면 켜짐이 이어졌을 것이다). 그래서 t16부터 거짓 10초(t16~t25)로 t25에 꺼지고
                // inflow_on_s는 t15~t24 = 10이다. 실제 서버 산술 그대로이고 결정적이라 이 값으로 고정한다.
                "0.6,10,6,3.0,10,false,2,2,1,2,3,15,4,17,10",
                "0.7,10,6,3.0,10,false,2,2,0,2,3,,4,17,0",
                "0.6,5,3,5.0,10,false,2,2,1,2,3,12,4,17,13");
    }

    @Test
    @DisplayName("CSV 머리줄은 Python report.py 열과 약속한 문자열이다 (계획 9.1절)")
    void headersMatchContract() {
        assertThat(E5Sweep.TICKS_HEADER)
                .isEqualTo("t,zone_grade,max_density,inflow_avg,inflow_alert,n_unstable,unstable_cells,events");
        assertThat(E5Sweep.ALERTS_HEADER).isEqualTo("t,reason,level,value,cell_ids");
        assertThat(E5Sweep.INSTABILITY_HEADER).isEqualTo("pressure,seconds,min_density,is_default,n_instability,"
                + "n_grade_up,n_inflow,first_instability_t,first_grade_up_t,first_inflow_t,unstable_s,critical_s,"
                + "inflow_on_s");
        assertThat(E5Sweep.INFLOW_HEADER).isEqualTo("ratio,window_seconds,min_samples,min_count,off_seconds,"
                + "is_default,n_instability,n_grade_up,n_inflow,first_instability_t,first_grade_up_t,first_inflow_t,"
                + "unstable_s,critical_s,inflow_on_s");
    }

    @Test
    @DisplayName("초별 행은 40개이고 판정 대상 불안정 셀·알림 사건·유입 경보를 담는다")
    void tickRowsDescribeEachSecond() {
        List<String> rows = E5Sweep.tickRows(replayDefault(fixture()));

        assertThat(rows).hasSize(40);
        assertThat(rows.get(0)).isEqualTo("0,NORMAL,3.0,,false,0,,");
        assertThat(rows.get(1)).isEqualTo("1,CAUTION,3.0,,false,0,,");
        assertThat(rows.get(2)).isEqualTo("2,CAUTION,3.0,,false,1,c-0000,INSTABILITY:CRITICAL");
        assertThat(rows.get(3)).isEqualTo("3,CRITICAL,3.0,,false,1,c-0000,GRADE_UP:CRITICAL");
        String[] t12 = rows.get(12).split(",", -1);
        assertThat(Double.parseDouble(t12[3])).isCloseTo(0.8, within(1e-12));
        assertThat(t12[4]).isEqualTo("true");
        assertThat(t12[7]).isEqualTo("INFLOW:CAUTION");
        String[] t13 = rows.get(13).split(",", -1);
        assertThat(t13[1]).isEqualTo("ALERT");
        assertThat(t13[4]).isEqualTo("true");
        assertThat(t13[7]).isEmpty();
    }

    @Test
    @DisplayName("알림 행은 서버가 내는 순서이고 INFLOW의 셀 ID는 빈칸이다")
    void alertRowsFollowServerOrder() {
        List<String> rows = E5Sweep.alertRows(replayDefault(fixture()));

        assertThat(rows).containsExactly(
                "2,INSTABILITY,CRITICAL,0.03,c-0000",
                "3,GRADE_UP,CRITICAL,3.0,c-0000",
                "12,INFLOW,CAUTION,0.8,",
                "32,INSTABILITY,CRITICAL,0.03,c-0000",
                "33,GRADE_UP,CRITICAL,3.0,c-0000");
    }

    @Test
    @DisplayName("main은 없는 출력 폴더를 만들고 타임라인 이름으로 CSV 4개를 LF로 쓴다")
    void mainWritesFourCsvFiles() throws IOException {
        Path out = dir.resolve("out");

        E5Sweep.main(new String[] {fixture().toString(), out.toString()});

        assertCsv(out.resolve("e5_sweep_v02_ticks.csv"), E5Sweep.TICKS_HEADER, 40);
        assertCsv(out.resolve("e5_sweep_v02_alerts.csv"), E5Sweep.ALERTS_HEADER, 5);
        assertCsv(out.resolve("e5_sweep_v02_sweep_instability.csv"), E5Sweep.INSTABILITY_HEADER, 60);
        assertCsv(out.resolve("e5_sweep_v02_sweep_inflow.csv"), E5Sweep.INFLOW_HEADER, 45);
    }

    @Test
    @DisplayName("인자가 2개가 아니면 사용법을 담은 IllegalArgumentException")
    void mainRejectsWrongArgumentCount() {
        assertThatThrownBy(() -> E5Sweep.main(new String[] {fixture().toString()}))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("사용법");
    }

    /** 머리줄 + rows행, 모든 줄 끝이 LF(CR 없음)인지 본다. */
    private static void assertCsv(Path file, String header, int rows) throws IOException {
        String text = Files.readString(file, StandardCharsets.UTF_8);
        assertThat(text).doesNotContain("\r").endsWith("\n");
        List<String> lines = text.lines().toList();
        assertThat(lines).hasSize(rows + 1);
        assertThat(lines.getFirst()).isEqualTo(header);
    }
}
