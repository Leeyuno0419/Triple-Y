package com.tripley.crowdsight.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskScheduler;

/** 재생 스케줄러 빈. 시작(initialize)과 종료(shutdown)는 Spring이 맡는다. */
@Configuration(proxyBeanMethods = false)
public class ReplaySchedulerConfig {

    /**
     * 재생·ping 스레드 2개. 재생 tickAll과 ping은 각각 scheduleAtFixedRate 작업 하나다.
     * 같은 주기 작업은 자기와 겹치지 않으므로 판정 상태는 여전히 한 번에 한 스레드만 만진다.
     * 실행마다 스레드가 바뀔 수 있으나 실행기 큐가 앞뒤 실행 사이의 happens-before를 보장한다.
     * ping이 따로 돌아야 느린 세션에 막힌 재생과 겹칠 때 데코레이터 한도 검사가 일어난다.
     */
    @Bean
    public ThreadPoolTaskScheduler replayTaskScheduler() {
        ThreadPoolTaskScheduler scheduler = new ThreadPoolTaskScheduler();
        scheduler.setPoolSize(2);
        scheduler.setThreadNamePrefix("replay-");
        scheduler.setRemoveOnCancelPolicy(true);
        return scheduler;
    }
}
