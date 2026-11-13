package com.tripley.crowdsight.ws;

import static org.assertj.core.api.Assertions.assertThat;
import static org.awaitility.Awaitility.await;
import static org.mockito.Mockito.atLeast;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;

import java.time.Duration;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.scheduling.concurrent.ThreadPoolTaskScheduler;

import com.tripley.crowdsight.config.CrowdsightProperties;
import com.tripley.crowdsight.config.TestProperties;

class WsPingSchedulerTest {

    private ThreadPoolTaskScheduler scheduler;
    private WsPingScheduler ping;

    @BeforeEach
    void setUp() {
        scheduler = new ThreadPoolTaskScheduler();
        scheduler.setPoolSize(1);
        scheduler.setThreadNamePrefix("ping-test-");
        scheduler.initialize();
    }

    @AfterEach
    void tearDown() {
        if (ping != null) {
            ping.stop();
        }
        scheduler.shutdown();
    }

    @Test
    @DisplayName("간격마다 pingAll을 부르고 stop하면 멈춘다")
    void pingsOnIntervalUntilStop() {
        ZoneSessions sessions = mock(ZoneSessions.class);
        ping = new WsPingScheduler(sessions, scheduler,
                TestProperties.ws(new CrowdsightProperties.Ws(20, 2000, 524288)));

        ping.start();

        await().atMost(Duration.ofSeconds(2)).untilAsserted(() -> verify(sessions, atLeast(3)).pingAll());
        assertThat(ping.isRunning()).isTrue();
        ping.stop();
        assertThat(ping.isRunning()).isFalse();
    }
}
