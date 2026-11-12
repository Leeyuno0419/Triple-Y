package com.tripley.crowdsight.replay;

import static com.tripley.crowdsight.timeline.TimelineFixtures.timelineOf;
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatCode;
import static org.awaitility.Awaitility.await;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import java.time.Duration;
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
        ZonePlayer b = new ZonePlayer(timelineOf(5), true);
        ZoneRegistry registry = mock(ZoneRegistry.class);
        when(registry.all()).thenReturn(List.of(a, b));
        replay = new ReplayScheduler(registry, scheduler, TestProperties.replay(1000, true));

        assertThatCode(() -> {
            replay.tickAll();
            replay.tickAll();
        }).doesNotThrowAnyException();

        assertThat(b.snapshot().t()).isEqualTo(1);
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
        when(registry.all()).thenReturn(List.of(player));
        replay = new ReplayScheduler(registry, scheduler, TestProperties.replay(20, true));

        replay.start();

        await().atMost(Duration.ofSeconds(2)).until(() -> count.get() >= 5);
        assertThat(replay.isRunning()).isTrue();
        replay.stop();
        assertThat(replay.isRunning()).isFalse();
        int n = count.get();
        await().pollDelay(Duration.ofMillis(200)).atMost(Duration.ofSeconds(1))
                .untilAsserted(() -> assertThat(count.get()).isLessThanOrEqualTo(n + 1));
    }
}
