package com.tripley.crowdsight.ws;

import java.io.IOException;
import java.util.List;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;

import org.springframework.stereotype.Component;
import org.springframework.web.socket.CloseStatus;
import org.springframework.web.socket.PingMessage;
import org.springframework.web.socket.TextMessage;
import org.springframework.web.socket.WebSocketMessage;
import org.springframework.web.socket.WebSocketSession;
import org.springframework.web.socket.adapter.NativeWebSocketSession;
import org.springframework.web.socket.handler.ConcurrentWebSocketSessionDecorator;

import com.tripley.crowdsight.config.CrowdsightProperties;

import jakarta.websocket.Session;
import lombok.extern.slf4j.Slf4j;

/**
 * 구역별 접속 화면. 세션은 ConcurrentWebSocketSessionDecorator로 감싸 두 스레드(재생·ping)가 보내도 안전하게 한다.
 * 느린 화면(결정 기록 1): 세션마다 Tomcat 차단 전송 제한을 걸고, 보내기가 실패하면 그 세션만 닫고 뺀다.
 * 스레드 규칙: join·leave는 Tomcat 스레드, broadcast는 재생 스레드, pingAll은 ping 스레드가 부른다.
 * 맵은 Concurrent 컬렉션이라 잠금이 없다.
 */
@Slf4j
@Component
public final class ZoneSessions {

    /** Tomcat이 보낼 때마다 읽는 세션 사용자 속성. 값이 Long이 아니면 무시하고 기본 20초를 쓴다 (jar 확인). */
    static final String BLOCKING_SEND_TIMEOUT = "org.apache.tomcat.websocket.BLOCKING_SEND_TIMEOUT";

    private final CrowdsightProperties.Ws ws;
    private final ConcurrentMap<String, Set<WebSocketSession>> byZone = new ConcurrentHashMap<>();
    private final ConcurrentMap<String, Member> bySessionId = new ConcurrentHashMap<>();

    public ZoneSessions(CrowdsightProperties props) {
        this.ws = props.ws();
    }

    /** 감싼 세션과 구역. 키는 원래 세션 ID. */
    private record Member(String zoneId, WebSocketSession session) {
    }

    /**
     * 차단 전송 제한을 걸고, 감싸고, hello를 보낸 뒤 방송 대상에 넣는다.
     * hello 전송이 실패하면 닫고 넣지 않는다. 그 사이 끊겼으면 다시 뺀다.
     */
    public void join(String zoneId, WebSocketSession raw, String helloJson) {
        setBlockingSendTimeout(raw);
        WebSocketSession session = new ConcurrentWebSocketSessionDecorator(raw, ws.sendTimeLimitMs(),
                ws.bufferSizeLimitBytes());
        try {
            session.sendMessage(new TextMessage(helloJson));
        } catch (IOException | RuntimeException e) {
            log.warn("hello 전송 실패, 세션을 닫음 zone={} session={} 원인={}", zoneId, raw.getId(), e.toString());
            closeQuietly(session);
            return;
        }
        Member member = new Member(zoneId, session);
        bySessionId.put(raw.getId(), member);
        Set<WebSocketSession> targets = byZone.computeIfAbsent(zoneId, k -> ConcurrentHashMap.newKeySet());
        targets.add(session);
        if (!raw.isOpen()) {     // 그 사이 끊김. leave가 bySessionId만 먼저 지웠을 수 있어 두 맵에서 직접 뺀다
            targets.remove(session);
            if (bySessionId.remove(raw.getId(), member)) {     // Member를 뺀 쪽만 로그 (leave가 뺐으면 leave가 남겼다)
                log.info("화면 접속 끊김 zone={} session={} 접속자={}", zoneId, raw.getId(), sessionCount(zoneId));
            }
            return;
        }
        log.info("화면 접속 zone={} session={} 접속자={}", zoneId, raw.getId(), sessionCount(zoneId));
    }

    /** 방송 대상에서 뺀다. 없으면 아무것도 하지 않는다 (닫힘·전송 오류에서 여러 번 불려도 된다). */
    public void leave(WebSocketSession raw) {
        Member member = bySessionId.remove(raw.getId());
        if (member == null) {
            return;
        }
        Set<WebSocketSession> targets = byZone.get(member.zoneId());
        if (targets != null) {
            targets.remove(member.session());
        }
        log.info("화면 접속 끊김 zone={} session={} 접속자={}", member.zoneId(), raw.getId(),
                sessionCount(member.zoneId()));
    }

    /** 이미 만든 JSON 하나를 그 구역 화면 모두에 보낸다. 실패한 세션만 닫고 빼고 나머지는 계속한다. */
    public void broadcast(String zoneId, String json) {
        Set<WebSocketSession> targets = byZone.get(zoneId);
        if (targets == null || targets.isEmpty()) {
            return;
        }
        TextMessage message = new TextMessage(json);
        for (WebSocketSession session : targets) {
            send(zoneId, session, message);
        }
    }

    /** 모든 화면에 ping을 보낸다 (브라우저가 pong으로 자동 응답). */
    public void pingAll() {
        byZone.forEach((zoneId, targets) -> {
            for (WebSocketSession session : targets) {
                send(zoneId, session, new PingMessage());     // ByteBuffer를 세션끼리 나눠 쓰지 않는다
            }
        });
    }

    /** 모든 구역 접속 수. */
    public int sessionCount() {
        return byZone.values().stream().mapToInt(Set::size).sum();
    }

    /** 구역 접속 수. */
    public int sessionCount(String zoneId) {
        Set<WebSocketSession> targets = byZone.get(zoneId);
        return targets == null ? 0 : targets.size();
    }

    /** 테스트용: 구역의 감싼 세션 목록. */
    List<WebSocketSession> sessions(String zoneId) {
        return List.copyOf(byZone.getOrDefault(zoneId, Set.of()));
    }

    private void send(String zoneId, WebSocketSession session, WebSocketMessage<?> message) {
        try {
            session.sendMessage(message);
        } catch (IOException | RuntimeException e) {     // 차단 제한 초과·끊김(IOException), 한도 초과·닫힌 세션(Runtime)
            drop(zoneId, session, e);
        }
    }

    /** 실패한 세션을 빼고 닫는다. 두 스레드(재생·ping)가 같이 불러도 뺀 스레드 하나만 로그를 남기고 닫는다. */
    private void drop(String zoneId, WebSocketSession session, Exception cause) {
        Set<WebSocketSession> targets = byZone.get(zoneId);
        if (targets == null || !targets.remove(session)) {
            return;     // 다른 스레드의 drop이나 leave가 이미 뺐다
        }
        bySessionId.remove(session.getId());
        log.warn("보내기 실패한 화면을 닫고 뺌 zone={} session={} 원인={}", zoneId, session.getId(), cause.toString());
        closeQuietly(session);
    }

    private void setBlockingSendTimeout(WebSocketSession raw) {
        if (raw instanceof NativeWebSocketSession nativeSession) {
            Session tomcat = nativeSession.getNativeSession(Session.class);
            if (tomcat != null) {
                tomcat.getUserProperties().put(BLOCKING_SEND_TIMEOUT, Long.valueOf(ws.sendTimeLimitMs()));
                return;
            }
        }
        log.warn("Tomcat 세션이 아니라 차단 전송 제한을 걸지 못함 session={} 종류={}", raw.getId(),
                raw.getClass().getName());
    }

    private static void closeQuietly(WebSocketSession session) {
        try {
            session.close(CloseStatus.SESSION_NOT_RELIABLE);
        } catch (IOException | RuntimeException e) {
            log.debug("세션 닫기 실패 무시 session={} 원인={}", session.getId(), e.toString());
        }
    }
}
