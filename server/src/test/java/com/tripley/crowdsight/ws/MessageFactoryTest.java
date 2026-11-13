package com.tripley.crowdsight.ws;

import static com.tripley.crowdsight.grade.Grade.ALERT;
import static com.tripley.crowdsight.grade.Grade.CAUTION;
import static com.tripley.crowdsight.grade.Grade.CRITICAL;
import static com.tripley.crowdsight.grade.Grade.NORMAL;
import static com.tripley.crowdsight.timeline.TimelineFixtures.MAPPER;
import static com.tripley.crowdsight.timeline.TimelineFixtures.fixturePath;
import static com.tripley.crowdsight.timeline.TimelineFixtures.timelineWithInflow;
import static org.assertj.core.api.Assertions.assertThat;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneId;
import java.util.List;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;

import com.tripley.crowdsight.config.TestProperties;
import com.tripley.crowdsight.grade.DensityThresholds;
import com.tripley.crowdsight.replay.PlaybackSnapshot;
import com.tripley.crowdsight.replay.PlaybackState;
import com.tripley.crowdsight.replay.ZonePlayer;
import com.tripley.crowdsight.replay.ZoneRuntime;
import com.tripley.crowdsight.replay.ZoneStep;
import com.tripley.crowdsight.timeline.TimelineLoader;
import com.tripley.crowdsight.timeline.ZoneTimeline;
import com.tripley.crowdsight.ws.message.CellView;
import com.tripley.crowdsight.ws.message.HelloMessage;
import com.tripley.crowdsight.ws.message.PlaybackMessage;
import com.tripley.crowdsight.ws.message.PlaybackView;
import com.tripley.crowdsight.ws.message.ThresholdsView;
import com.tripley.crowdsight.ws.message.ZoneStateMessage;
import com.tripley.crowdsight.ws.message.ZoneView;

class MessageFactoryTest {

    static final Clock FIXED = Clock.fixed(Instant.parse("2026-11-18T05:02:31.512Z"), ZoneId.of("Asia/Seoul"));
    static final String FIXED_TS = "2026-11-18T14:02:31.512+09:00";

    private final MessageFactory messages = new MessageFactory(FIXED, TestProperties.replay(1000, true));
    private ZoneTimeline timeline;
    private ZoneRuntime runtime;

    /** fixture valid_v02.json을 읽는다 (검증기를 거친다). */
    static ZoneTimeline fixtureTimeline() {
        return new TimelineLoader(MAPPER, TestProperties.of(fixturePath().getParent().toString(),
                List.of("valid_v02.json"), 1000, true)).loadAll().get(0);
    }

    /** 반복 재생하는 fixture 런타임. */
    static ZoneRuntime fixtureRuntime(ZoneTimeline timeline) {
        return new ZoneRuntime(new ZonePlayer(timeline, true), TestProperties.grader(timeline.meta().cells()));
    }

    /** tick을 n번 하고 마지막 step을 준다. */
    static ZoneStep tickTimes(ZoneRuntime runtime, int n) {
        ZoneStep last = null;
        for (int i = 0; i < n; i++) {
            last = runtime.tick().orElseThrow();
        }
        return last;
    }

    @BeforeEach
    void setUp() {
        timeline = fixtureTimeline();
        runtime = fixtureRuntime(timeline);
    }

    @Test
    @DisplayName("hello는 meta 원본·재생 상태·기준값·빈 미확인 알림을 담는다")
    void helloFromFixture() {
        HelloMessage hello = messages.hello(runtime);

        assertThat(hello.type()).isEqualTo("hello");
        assertThat(hello.schemaVersion()).isEqualTo("0.2");
        assertThat(hello.zoneId()).isEqualTo("zone-test");
        assertThat(hello.meta()).isSameAs(timeline.metaJson());
        assertThat(hello.playback()).isEqualTo(new PlaybackView("playing", 0, true, 5));
        assertThat(hello.thresholds()).isEqualTo(new ThresholdsView(new DensityThresholds(3.0, 4.0, 5.0), 0.02, 0.6));
        assertThat(hello.unackedAlerts()).isEmpty();
    }

    @Test
    @DisplayName("hello 재생 위치는 마지막으로 준 프레임이다")
    void helloReflectsCurrentPlayback() {
        tickTimes(runtime, 3);

        assertThat(messages.hello(runtime).playback().t()).isEqualTo(2);
    }

    @Test
    @DisplayName("t4 zone_state는 fixture 판정과 같다")
    void zoneStateAtT4() {
        ZoneStep step = tickTimes(runtime, 5);

        ZoneStateMessage message = messages.zoneState("zone-test", step, messages.frameTs());

        assertThat(message.type()).isEqualTo("zone_state");
        assertThat(message.zoneId()).isEqualTo("zone-test");
        assertThat(message.t()).isEqualTo(4);
        assertThat(message.frameTs()).isEqualTo(FIXED_TS);
        assertThat(message.zone()).isEqualTo(new ZoneView(CAUTION, 4.2, 0.65, false, null));
        assertThat(message.cells()).containsExactly(
                new CellView("c-0000", CAUTION, 4.2, 0.3, -0.1, 0.012, 0.0504, 0.25, 4.6, ALERT),
                new CellView("c-0001", NORMAL, 1.5, 0.2, 0.0, 0.006, 0.009, null, 1.6, NORMAL),
                new CellView("c-0102", ALERT, 5.5, 0.2, 0.1, 0.006, 0.033, null, 5.9, CRITICAL));
    }

    @Test
    @DisplayName("null 값은 null 그대로 옮긴다")
    void zoneStateAtT0KeepsNulls() {
        ZoneStep step = tickTimes(runtime, 1);

        ZoneStateMessage message = messages.zoneState("zone-test", step, FIXED_TS);

        assertThat(message.zone()).isEqualTo(new ZoneView(NORMAL, 1.25, null, false, 6.5));
        assertThat(message.cells().get(1))
                .isEqualTo(new CellView("c-0001", NORMAL, 0.0, null, null, null, 0.0, null, null, null));
    }

    @ParameterizedTest
    @CsvSource({"PLAYING,playing", "PAUSED,paused", "ENDED,ended"})
    @DisplayName("재생 상태는 소문자로 보낸다")
    void playbackStateLowercase(PlaybackState state, String expected) {
        PlaybackMessage message = messages.playback("zone-test", new PlaybackSnapshot(state, 4, false, 5));

        assertThat(message).isEqualTo(new PlaybackMessage("playback", "zone-test", expected, 4, false));
    }

    @Test
    @DisplayName("zone.inflow_alert는 판정 결과를 옮긴다")
    void zoneStateCarriesInflowAlert() {
        ZoneRuntime inflow = fixtureRuntime(timelineWithInflow(5, 0.8, 5.0));

        ZoneView t3 = messages.zoneState("zone-test", tickTimes(inflow, 4), messages.frameTs()).zone();
        ZoneView t4 = messages.zoneState("zone-test", tickTimes(inflow, 1), messages.frameTs()).zone();

        assertThat(t3.inflowAlert()).isFalse();
        assertThat(t4.inflowAlert()).isTrue();
        assertThat(t4.inflowRatio()).isEqualTo(0.8);
        assertThat(t4.count()).isEqualTo(5.0);
    }

    @Test
    @DisplayName("frame_ts는 주입한 시계를 쓴다")
    void frameTsUsesClock() {
        assertThat(messages.frameTs()).isEqualTo(FIXED_TS);
    }
}
