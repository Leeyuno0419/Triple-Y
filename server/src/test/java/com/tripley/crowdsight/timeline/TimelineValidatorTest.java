package com.tripley.crowdsight.timeline;

import static com.tripley.crowdsight.timeline.TimelineFixtures.MAPPER;
import static com.tripley.crowdsight.timeline.TimelineFixtures.cell;
import static com.tripley.crowdsight.timeline.TimelineFixtures.frame;
import static com.tripley.crowdsight.timeline.TimelineFixtures.meta;
import static com.tripley.crowdsight.timeline.TimelineFixtures.metaCell;
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatCode;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.nio.file.Path;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;

import tools.jackson.databind.JsonNode;
import tools.jackson.databind.node.ArrayNode;
import tools.jackson.databind.node.DoubleNode;
import tools.jackson.databind.node.ObjectNode;

class TimelineValidatorTest {

    private static final Path FILE = Path.of("fixture.json").toAbsolutePath();

    private ObjectNode tree;

    @BeforeEach
    void setUp() {
        tree = TimelineFixtures.validTree();
    }

    private void assertRejected(JsonNode root, String message) {
        assertThatThrownBy(() -> TimelineValidator.validate(root, FILE))
                .isInstanceOf(InvalidTimelineException.class)
                .hasMessageContaining(message);
    }

    private void assertRejected(String message) {
        assertRejected(tree, message);
    }

    private void assertAccepted() {
        assertThatCode(() -> TimelineValidator.validate(tree, FILE)).doesNotThrowAnyException();
    }

    private ArrayNode frames() {
        return (ArrayNode) tree.get("frames");
    }

    @Test
    @DisplayName("fixture는 통과한다")
    void acceptsFixture() {
        assertAccepted();
    }

    @Test
    @DisplayName("오류 메시지에 파일 절대 경로가 들어간다")
    void messageHasAbsolutePath() {
        meta(tree).put("interval_s", 2);

        assertThatThrownBy(() -> TimelineValidator.validate(tree, FILE))
                .isInstanceOfSatisfying(InvalidTimelineException.class, e -> {
                    assertThat(e.getMessage()).contains(FILE.toString());
                    assertThat(e.file()).isEqualTo(FILE);
                });
    }

    @Test
    @DisplayName("루트가 객체가 아니면 거부한다")
    void rejectsNonObjectRoot() {
        assertRejected(MAPPER.createArrayNode(), "meta(객체)와 frames(배열)");
    }

    @Test
    @DisplayName("앞자리가 0이 아닌 버전은 거부한다")
    void rejectsMajorVersion() {
        tree.put("schema_version", "1.0");

        assertRejected("지원하지 않는 schema_version");
    }

    @Test
    @DisplayName("schema_version이 없으면 거부한다")
    void rejectsMissingSchemaVersion() {
        tree.remove("schema_version");

        assertRejected("schema_version: (없음)");
    }

    @Test
    @DisplayName("schema_version이 숫자면 거부한다 (서버 추가)")
    void rejectsNumericSchemaVersion() {
        tree.put("schema_version", 0.2);

        assertRejected("schema_version");
    }

    @Test
    @DisplayName("meta 필수 키가 빠지면 거부한다")
    void rejectsMissingMetaKey() {
        meta(tree).remove("camera_id");

        assertRejected("meta.camera_id 가 없습니다");
    }

    @Test
    @DisplayName("zone_id가 빈 문자열이면 거부한다 (서버 추가)")
    void rejectsBlankZoneId() {
        meta(tree).put("zone_id", "");

        assertRejected("meta.zone_id 는 비어 있지 않은 문자열");
    }

    @Test
    @DisplayName("interval_s가 1이 아니면 거부한다 (서버 추가)")
    void rejectsInterval2() {
        meta(tree).put("interval_s", 2);

        assertRejected("meta.interval_s 는 1 이어야 합니다");
    }

    @Test
    @DisplayName("interval_s 1.0도 거부한다 (서버 추가)")
    void rejectsFractionalInterval() {
        meta(tree).put("interval_s", 1.0);

        assertRejected("meta.interval_s 는 1 이어야 합니다");
    }

    @Test
    @DisplayName("cell_size_m가 0이면 거부한다 (서버 추가)")
    void rejectsZeroCellSize() {
        meta(tree).put("cell_size_m", 0);

        assertRejected("meta.cell_size_m");
    }

    @Test
    @DisplayName("models가 객체가 아니면 거부한다 (서버 추가)")
    void rejectsNonObjectModels() {
        meta(tree).put("models", "x");

        assertRejected("meta.models 는 객체");
    }

    @Test
    @DisplayName("duration_s와 프레임 수가 다르면 거부한다")
    void rejectsDurationMismatch() {
        meta(tree).put("duration_s", 6);

        assertRejected("meta.duration_s(6) 와 frames 개수(5) 가 다릅니다");
    }

    @Test
    @DisplayName("duration_s 5.0은 거부한다 (서버 추가)")
    void rejectsFractionalDuration() {
        meta(tree).put("duration_s", 5.0);

        assertRejected("meta.duration_s 는 정수여야");
    }

    @Test
    @DisplayName("프레임이 없으면 거부한다 (서버 추가)")
    void rejectsEmptyFrames() {
        meta(tree).put("duration_s", 0);
        frames().removeAll();

        assertRejected("frames 가 비어 있습니다");
    }

    @Test
    @DisplayName("history_s가 0이면 거부한다")
    void rejectsHistoryZero() {
        ((ObjectNode) meta(tree).get("prediction")).put("history_s", 0);

        assertRejected("history_s 는 1 이상의 정수");
    }

    @Test
    @DisplayName("horizon_s가 정수가 아니면 거부한다 (서버 추가)")
    void rejectsFractionalHorizon() {
        ((ObjectNode) meta(tree).get("prediction")).put("horizon_s", 60.5);

        assertRejected("horizon_s 는 정수");
    }

    @Test
    @DisplayName("cell_id 형식이 틀리면 거부한다")
    void rejectsCellIdFormat() {
        metaCell(tree, 2).put("cell_id", "c-12");

        assertRejected("cell_id 형식 오류");
    }

    @Test
    @DisplayName("cell_id와 row/col이 다르면 거부한다")
    void rejectsCellIdRowMismatch() {
        metaCell(tree, 2).put("col", 3);

        assertRejected("cell_id c-0102 와 row/col 이 다릅니다");
    }

    @Test
    @DisplayName("row 1.0은 거부한다 (서버 추가)")
    void rejectsFractionalRow() {
        metaCell(tree, 2).put("row", 1.0);

        assertRejected("row/col");
    }

    @Test
    @DisplayName("보행 면적 0인 셀은 거부한다")
    void rejectsZeroArea() {
        metaCell(tree, 2).put("walkable_area_m2", 0);

        assertRejected("c-0102: walkable_area_m2 는 0보다 커야");
    }

    @Test
    @DisplayName("다각형 좌표가 0~1 밖이면 거부한다")
    void rejectsPolygonOutOfRange() {
        ((ArrayNode) metaCell(tree, 0).get("image_polygon").get(1)).set(0, DoubleNode.valueOf(1.2));

        assertRejected("c-0000: image_polygon");
    }

    @Test
    @DisplayName("cell_id가 중복이면 거부한다")
    void rejectsDuplicateCellId() {
        ArrayNode cells = (ArrayNode) meta(tree).get("cells");
        cells.set(1, cells.get(0).deepCopy());

        assertRejected("중복 cell_id");
    }

    @Test
    @DisplayName("t가 빠지면 거부한다")
    void rejectsGapInT() {
        frame(tree, 3).put("t", 4);

        assertRejected("frames[3].t 는 3 이어야");
    }

    @Test
    @DisplayName("t 1.5는 거부한다")
    void rejectsFractionalT() {
        frame(tree, 1).put("t", 1.5);

        assertRejected("frames[1].t");
    }

    @Test
    @DisplayName("t 1.0도 거부한다 (서버 추가, Jackson 정수 변환 방지)")
    void rejectsIntegralFloatT() {
        frame(tree, 1).put("t", 1.0);

        assertRejected("frames[1].t");
    }

    @Test
    @DisplayName("inflow_ratio가 1을 넘으면 거부한다")
    void rejectsInflowOutOfRange() {
        frame(tree, 1).put("inflow_ratio", 1.2);

        assertRejected("t=1: inflow_ratio 는 0~1 또는 null");
    }

    @Test
    @DisplayName("inflow_ratio 키가 없어도 통과한다")
    void acceptsMissingInflowKey() {
        frame(tree, 1).remove("inflow_ratio");

        assertAccepted();
    }

    @Test
    @DisplayName("v0.2에서 count 키가 없으면 거부한다")
    void rejectsMissingCountV02() {
        frame(tree, 1).remove("count");

        assertRejected("t=1: count 필드가 없습니다");
    }

    @Test
    @DisplayName("count가 0이면 통과한다")
    void acceptsZeroCount() {
        frame(tree, 1).put("count", 0);

        assertAccepted();
    }

    @Test
    @DisplayName("count가 음수면 거부한다")
    void rejectsNegativeCount() {
        frame(tree, 1).put("count", -1);

        assertRejected("t=1: count 는 0 이상의 숫자 또는 null");
    }

    @Test
    @DisplayName("count가 문자열이면 거부한다")
    void rejectsStringCount() {
        frame(tree, 1).put("count", "6.5");

        assertRejected("t=1: count 는 0 이상");
    }

    @Test
    @DisplayName("v0.1이어도 count가 있으면 범위를 검사한다")
    void rejectsNegativeCountInV01() {
        tree.put("schema_version", "0.1");
        frame(tree, 1).put("count", -1);

        assertRejected("t=1: count");
    }

    @Test
    @DisplayName("셀 순서가 다르면 거부한다")
    void rejectsCellOrder() {
        ArrayNode cells = (ArrayNode) frame(tree, 2).get("cells");
        JsonNode first = cells.get(0);
        cells.set(0, cells.get(1));
        cells.set(1, first);

        assertRejected("t=2: cells 는 meta.cells 와 같은 순서");
    }

    @Test
    @DisplayName("셀이 빠지면 거부한다")
    void rejectsMissingCell() {
        ((ArrayNode) frame(tree, 2).get("cells")).remove(2);

        assertRejected("t=2: cells");
    }

    @Test
    @DisplayName("density가 null이면 거부한다")
    void rejectsNullDensity() {
        cell(tree, 1, 0).putNull("density");

        assertRejected("t=1 c-0000: density 는 숫자여야");
    }

    @Test
    @DisplayName("vx 키가 없으면 거부한다")
    void rejectsMissingVxKey() {
        cell(tree, 1, 0).remove("vx");

        assertRejected("t=1 c-0000: vx 필드가 없습니다");
    }

    @Test
    @DisplayName("pressure가 문자열이면 거부한다")
    void rejectsStringPressure() {
        cell(tree, 1, 1).put("pressure", "0.1");

        assertRejected("t=1 c-0001: pressure 는 숫자 또는 null");
    }

    @Test
    @DisplayName("v0.2에서 counterflow 키가 없으면 거부한다")
    void rejectsMissingCounterflowV02() {
        cell(tree, 1, 0).remove("counterflow");

        assertRejected("t=1 c-0000: counterflow 필드가 없습니다");
    }

    @Test
    @DisplayName("counterflow가 1을 넘으면 거부한다")
    void rejectsCounterflowOutOfRange() {
        cell(tree, 1, 0).put("counterflow", 1.2);

        assertRejected("t=1 c-0000: counterflow 는 0~1 또는 null");
    }

    @Test
    @DisplayName("counterflow가 음수면 거부한다")
    void rejectsNegativeCounterflow() {
        cell(tree, 1, 0).put("counterflow", -0.1);

        assertRejected("t=1 c-0000: counterflow 는 0~1 또는 null");
    }

    @Test
    @DisplayName("history_s−1 이전 초에 예측값이 있으면 거부한다")
    void rejectsEarlyPrediction() {
        cell(tree, 0, 0).put("density_pred_60s", 1.0);

        assertRejected("t=0 c-0000: t < 1 이면 density_pred_60s 는 null");
    }

    @Test
    @DisplayName("v0.1은 count·counterflow 키가 없어도 통과한다")
    void acceptsV01WithoutNewKeys() {
        tree.put("schema_version", "0.1");
        for (JsonNode f : frames()) {
            ((ObjectNode) f).remove("count");
            for (JsonNode c : f.get("cells")) {
                ((ObjectNode) c).remove("counterflow");
            }
        }

        assertAccepted();
    }

    @Test
    @DisplayName("v0.3도 앞자리가 0이면 통과한다")
    void acceptsFutureMinor() {
        tree.put("schema_version", "0.3");

        assertAccepted();
    }

    @ParameterizedTest
    @CsvSource({"0.2, 2", "0.1, 1", "0, 0", "0.x, 0", "0.10, 10", "0.2.1, 2", "0., 0", "0.2a, 0"})
    @DisplayName("버전 둘째 자리는 schema.py와 같게 읽는다")
    void parsesMinorLikeSchemaPy(String version, int expected) {
        assertThat(TimelineValidator.schemaMinor(version)).isEqualTo(expected);
    }
}
