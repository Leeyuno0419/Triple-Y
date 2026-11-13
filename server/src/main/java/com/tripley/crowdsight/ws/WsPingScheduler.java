package com.tripley.crowdsight.ws;

import java.time.Duration;
import java.util.concurrent.ScheduledFuture;

import org.springframework.context.SmartLifecycle;
import org.springframework.scheduling.concurrent.ThreadPoolTaskScheduler;
import org.springframework.stereotype.Component;

import com.tripley.crowdsight.config.CrowdsightProperties;

import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;

/**
 * ping-interval-ms마다 모든 화면에 ping을 보낸다 (api-spec 3.5).
 * 재생과 같은 replayTaskScheduler(스레드 2개)의 두 번째 주기 작업이다.
 * SmartLifecycle 기본 phase라 웹 서버가 뜬 뒤 시작하고 닫을 때 먼저 멈춘다.
 */
@Slf4j
@Component
@RequiredArgsConstructor
public class WsPingScheduler implements SmartLifecycle {

    private final ZoneSessions sessions;
    private final ThreadPoolTaskScheduler replayTaskScheduler;
    private final CrowdsightProperties props;
    private volatile ScheduledFuture<?> future;

    @Override
    public void start() {
        if (future != null) {
            return;
        }
        Duration interval = Duration.ofMillis(props.ws().pingIntervalMs());
        future = replayTaskScheduler.scheduleAtFixedRate(sessions::pingAll, interval);
        log.info("ping 시작: 간격 {} ms", interval.toMillis());
    }

    @Override
    public void stop() {
        ScheduledFuture<?> running = future;
        if (running != null) {
            running.cancel(false);
            future = null;
        }
    }

    @Override
    public boolean isRunning() {
        return future != null;
    }
}
