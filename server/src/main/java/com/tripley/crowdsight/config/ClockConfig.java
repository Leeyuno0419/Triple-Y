package com.tripley.crowdsight.config;

import java.time.Clock;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/** 서버 시계. 시각이 필요한 곳은 이 Clock을 주입받는다 (Instant.now() 금지, CLAUDE.md). */
@Configuration(proxyBeanMethods = false)
public class ClockConfig {

    /** crowdsight.time-zone 시간대의 시스템 시계. 테스트는 Clock.fixed를 직접 만든다. */
    @Bean
    public Clock clock(CrowdsightProperties props) {
        return Clock.system(props.clockZone());
    }
}
