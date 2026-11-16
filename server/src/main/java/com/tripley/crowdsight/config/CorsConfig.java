package com.tripley.crowdsight.config;

import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.CorsRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

import lombok.RequiredArgsConstructor;

/** REST /api/** 허용 출처 (api-spec 2절, 결정 기록 2). WebSocket(WebSocketConfig)과 같은 패턴을 쓴다. */
@Configuration(proxyBeanMethods = false)
@RequiredArgsConstructor
public class CorsConfig implements WebMvcConfigurer {

    private final CrowdsightProperties props;

    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/api/**")
                .allowedOriginPatterns(props.corsOriginPatterns().toArray(String[]::new))
                .allowedMethods("GET", "POST");
    }
}
