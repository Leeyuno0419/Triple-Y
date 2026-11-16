package com.tripley.crowdsight.ws;

import java.net.URI;
import java.util.Optional;

import org.springframework.stereotype.Component;
import org.springframework.web.socket.CloseStatus;
import org.springframework.web.socket.TextMessage;
import org.springframework.web.socket.WebSocketSession;
import org.springframework.web.socket.handler.TextWebSocketHandler;
import org.springframework.web.util.UriTemplate;

import com.tripley.crowdsight.alert.AlertStore;
import com.tripley.crowdsight.replay.ZoneRegistry;
import com.tripley.crowdsight.replay.ZoneRuntime;

import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import tools.jackson.databind.json.JsonMapper;

/**
 * /ws/zones/{zone_id} 접속 처리 (api-spec 3절). 접속하면 hello를 보낸 뒤 방송 대상에 넣는다.
 * hello에는 그 구역 미확인 알림을 담는다 (api-spec 3.1).
 * 없는 구역이면 닫기 코드 4404로 닫는다. 화면 → 서버 텍스트 메시지는 무시한다 (요청은 REST).
 * 스레드 규칙: Tomcat 스레드에서 불린다. 상태는 ZoneSessions에만 있다.
 */
@Slf4j
@Component
@RequiredArgsConstructor
public class ZoneWebSocketHandler extends TextWebSocketHandler {

    /** 없는 구역 (api-spec 3.1). 4000~4999는 응용이 정해 쓰는 닫기 코드다. */
    public static final CloseStatus UNKNOWN_ZONE = new CloseStatus(4404, "unknown zone");

    private static final UriTemplate PATH = new UriTemplate("/ws/zones/{zoneId}");

    private final ZoneRegistry zones;
    private final ZoneSessions sessions;
    private final MessageFactory messages;
    private final JsonMapper jsonMapper;
    private final AlertStore alerts;

    @Override
    public void afterConnectionEstablished(WebSocketSession session) throws Exception {
        Optional<ZoneRuntime> zone = zoneIdOf(session.getUri()).flatMap(zones::find);
        if (zone.isEmpty()) {
            log.info("없는 구역 접속을 닫음 uri={} session={}", session.getUri(), session.getId());
            session.close(UNKNOWN_ZONE);
            return;
        }
        ZoneRuntime runtime = zone.get();
        String hello = jsonMapper.writeValueAsString(messages.hello(runtime, alerts.unacked(runtime.zoneId())));
        sessions.join(runtime.zoneId(), session, hello);
    }

    @Override
    protected void handleTextMessage(WebSocketSession session, TextMessage message) {
        // 화면 → 서버 메시지는 쓰지 않는다 (api-spec 1절: 요청은 REST). 연결은 유지한다.
    }

    @Override
    public void handleTransportError(WebSocketSession session, Throwable exception) {
        log.debug("WS 전송 오류 session={} 원인={}", session.getId(), exception.toString());
        sessions.leave(session);
    }

    @Override
    public void afterConnectionClosed(WebSocketSession session, CloseStatus status) {
        sessions.leave(session);
    }

    /** 경로에서 구역 ID를 꺼낸다. 형식이 다르거나 비어 있으면 빈 값. */
    static Optional<String> zoneIdOf(URI uri) {
        if (uri == null || !PATH.matches(uri.getPath())) {
            return Optional.empty();
        }
        return Optional.ofNullable(PATH.match(uri.getPath()).get("zoneId")).filter(id -> !id.isEmpty());
    }
}
