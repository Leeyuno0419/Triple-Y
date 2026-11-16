package com.tripley.crowdsight.ws;

import static com.tripley.crowdsight.timeline.TimelineFixtures.MAPPER;
import static com.tripley.crowdsight.timeline.TimelineFixtures.timelineWithDensity;
import static com.tripley.crowdsight.ws.MessageFactoryTest.FIXED;
import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneId;
import java.util.List;
import java.util.concurrent.atomic.AtomicLong;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;

import com.tripley.crowdsight.alert.Alert;
import com.tripley.crowdsight.alert.AlertStore;
import com.tripley.crowdsight.config.CrowdsightProperties;
import com.tripley.crowdsight.config.TestProperties;
import com.tripley.crowdsight.replay.ZonePlayer;
import com.tripley.crowdsight.replay.ZoneRuntime;
import com.tripley.crowdsight.timeline.ZoneTimeline;

import tools.jackson.databind.JsonNode;

class WsZoneBroadcasterTest {

    private final CrowdsightProperties props = TestProperties.replay(1000, true);
    private final AlertStore store = new AlertStore(props, FIXED);

    /** instant()를 부를 때마다 1 ms씩 가는 시계. frame_ts를 한 tick에 두 번 만들면 값이 달라진다. */
    private static final class SteppingClock extends Clock {
        private final AtomicLong millis = new AtomicLong(Instant.parse("2026-11-18T05:02:31.512Z").toEpochMilli());

        @Override
        public ZoneId getZone() {
            return ZoneId.of("Asia/Seoul");
        }

        @Override
        public Clock withZone(ZoneId zone) {
            throw new UnsupportedOperationException();
        }

        @Override
        public Instant instant() {
            return Instant.ofEpochMilli(millis.getAndIncrement());
        }
    }

    private static ZoneRuntime runtime(ZoneTimeline timeline) {
        return new ZoneRuntime(new ZonePlayer(timeline, true), TestProperties.grader(timeline.meta().cells()));
    }

    /** tick을 n번 하며 매번 zoneState를 보낸다. */
    private static void tickAndSend(ZoneRuntime runtime, WsZoneBroadcaster broadcaster, int n) {
        for (int i = 0; i < n; i++) {
            broadcaster.zoneState("zone-test", runtime.tick().orElseThrow());
        }
    }

    @Test
    @DisplayName("알림은 그 초 zone_state 다음에 같은 t·frame_ts로 보낸다")
    void alertFollowsZoneStateWithSameFrameTs() {
        ZoneSessions sessions = mock(ZoneSessions.class);
        WsZoneBroadcaster broadcaster = new WsZoneBroadcaster(new MessageFactory(new SteppingClock(), props),
                sessions, MAPPER, store);

        tickAndSend(runtime(timelineWithDensity(3, 4.5)), broadcaster, 2);

        ArgumentCaptor<String> captor = ArgumentCaptor.forClass(String.class);
        verify(sessions, times(3)).broadcast(eq("zone-test"), captor.capture());
        List<JsonNode> sent = captor.getAllValues().stream().map(MAPPER::readTree).toList();
        assertThat(sent).extracting(n -> n.get("type").asString()).containsExactly("zone_state", "zone_state", "alert");
        assertThat(sent).extracting(n -> n.get("t").asInt()).containsExactly(0, 1, 1);
        assertThat(sent).extracting(n -> n.get("frame_ts").asString()).containsExactly(
                "2026-11-18T14:02:31.512+09:00", "2026-11-18T14:02:31.513+09:00", "2026-11-18T14:02:31.513+09:00");
        JsonNode alert = sent.get(2);
        assertThat(alert.get("alert_id").asString()).isEqualTo("a-20261118-0001");
        assertThat(alert.get("reason").asString()).isEqualTo("GRADE_UP");
        assertThat(alert.get("level").asString()).isEqualTo("ALERT");
        assertThat(alert.get("value").asDouble()).isEqualTo(4.5);
        assertThat(alert.get("cell_ids").values()).extracting(JsonNode::asString).containsExactly("c-0000");
        assertThat(store.unacked("zone-test")).extracting(Alert::alertId).containsExactly("a-20261118-0001");
    }

    @Test
    @DisplayName("알림이 없는 초에는 zone_state만 보낸다")
    void noAlertNoExtraMessage() {
        ZoneSessions sessions = mock(ZoneSessions.class);
        WsZoneBroadcaster broadcaster = new WsZoneBroadcaster(new MessageFactory(new SteppingClock(), props),
                sessions, MAPPER, store);

        tickAndSend(runtime(timelineWithDensity(3, 4.5)), broadcaster, 1);

        ArgumentCaptor<String> captor = ArgumentCaptor.forClass(String.class);
        verify(sessions, times(1)).broadcast(eq("zone-test"), captor.capture());
        assertThat(MAPPER.readTree(captor.getValue()).get("type").asString()).isEqualTo("zone_state");
        assertThat(store.unacked("zone-test")).isEmpty();
    }

    @Test
    @DisplayName("30분 반복 재생에도 미확인 알림은 상한에서 멈춘다")
    void thirtyMinuteLoopKeepsStoreBounded() {
        WsZoneBroadcaster broadcaster = new WsZoneBroadcaster(new MessageFactory(FIXED, props),
                new ZoneSessions(props), MAPPER, store);
        ZoneRuntime runtime = runtime(timelineWithDensity(10, 4.5));

        tickAndSend(runtime, broadcaster, 1800);

        assertThat(runtime.player().snapshot().t()).isEqualTo(9);
        List<Alert> unacked = store.unacked("zone-test");
        assertThat(unacked).hasSize(100);
        assertThat(unacked.get(0).alertId()).isEqualTo("a-20261118-0081");
        assertThat(unacked.get(99).alertId()).isEqualTo("a-20261118-0180");
    }
}
