package com.tripley.crowdsight.timeline;

import java.nio.file.Path;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

import tools.jackson.databind.JsonNode;

/**
 * 타임라인 JSON 트리가 규격 v0.2(v0.1 파일 허용)를 지키는지 검사한다.
 * 규칙은 src/predict/schema.py validate_timeline·web/src/lib/validate.ts와 같고 (결정 기록 7),
 * 서버 추가 규칙은 interval_s == 1, 정수 필드는 JSON 정수만(1.0·1.5 거부), frames 1개 이상,
 * schema_version·zone_id·camera_id·video_id 문자열, cell_size_m > 0, models 객체, horizon_s 정수다.
 * '키 없음'과 'null'을 구분해야 하므로 record로 바꾸기 전 JsonNode 단계에서 검사한다.
 * 상태가 없어 여러 스레드에서 불러도 된다.
 */
final class TimelineValidator {

    static final String SUPPORTED_MAJOR = "0";
    /** count·counterflow가 필수가 된 버전의 둘째 자리 (schema.py _V02_MINOR). */
    static final int V02_MINOR = 2;

    private static final Pattern CELL_ID = Pattern.compile("^c-(\\d{2})(\\d{2})$");
    private static final List<String> META_KEYS = List.of("zone_id", "camera_id", "video_id", "duration_s",
            "interval_s", "cell_size_m", "models", "prediction", "cells");
    private static final List<String> CELL_KEYS = List.of("cell_id", "density", "vx", "vy", "speed_var",
            "pressure", "density_pred_60s");
    private static final List<String> NULLABLE_CELL_KEYS = CELL_KEYS.subList(2, CELL_KEYS.size());

    private TimelineValidator() {
    }

    /**
     * 규격에 어긋나면 InvalidTimelineException을 던진다. 검사 순서는 schema.py와 같다.
     *
     * @param root 파일 전체 트리
     * @param file 메시지에 넣을 파일 절대 경로
     */
    static void validate(JsonNode root, Path file) {
        if (root == null || !root.isObject() || !root.path("meta").isObject() || !root.path("frames").isArray()) {
            throw fail(file, "timeline 형식 오류: meta(객체)와 frames(배열)가 필요합니다.");
        }
        JsonNode version = root.path("schema_version");
        if (!version.isString() || !version.asString().split("\\.", -1)[0].equals(SUPPORTED_MAJOR)) {
            throw fail(file, "지원하지 않는 schema_version: " + (version.isMissingNode() ? "(없음)" : version));
        }
        boolean requireV02 = schemaMinor(version.asString()) >= V02_MINOR;

        JsonNode meta = root.get("meta");
        for (String key : META_KEYS) {
            if (!meta.has(key)) {
                throw fail(file, "meta." + key + " 가 없습니다.");
            }
        }
        for (String key : List.of("zone_id", "camera_id", "video_id")) {
            JsonNode value = meta.get(key);
            if (!value.isString() || value.asString().isBlank()) {
                throw fail(file, "meta." + key + " 는 비어 있지 않은 문자열이어야 합니다.");
            }
        }
        JsonNode interval = meta.get("interval_s");
        if (!isInt(interval) || interval.intValue() != 1) {
            throw fail(file, "meta.interval_s 는 1 이어야 합니다 (서버는 1초 간격만 재생합니다): " + interval);
        }
        JsonNode cellSize = meta.get("cell_size_m");
        if (!cellSize.isNumber() || cellSize.doubleValue() <= 0) {
            throw fail(file, "meta.cell_size_m 는 0보다 큰 숫자여야 합니다.");
        }
        if (!meta.get("models").isObject()) {
            throw fail(file, "meta.models 는 객체여야 합니다.");
        }
        if (!meta.get("cells").isArray()) {
            throw fail(file, "meta.cells 는 배열이어야 합니다.");
        }
        JsonNode duration = meta.get("duration_s");
        int frameCount = root.get("frames").size();
        if (!isInt(duration)) {
            throw fail(file, "meta.duration_s 는 정수여야 합니다.");
        }
        if (duration.intValue() != frameCount) {
            throw fail(file, "meta.duration_s(" + duration + ") 와 frames 개수(" + frameCount + ") 가 다릅니다.");
        }
        if (frameCount < 1) {
            throw fail(file, "frames 가 비어 있습니다 (재생할 프레임이 1개 이상 필요합니다).");
        }
        JsonNode prediction = meta.get("prediction");
        JsonNode history = prediction.path("history_s");
        if (!prediction.isObject() || !isInt(history) || history.intValue() < 1) {
            throw fail(file, "meta.prediction.history_s 는 1 이상의 정수여야 합니다.");
        }
        if (!isInt(prediction.path("horizon_s"))) {
            throw fail(file, "meta.prediction.horizon_s 는 정수여야 합니다.");
        }
        int predMinT = history.intValue() - 1;

        List<String> ids = validateMetaCells(meta.get("cells"), file);

        JsonNode frames = root.get("frames");
        for (int i = 0; i < frames.size(); i++) {
            validateFrame(frames.get(i), i, ids, requireV02, predMinT, file);
        }
    }

    /** "0.2"의 둘째 자리(2). schema.py _schema_minor와 같게 없거나 숫자가 아니면 0. */
    static int schemaMinor(String version) {
        String[] parts = version.split("\\.", -1);
        if (parts.length < 2 || !parts[1].matches("\\d+")) {
            return 0;
        }
        return parts[1].length() > 9 ? Integer.MAX_VALUE : Integer.parseInt(parts[1]);
    }

    private static List<String> validateMetaCells(JsonNode cells, Path file) {
        List<String> ids = new ArrayList<>();
        for (JsonNode cell : cells) {
            JsonNode idNode = cell.path("cell_id");
            Matcher m = idNode.isString() ? CELL_ID.matcher(idNode.asString()) : null;
            if (m == null || !m.matches()) {
                throw fail(file, "cell_id 형식 오류: " + idNode + " (c-행2자리열2자리)");
            }
            String id = idNode.asString();
            JsonNode row = cell.path("row");
            JsonNode col = cell.path("col");
            if (!isInt(row) || !isInt(col) || row.intValue() != Integer.parseInt(m.group(1))
                    || col.intValue() != Integer.parseInt(m.group(2))) {
                throw fail(file, "cell_id " + id + " 와 row/col 이 다릅니다.");
            }
            JsonNode area = cell.path("walkable_area_m2");
            if (!area.isNumber() || area.doubleValue() <= 0) {
                throw fail(file, id + ": walkable_area_m2 는 0보다 커야 합니다 (0인 셀은 목록에서 뺌).");
            }
            if (!isPolygon(cell.path("image_polygon"))) {
                throw fail(file, id + ": image_polygon 은 0~1 좌표 4개여야 합니다.");
            }
            ids.add(id);
        }
        if (new HashSet<>(ids).size() != ids.size()) {
            throw fail(file, "meta.cells 에 중복 cell_id 가 있습니다.");
        }
        return ids;
    }

    private static void validateFrame(JsonNode frame, int i, List<String> ids, boolean requireV02,
                                      int predMinT, Path file) {
        JsonNode t = frame.path("t");
        if (!isInt(t) || t.intValue() != i) {
            throw fail(file, "frames[" + i + "].t 는 " + i + " 이어야 합니다 (0부터 빠짐없이 증가하는 정수).");
        }
        JsonNode ratio = frame.path("inflow_ratio");
        if (!isAbsent(ratio) && !(ratio.isNumber() && isUnit(ratio))) {
            throw fail(file, "t=" + i + ": inflow_ratio 는 0~1 또는 null 입니다.");
        }
        if (requireV02 && !frame.has("count")) {
            throw fail(file, "t=" + i + ": count 필드가 없습니다 (v0.2 부터 필수, 아직 없으면 null).");
        }
        JsonNode count = frame.path("count");
        if (!isAbsent(count) && !(count.isNumber() && count.doubleValue() >= 0)) {
            throw fail(file, "t=" + i + ": count 는 0 이상의 숫자 또는 null 입니다.");
        }
        JsonNode cells = frame.path("cells");
        if (!cells.isArray() || !idsOf(cells).equals(ids)) {
            throw fail(file, "t=" + i + ": cells 는 meta.cells 와 같은 순서로 모든 셀을 담아야 합니다.");
        }
        for (JsonNode cell : cells) {
            validateCell(cell, i, requireV02, predMinT, file);
        }
    }

    private static void validateCell(JsonNode cell, int t, boolean requireV02, int predMinT, Path file) {
        String where = "t=" + t + " " + cell.get("cell_id").asString() + ": ";
        for (String key : CELL_KEYS) {
            if (!cell.has(key)) {
                throw fail(file, where + key + " 필드가 없습니다 (아직 없으면 null).");
            }
        }
        if (!cell.get("density").isNumber()) {
            throw fail(file, where + "density 는 숫자여야 합니다.");
        }
        for (String key : NULLABLE_CELL_KEYS) {
            JsonNode value = cell.get(key);
            if (!value.isNull() && !value.isNumber()) {
                throw fail(file, where + key + " 는 숫자 또는 null 입니다.");
            }
        }
        if (requireV02 && !cell.has("counterflow")) {
            throw fail(file, where + "counterflow 필드가 없습니다 (v0.2 부터 필수, 아직 없으면 null).");
        }
        JsonNode counterflow = cell.path("counterflow");
        if (!isAbsent(counterflow) && !(counterflow.isNumber() && isUnit(counterflow))) {
            throw fail(file, where + "counterflow 는 0~1 또는 null 입니다.");
        }
        if (t < predMinT && !cell.get("density_pred_60s").isNull()) {
            throw fail(file, where + "t < " + predMinT + " 이면 density_pred_60s 는 null 입니다.");
        }
    }

    private static List<String> idsOf(JsonNode cells) {
        List<String> ids = new ArrayList<>();
        for (JsonNode cell : cells) {
            JsonNode id = cell.path("cell_id");
            ids.add(id.isString() ? id.asString() : null);
        }
        return ids;
    }

    private static boolean isPolygon(JsonNode polygon) {
        if (!polygon.isArray() || polygon.size() != 4) {
            return false;
        }
        for (JsonNode point : polygon) {
            if (!point.isArray() || point.size() != 2) {
                return false;
            }
            for (JsonNode xy : point) {
                if (!xy.isNumber() || !isUnit(xy)) {
                    return false;
                }
            }
        }
        return true;
    }

    /** JSON 정수이고 int 범위 (Jackson이 1.5를 1로 자르므로 record 변환 전에 본다). */
    private static boolean isInt(JsonNode node) {
        return node.isIntegralNumber() && node.canConvertToInt();
    }

    private static boolean isAbsent(JsonNode node) {
        return node.isMissingNode() || node.isNull();
    }

    private static boolean isUnit(JsonNode number) {
        double v = number.doubleValue();
        return v >= 0 && v <= 1;
    }

    private static InvalidTimelineException fail(Path file, String reason) {
        return new InvalidTimelineException(file, reason);
    }
}
