package com.tripley.crowdsight.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskScheduler;

/** 재생 스케줄러 빈. 시작(initialize)과 종료(shutdown)는 Spring이 맡는다. */
@Configuration(proxyBeanMethods = false)
public class ReplaySchedulerConfig {

    /**
     * 재생 전용 스레드 1개. 주기 작업은 자기와 겹치지 않으므로 판정 상태는 이 스레드만 만진다.
     * S3에서 ping 작업을 더하면 poolSize를 2로 올린다.
     */
    @Bean
    public ThreadPoolTaskScheduler replayTaskScheduler() {
        ThreadPoolTaskScheduler scheduler = new ThreadPoolTaskScheduler();
        scheduler.setPoolSize(1);
        scheduler.setThreadNamePrefix("replay-");
        scheduler.setRemoveOnCancelPolicy(true);
        return scheduler;
    }
}
