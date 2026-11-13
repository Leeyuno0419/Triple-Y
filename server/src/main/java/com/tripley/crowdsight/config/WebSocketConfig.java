package com.tripley.crowdsight.config;

import org.springframework.context.annotation.Configuration;
import org.springframework.web.socket.config.annotation.EnableWebSocket;
import org.springframework.web.socket.config.annotation.WebSocketConfigurer;
import org.springframework.web.socket.config.annotation.WebSocketHandlerRegistry;

import com.tripley.crowdsight.ws.ZoneWebSocketHandler;

import lombok.RequiredArgsConstructor;

/** WebSocket 경로와 허용 출처 (api-spec 2절, 결정 기록 2). */
@Configuration(proxyBeanMethods = false)
@EnableWebSocket
@RequiredArgsConstructor
public class WebSocketConfig implements WebSocketConfigurer {

    private final ZoneWebSocketHandler zoneHandler;
    private final CrowdsightProperties props;

    @Override
    public void registerWebSocketHandlers(WebSocketHandlerRegistry registry) {
        registry.addHandler(zoneHandler, "/ws/zones/*")
                .setAllowedOriginPatterns(props.corsOriginPatterns().toArray(String[]::new));
    }
}
