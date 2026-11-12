package com.tripley.crowdsight.timeline;

import java.net.URISyntaxException;
import java.nio.file.Path;
import java.util.List;
import java.util.stream.IntStream;

import tools.jackson.databind.PropertyNamingStrategies;
import tools.jackson.databind.json.JsonMapper;
import tools.jackson.databind.node.ObjectNode;

/** 테스트용 타임라인. validTree()는 부를 때마다 새로 읽으므로 고쳐도 다른 테스트에 영향이 없다. */
public final class TimelineFixtures {

    public static final JsonMapper MAPPER = JsonMapper.builder()
            .propertyNamingStrategy(PropertyNamingStrategies.SNAKE_CASE)   // application.yml과 같게
            .build();

    private TimelineFixtures() {
    }

    /** classpath의 valid_v02.json 절대 경로 (build/resources/test/timeline/...). */
    public static Path fixturePath() {
        try {
            return Path.of(TimelineFixtures.class.getResource("/timeline/valid_v02.json").toURI());
        } catch (URISyntaxException e) {
            throw new IllegalStateException(e);
        }
    }

    /** fixture 전체 트리 (새로 읽은 것). */
    public static ObjectNode validTree() {
        return (ObjectNode) MAPPER.readTree(fixturePath());
    }

    /** 루트의 meta 객체. */
    public static ObjectNode meta(ObjectNode root) {
        return (ObjectNode) root.get("meta");
    }

    /** meta.cells[index]. */
    public static ObjectNode metaCell(ObjectNode root, int index) {
        return (ObjectNode) root.get("meta").get("cells").get(index);
    }

    /** frames[t]. */
    public static ObjectNode frame(ObjectNode root, int t) {
        return (ObjectNode) root.get("frames").get(t);
    }

    /** frames[t].cells[index]. */
    public static ObjectNode cell(ObjectNode root, int t, int index) {
        return (ObjectNode) frame(root, t).get("cells").get(index);
    }

    /** 재생 시험용 최소 타임라인 (셀 없음, t=0..duration-1). 검증기를 거치지 않는다. */
    public static ZoneTimeline timelineOf(int duration) {
        Meta meta = new Meta("zone-test", "cam-test", "TEST_001", duration, 1, 2.0,
                new Models("fixture", "fixture", "fixture"), new Prediction(2, 60), List.of());
        List<Frame> frames = IntStream.range(0, duration)
                .mapToObj(t -> new Frame(t, null, null, List.of()))
                .toList();
        return new ZoneTimeline("0.2", meta, frames, MAPPER.createObjectNode(), Path.of("synthetic.json"));
    }
}
