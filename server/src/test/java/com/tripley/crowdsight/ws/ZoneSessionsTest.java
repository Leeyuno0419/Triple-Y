package com.tripley.crowdsight.ws;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatCode;
import static org.awaitility.Awaitility.await;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.doAnswer;
import static org.mockito.Mockito.doNothing;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.mockingDetails;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import java.io.IOException;
import java.time.Duration;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

import org.apache.tomcat.websocket.Constants;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.web.socket.CloseStatus;
import org.springframework.web.socket.TextMessage;
import org.springframework.web.socket.WebSocketSession;
import org.springframework.web.socket.adapter.NativeWebSocketSession;
import org.springframework.web.socket.handler.ConcurrentWebSocketSessionDecorator;

import com.tripley.crowdsight.config.CrowdsightProperties;
import com.tripley.crowdsight.config.TestProperties;

import jakarta.websocket.Session;

class ZoneSessionsTest {

    private final ZoneSessions sessions = new ZoneSessions(TestProperties.ws(TestProperties.WS));

    /** id를 주고 열려 있는 mock 세션. */
    private static WebSocketSession session(String id) {
        WebSocketSession session = mock(WebSocketSession.class);
        when(session.getId()).thenReturn(id);
        when(session.isOpen()).thenReturn(true);
        return session;
    }

    /** mock 세션에 보낸 메시지. 텍스트는 payload, 나머지(ping)는 "PING". */
    private static List<String> sent(WebSocketSession session) {
        return mockingDetails(session).getInvocations().stream()
                .filter(invocation -> invocation.getMethod().getName().equals("sendMessage"))
                .map(invocation -> invocation.getArgument(0) instanceof TextMessage text ? text.getPayload() : "PING")
                .toList();
    }

    @Test
    @DisplayName("Tomcat 차단 전송 제한을 Long 2000으로 건다")
    void setsTomcatBlockingSendTimeout() {
        NativeWebSocketSession raw = mock(NativeWebSocketSession.class);
        when(raw.getId()).thenReturn("a");
        when(raw.isOpen()).thenReturn(true);
        Session tomcat = mock(Session.class);
        Map<String, Object> userProperties = new HashMap<>();
        when(tomcat.getUserProperties()).thenReturn(userProperties);
        when(raw.getNativeSession(Session.class)).thenReturn(tomcat);

        sessions.join("zone-test", raw, "hello");

        assertThat(userProperties.get(Constants.BLOCKING_SEND_TIMEOUT_PROPERTY)).isInstanceOf(Long.class)
                .isEqualTo(2000L);
    }

    @Test
    @DisplayName("hello를 먼저 보내고 방송을 받는다")
    void sendsHelloBeforeBroadcast() {
        WebSocketSession a = session("a");

        sessions.join("zone-test", a, "hello");
        sessions.broadcast("zone-test", "s1");

        assertThat(sent(a)).containsExactly("hello", "s1");
    }

    @Test
    @DisplayName("다른 구역 방송은 받지 않는다")
    void broadcastsOnlyToSameZone() {
        WebSocketSession a = session("a");
        WebSocketSession b = session("b");
        sessions.join("zone-test", a, "hello");
        sessions.join("zone-b", b, "hello");

        sessions.broadcast("zone-test", "s1");

        assertThat(sent(a)).last().isEqualTo("s1");
        assertThat(sent(b)).containsExactly("hello");
    }

    @Test
    @DisplayName("보내기에서 IOException이 나면 그 세션만 닫고 뺀다")
    void dropsFailingSessionOnIoException() throws IOException {
        assertDropsSecondSendFailure(new IOException("끊김"));
    }

    @Test
    @DisplayName("보내기에서 RuntimeException이 나도 그 세션만 뺀다")
    void dropsFailingSessionOnRuntimeException() throws IOException {
        assertDropsSecondSendFailure(new IllegalStateException("닫힌 세션"));
    }

    private void assertDropsSecondSendFailure(Exception failure) throws IOException {
        WebSocketSession a = session("a");
        WebSocketSession b = session("b");
        doNothing().doThrow(failure).when(b).sendMessage(any());
        sessions.join("zone-test", a, "hello");
        sessions.join("zone-test", b, "hello");

        sessions.broadcast("zone-test", "s1");
        sessions.broadcast("zone-test", "s2");

        verify(b, times(1)).close(CloseStatus.SESSION_NOT_RELIABLE);
        assertThat(sent(a)).containsExactly("hello", "s1", "s2");
        assertThat(sent(b)).containsExactly("hello", "s1");
        assertThat(sessions.sessionCount()).isEqualTo(1);
    }

    @Test
    @DisplayName("재생이 막힌 세션은 ping이 한도를 검사해 닫는다")
    void dropsWhenPingFindsStuckSend() throws Exception {
        ZoneSessions limited = new ZoneSessions(TestProperties.ws(new CrowdsightProperties.Ws(30000, 50, 524288)));
        WebSocketSession a = session("a");
        CountDownLatch release = new CountDownLatch(1);
        AtomicInteger calls = new AtomicInteger();
        doAnswer(invocation -> {
            if (calls.incrementAndGet() == 2) {         // 첫 방송에서 멈춘다 (hello는 바로 보냄)
                release.await(5, TimeUnit.SECONDS);
            }
            return null;
        }).when(a).sendMessage(any());
        limited.join("zone-test", a, "hello");
        ConcurrentWebSocketSessionDecorator decorated =
                (ConcurrentWebSocketSessionDecorator) limited.sessions("zone-test").get(0);
        ExecutorService replayThread = Executors.newSingleThreadExecutor();
        try {
            Future<?> stuck = replayThread.submit(() -> limited.broadcast("zone-test", "zs"));
            await().atMost(Duration.ofSeconds(2)).until(() -> decorated.getTimeSinceSendStarted() > 50);

            limited.pingAll();
            release.countDown();

            assertThatCode(() -> stuck.get(2, TimeUnit.SECONDS)).doesNotThrowAnyException();
            verify(a, times(1)).close(CloseStatus.SESSION_NOT_RELIABLE);
            assertThat(limited.sessionCount()).isZero();
        } finally {
            release.countDown();
            replayThread.shutdownNow();
        }
    }

    @Test
    @DisplayName("hello를 못 보내면 닫고 넣지 않는다")
    void helloFailureNotJoined() throws IOException {
        WebSocketSession a = session("a");
        doThrow(new IOException("끊김")).when(a).sendMessage(any());

        sessions.join("zone-test", a, "hello");

        verify(a).close(CloseStatus.SESSION_NOT_RELIABLE);
        assertThat(sessions.sessionCount()).isZero();
    }

    @Test
    @DisplayName("hello 중에 끊긴 세션은 남기지 않는다")
    void removesSessionClosedDuringHello() {
        WebSocketSession a = session("a");
        when(a.isOpen()).thenReturn(false);

        sessions.join("zone-test", a, "hello");

        assertThat(sessions.sessionCount()).isZero();
    }

    @Test
    @DisplayName("leave하면 방송 대상에서 빠진다")
    void leaveRemoves() {
        WebSocketSession a = session("a");
        sessions.join("zone-test", a, "hello");

        sessions.leave(a);
        sessions.broadcast("zone-test", "s1");

        assertThat(sent(a)).containsExactly("hello");
        assertThat(sessions.sessionCount()).isZero();
        assertThatCode(() -> sessions.leave(a)).doesNotThrowAnyException();
    }

    @Test
    @DisplayName("pingAll은 모든 구역 세션에 ping을 보낸다")
    void pingAllSendsPing() {
        WebSocketSession a = session("a");
        WebSocketSession b = session("b");
        sessions.join("zone-test", a, "hello");
        sessions.join("zone-b", b, "hello");

        sessions.pingAll();

        assertThat(sent(a)).last().isEqualTo("PING");
        assertThat(sent(b)).last().isEqualTo("PING");
    }
}
