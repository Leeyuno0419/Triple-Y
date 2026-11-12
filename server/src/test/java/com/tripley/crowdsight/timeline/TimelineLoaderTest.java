package com.tripley.crowdsight.timeline;

import static com.tripley.crowdsight.timeline.TimelineFixtures.MAPPER;
import static com.tripley.crowdsight.timeline.TimelineFixtures.cell;
import static com.tripley.crowdsight.timeline.TimelineFixtures.fixturePath;
import static com.tripley.crowdsight.timeline.TimelineFixtures.frame;
import static com.tripley.crowdsight.timeline.TimelineFixtures.meta;
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;

import com.tripley.crowdsight.config.TestProperties;

import tools.jackson.databind.JsonNode;
import tools.jackson.databind.node.ObjectNode;

class TimelineLoaderTest {

    private static TimelineLoader loader(String dir, List<String> files) {
        return new TimelineLoader(MAPPER, TestProperties.of(dir, files, 1000, true));
    }

    private static TimelineLoader loader() {
        return loader(fixturePath().getParent().toString(), List.of("valid_v02.json"));
    }

    @Test
    @DisplayName("v0.2 fixture를 record로 읽는다")
    void loadsValidV02() {
        ZoneTimeline timeline = loader().load(fixturePath());

        assertThat(timeline.zoneId()).isEqualTo("zone-test");
        assertThat(timeline.schemaVersion()).isEqualTo("0.2");
        assertThat(timeline.meta().cells()).hasSize(3);
        assertThat(timeline.frames()).hasSize(5);
        assertThat(timeline.meta().cells().get(2).walkableAreaM2()).isEqualTo(1.5);
        List<Frame> frames = timeline.frames();
        assertThat(frames.get(0).count()).isEqualTo(6.5);
        assertThat(frames.get(3).count()).isEqualTo(22.8);
        assertThat(frames.get(4).count()).isNull();
        assertThat(frames.get(0).inflowRatio()).isNull();
        assertThat(frames.get(1).inflowRatio()).isEqualTo(0.3);
        assertThat(frames.get(2).cells().get(1).vx()).isNull();
        assertThat(frames.get(0).cells().get(1).density()).isEqualTo(0.0);
        assertThat(frames.get(0).cells().get(1).pressure()).isEqualTo(0.0);
        assertThat(frames.get(1).cells().get(0).counterflow()).isEqualTo(0.12);
        assertThat(frames.get(3).cells().get(0).densityPred60s()).isEqualTo(3.6);
        assertThat(timeline.meta().prediction().historyS()).isEqualTo(2);
        assertThat(timeline.metaJson().get("zone_id").asString()).isEqualTo("zone-test");
        assertThat(timeline.source().isAbsolute()).isTrue();
        assertThat(timeline.source().toString()).endsWith("valid_v02.json");
    }

    @Test
    @DisplayName("v0.1 파일은 count·counterflow를 null로 읽는다")
    void loadsV01WithoutCountAndCounterflow() {
        ObjectNode tree = TimelineFixtures.validTree();
        tree.put("schema_version", "0.1");
        for (JsonNode f : tree.get("frames")) {
            ((ObjectNode) f).remove("count");
            for (JsonNode c : f.get("cells")) {
                ((ObjectNode) c).remove("counterflow");
            }
        }

        ZoneTimeline timeline = loader().fromTree(tree, fixturePath());

        assertThat(timeline.schemaVersion()).isEqualTo("0.1");
        assertThat(timeline.frames()).allSatisfy(f -> {
            assertThat(f.count()).isNull();
            assertThat(f.cells()).allSatisfy(c -> assertThat(c.counterflow()).isNull());
        });
    }

    @Test
    @DisplayName("v0.2의 null count·counterflow는 null로 읽는다")
    void loadsV02WithNullCountAndCounterflow() {
        ObjectNode tree = TimelineFixtures.validTree();
        frame(tree, 1).putNull("count");
        cell(tree, 1, 0).putNull("counterflow");

        ZoneTimeline timeline = loader().fromTree(tree, fixturePath());

        assertThat(timeline.frames().get(1).count()).isNull();
        assertThat(timeline.frames().get(1).cells().get(0).counterflow()).isNull();
    }

    @Test
    @DisplayName("모르는 키는 무시하고 metaJson에는 남긴다")
    void ignoresUnknownKeys() {
        ObjectNode tree = TimelineFixtures.validTree();
        meta(tree).put("foo", 1);
        frame(tree, 0).put("bar", "x");
        cell(tree, 0, 0).put("baz", true);

        ZoneTimeline timeline = loader().fromTree(tree, fixturePath());

        assertThat(timeline.metaJson().get("foo").intValue()).isEqualTo(1);
    }

    @Test
    @DisplayName("파일이 없으면 절대 경로를 넣어 거부한다")
    void rejectsMissingFileWithAbsolutePath(@TempDir Path dir) {
        Path missing = dir.resolve("nope.json");

        assertThatThrownBy(() -> loader().load(missing))
                .isInstanceOf(InvalidTimelineException.class)
                .hasMessageContaining(missing.toAbsolutePath().normalize().toString())
                .hasMessageContaining("파일이 없습니다");
    }

    @ParameterizedTest
    @ValueSource(strings = {"{", "{\"a\": NaN}", "{} {}"})
    @DisplayName("JSON으로 읽을 수 없으면 거부한다")
    void rejectsUnreadableJson(String content, @TempDir Path dir) throws IOException {
        Path bad = dir.resolve("bad.json");
        Files.writeString(bad, content);

        assertThatThrownBy(() -> loader().load(bad))
                .isInstanceOf(InvalidTimelineException.class)
                .hasMessageContaining("JSON을 읽을 수 없습니다")
                .hasMessageContaining(bad.toAbsolutePath().normalize().toString());
    }

    @Test
    @DisplayName("설정한 폴더의 파일을 읽는다")
    void loadAllReadsConfiguredFiles() {
        List<ZoneTimeline> timelines = loader().loadAll();

        assertThat(timelines).hasSize(1);
        assertThat(timelines.get(0).zoneId()).isEqualTo("zone-test");
    }

    @Test
    @DisplayName("같은 zone_id가 두 번이면 거부한다")
    void rejectsDuplicateZone() {
        TimelineLoader loader = loader(fixturePath().getParent().toString(),
                List.of("valid_v02.json", "valid_v02.json"));

        assertThatThrownBy(loader::loadAll)
                .isInstanceOf(InvalidTimelineException.class)
                .hasMessageContaining("zone_id 중복: zone-test");
    }
}
