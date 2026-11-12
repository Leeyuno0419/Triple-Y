package com.tripley.crowdsight.replay;

import java.time.Duration;
import java.util.Optional;
import java.util.concurrent.ScheduledFuture;

import org.springframework.context.SmartLifecycle;
import org.springframework.scheduling.concurrent.ThreadPoolTaskScheduler;
import org.springframework.stereotype.Component;

import com.tripley.crowdsight.config.CrowdsightProperties;

import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;

/**
 * 모든 구역을 interval-ms마다 한 칸씩 재생한다.
 * 스레드 규칙: tickAll은 replayTaskScheduler의 스레드 하나에서만 돈다 (주기 작업은 자기와 겹치지 않음).
 * 구역 하나가 예외를 던져도 로그만 남기고 다른 구역과 다음 tick은 계속한다.
 * SmartLifecycle 기본 phase(MAX)라 다른 빈(웹 서버 포함)이 다 뜬 뒤 시작하고, 닫을 때 가장 먼저 멈춘다.
 * S2는 판정 결과(구역 등급)를 DEBUG 로그로만 남긴다. S3에서 방송(ZoneBroadcaster)을 붙인다.
 */
@Slf4j
@Component
@RequiredArgsConstructor
public class ReplayScheduler implements SmartLifecycle {

    private final ZoneRegistry zones;
    private final ThreadPoolTaskScheduler replayTaskScheduler;
    private final CrowdsightProperties props;
    private volatile ScheduledFuture<?> future;

    @Override
    public void start() {
        if (future != null) {
            return;
        }
        Duration interval = Duration.ofMillis(props.replay().intervalMs());
        future = replayTaskScheduler.scheduleAtFixedRate(this::tickAll, interval);
        log.info("재생 시작: 구역 {}개, 간격 {} ms", zones.all().size(), interval.toMillis());
    }

    @Override
    public void stop() {
        ScheduledFuture<?> running = future;
        if (running != null) {
            running.cancel(false);
            future = null;
            log.info("재생 멈춤");
        }
    }

    @Override
    public boolean isRunning() {
        return future != null;
    }

    /** 모든 구역을 한 칸씩 진행하고 판정한다. 재생 스레드에서만 부른다 (테스트는 직접 부른다). */
    void tickAll() {
        for (ZoneRuntime zone : zones.all()) {
            try {
                Optional<ZoneStep> step = zone.tick();
                zone.player().pollStateChange().ifPresent(s -> log.info("재생 상태 zone={} state={} t={} loop={}",
                        zone.zoneId(), s.state(), s.t(), s.loop()));
                step.ifPresent(s -> log.debug("재생 zone={} t={} discontinuity={} wrapped={} grade={} max_density={}",
                        zone.zoneId(), s.tick().frame().t(), s.tick().discontinuity(), s.tick().wrapped(),
                        s.evaluation().zoneGrade(), s.evaluation().maxDensity()));
                // S3: [playback?] → zone_state 방송
            } catch (RuntimeException e) {
                log.error("구역 재생 중 오류, 다음 구역으로 계속 zone={}", zone.zoneId(), e);
            }
        }
    }
}
