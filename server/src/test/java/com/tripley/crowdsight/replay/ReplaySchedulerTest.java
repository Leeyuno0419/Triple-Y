package com.tripley.crowdsight.replay;

import static com.tripley.crowdsight.timeline.TimelineFixtures.timelineOf;
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatCode;
import static org.awaitility.Awaitility.await;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.scheduling.concurrent.ThreadPoolTaskScheduler;

import com.tripley.crowdsight.config.TestProperties;

class ReplaySchedulerTest {

    private ThreadPoolTaskScheduler scheduler;
    private ReplayScheduler replay;

    /** 셀 없는 판정기로 감싼다. mock 플레이어에는 timeline이 없고 timelineOf의 셀도 비어 있다. */
    private static ZoneRuntime runtime(ZonePlayer player) {
        return new ZoneRuntime(player, TestProperties.grader(List.of()));
    }

    @BeforeEach
    void setUp() {
        scheduler = new ThreadPoolTaskScheduler();
        scheduler.setPoolSize(1);
        scheduler.setThreadNamePrefix("replay-test-");
        scheduler.initialize();
    }

    @AfterEach
    void tearDown() {
        if (replay != null) {
            replay.stop();
        }
        scheduler.shutdown();
    }

    @Test
    @DisplayName("구역 하나가 예외를 던져도 다른 구역은 진행한다")
    void survivesZoneException() {
        ZonePlayer a = mock(ZonePlayer.class);
        when(a.tick()).thenThrow(new IllegalStateException("시험"));
        when(a.zoneId()).thenReturn("zone-a");
        ZoneRuntime b = runtime(new ZonePlayer(timelineOf(5), true));
        ZoneRegistry registry = mock(ZoneRegistry.class);
        when(registry.all()).thenReturn(List.of(runtime(a), b));
        replay = new ReplayScheduler(registry, scheduler, TestProperties.replay(1000, true),
                mock(ZoneBroadcaster.class));

        assertThatCode(() -> {
            replay.tickAll();
            replay.tickAll();
        }).doesNotThrowAnyException();

        assertThat(b.player().snapshot().t()).isEqualTo(1);
        verify(a, times(2)).tick();
    }

    @Test
    @DisplayName("설정 간격마다 tick을 반복하고 stop하면 멈춘다")
    void ticksOnSchedule() {
        AtomicInteger count = new AtomicInteger();
        ZonePlayer player = mock(ZonePlayer.class);
        when(player.tick()).thenAnswer(invocation -> {
            count.incrementAndGet();
            return Optional.empty();
        });
        when(player.pollStateChange()).thenReturn(Optional.empty());
        ZoneRegistry registry = mock(ZoneRegistry.class);
        when(registry.all()).thenReturn(List.of(runtime(player)));
        replay = new ReplayScheduler(registry, scheduler, TestProperties.replay(20, true),
                mock(ZoneBroadcaster.class));

        replay.start();

        await().atMost(Duration.ofSeconds(2)).until(() -> count.get() >= 5);
        assertThat(replay.isRunning()).isTrue();
        replay.stop();
        assertThat(replay.isRunning()).isFalse();
        int n = count.get();
        await().pollDelay(Duration.ofMillis(200)).atMost(Duration.ofSeconds(1))
                .untilAsserted(() -> assertThat(count.get()).isLessThanOrEqualTo(n + 1));
    }

    /** 방송 순서를 문자열로 쌓는다. */
    private static final class RecordingBroadcaster implements ZoneBroadcaster {
        final List<String> events = new ArrayList<>();

        @Override
        public void playback(String zoneId, PlaybackSnapshot snapshot) {
            events.add("playback " + snapshot.state() + " " + snapshot.t());
        }

        @Override
        public void zoneState(String zoneId, ZoneStep step) {
            events.add("zone_state " + step.evaluation().t());
        }
    }

    private static ZoneRegistry registryOf(ZoneRuntime... runtimes) {
        ZoneRegistry registry = mock(ZoneRegistry.class);
        when(registry.all()).thenReturn(List.of(runtimes));
        return registry;
    }

    @Test
    @DisplayName("반복으로 처음에 돌아오면 playback을 zone_state보다 먼저 보낸다")
    void wrapSendsPlaybackBeforeZoneState() {
        RecordingBroadcaster broadcaster = new RecordingBroadcaster();
        replay = new ReplayScheduler(registryOf(runtime(new ZonePlayer(timelineOf(3), true))), scheduler,
                TestProperties.replay(1000, true), broadcaster);

        for (int i = 0; i < 4; i++) {
            replay.tickAll();
        }

        assertThat(broadcaster.events).containsExactly("zone_state 0", "zone_state 1", "zone_state 2",
                "playback PLAYING 0", "zone_state 0");
    }

    @Test
    @DisplayName("끝나면 playback(ended)을 한 번만 보낸다")
    void endSendsPlaybackOnce() {
        RecordingBroadcaster broadcaster = new RecordingBroadcaster();
        replay = new ReplayScheduler(registryOf(runtime(new ZonePlayer(timelineOf(2), false))), scheduler,
                TestProperties.replay(1000, false), broadcaster);

        for (int i = 0; i < 4; i++) {
            replay.tickAll();
        }

        assertThat(broadcaster.events).containsExactly("zone_state 0", "zone_state 1", "playback ENDED 1");
    }

    @Test
    @DisplayName("한 구역 방송이 실패해도 같은 tick의 다른 구역은 보낸다")
    void broadcastFailureDoesNotStopOtherZones() {
        ZoneBroadcaster broadcaster = mock(ZoneBroadcaster.class);
        doThrow(new IllegalStateException("시험")).doNothing().when(broadcaster).zoneState(any(), any());
        replay = new ReplayScheduler(registryOf(runtime(new ZonePlayer(timelineOf(5), true)),
                runtime(new ZonePlayer(timelineOf(5), true))), scheduler, TestProperties.replay(1000, true),
                broadcaster);

        assertThatCode(() -> {
            replay.tickAll();
            replay.tickAll();
        }).doesNotThrowAnyException();

        verify(broadcaster, times(4)).zoneState(eq("zone-test"), any());
    }
}
