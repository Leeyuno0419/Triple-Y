package com.tripley.crowdsight.ws;

import static com.tripley.crowdsight.timeline.TimelineFixtures.MAPPER;
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.awaitility.Awaitility.await;

import java.io.IOException;
import java.net.URI;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.TimeUnit;
import java.util.regex.Pattern;

import org.apache.tomcat.websocket.Constants;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.web.socket.CloseStatus;
import org.springframework.web.socket.TextMessage;
import org.springframework.web.socket.WebSocketHttpHeaders;
import org.springframework.web.socket.WebSocketSession;
import org.springframework.web.socket.adapter.NativeWebSocketSession;
import org.springframework.web.socket.client.standard.StandardWebSocketClient;
import org.springframework.web.socket.handler.TextWebSocketHandler;
import org.springframework.web.socket.handler.WebSocketSessionDecorator;

import jakarta.websocket.Session;
import tools.jackson.databind.JsonNode;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT, properties = {
        "crowdsight.timeline-dir=src/test/resources/timeline",
        "crowdsight.timeline-files=valid_v02.json",
        "crowdsight.replay.interval-ms=100"
})
class ZoneWebSocketIntegrationTest {

    private static final Duration WAIT = Duration.ofSeconds(3);
    private static final int MAX_SKIP = 50;
    private static final Pattern FRAME_TS =
            Pattern.compile("\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}\\.\\d{3}\\+09:00");

    @LocalServerPort
    private int port;

    @Autowired
    private ZoneSessions sessions;

    private final StandardWebSocketClient client = new StandardWebSocketClient();
    private final List<WebSocketSession> opened = new ArrayList<>();

    @AfterEach
    void closeClients() throws IOException {
        for (WebSocketSession s : opened) {
            if (s.isOpen()) {
                s.close();
            }
        }
        await().atMost(WAIT).until(() -> sessions.sessionCount() == 0);   // 다음 테스트가 0에서 시작
    }

    private Inbox connect(String zoneId) throws Exception {
        Inbox inbox = new Inbox();
        opened.add(client.execute(inbox, "ws://localhost:{port}/ws/zones/{zone}", port, zoneId)
                .get(5, TimeUnit.SECONDS));
        return inbox;
    }

    private CompletableFuture<WebSocketSession> connectWithOrigin(Inbox inbox, String origin) {
        WebSocketHttpHeaders headers = new WebSocketHttpHeaders();
        headers.setOrigin(origin);
        return client.execute(inbox, headers, URI.create("ws://localhost:" + port + "/ws/zones/zone-test"));
    }

    /** 클라이언트가 받은 메시지와 닫힘 상태. Tomcat 클라이언트 스레드가 채운다. */
    static final class Inbox extends TextWebSocketHandler {
        final BlockingQueue<JsonNode> messages = new LinkedBlockingQueue<>();
        final CompletableFuture<CloseStatus> closed = new CompletableFuture<>();

        @Override
        protected void handleTextMessage(WebSocketSession session, TextMessage message) {
            messages.add(MAPPER.readTree(message.getPayload()));
        }

        @Override
        public void afterConnectionClosed(WebSocketSession session, CloseStatus status) {
            closed.complete(status);
        }

        JsonNode next() throws InterruptedException {
            JsonNode node = messages.poll(WAIT.toMillis(), TimeUnit.MILLISECONDS);
            assertThat(node).as("메시지가 와야 한다").isNotNull();
            return node;
        }

        /** 다음 zone_state (최대 50개 넘김). */
        JsonNode nextZoneState() throws InterruptedException {
            for (int i = 0; i < MAX_SKIP; i++) {
                JsonNode node = next();
                if (node.get("type").asString().equals("zone_state")) {
                    return node;
                }
            }
            throw new AssertionError("zone_state가 오지 않았다");
        }

        /** t가 같은 zone_state까지 넘긴다 (최대 50개). */
        JsonNode zoneStateAt(int t) throws InterruptedException {
            for (int i = 0; i < MAX_SKIP; i++) {
                JsonNode node = nextZoneState();
                if (node.get("t").asInt() == t) {
                    return node;
                }
            }
            throw new AssertionError("t=" + t + " zone_state가 오지 않았다");
        }
    }

    @Test
    @DisplayName("접속하면 hello를 먼저 받는다")
    void helloFirst() throws Exception {
        JsonNode hello = connect("zone-test").next();

        assertThat(hello.get("type").asString()).isEqualTo("hello");
        assertThat(hello.get("schema_version").asString()).isEqualTo("0.2");
        assertThat(hello.get("zone_id").asString()).isEqualTo("zone-test");
        assertThat(hello.get("meta").get("video_id").asString()).isEqualTo("TEST_001");
        assertThat(hello.get("meta").get("cells").size()).isEqualTo(3);
        assertThat(hello.get("playback").get("state").asString()).isEqualTo("playing");
        assertThat(hello.get("playback").get("loop").asBoolean()).isTrue();
        assertThat(hello.get("playback").get("duration_s").asInt()).isEqualTo(5);
        assertThat(hello.get("thresholds").get("density").get("alert").asDouble()).isEqualTo(4.0);
        assertThat(hello.get("thresholds").get("pressure").asDouble()).isEqualTo(0.02);
        assertThat(hello.get("thresholds").get("inflow_ratio").asDouble()).isEqualTo(0.6);
        assertThat(hello.get("unacked_alerts").size()).isZero();
    }

    @Test
    @DisplayName("zone_state t가 1씩 늘고, 반복 때 playback(playing, 0)이 먼저 온다")
    void zoneStatesInOrderWithPlaybackOnWrap() throws Exception {
        Inbox inbox = connect("zone-test");
        inbox.next();                                        // hello
        List<JsonNode> received = new ArrayList<>();
        for (int i = 0; i < 15; i++) {
            received.add(inbox.next());
        }

        Integer previousT = null;
        int playbacks = 0;
        for (int i = 0; i < received.size(); i++) {
            JsonNode node = received.get(i);
            String type = node.get("type").asString();
            assertThat(type).isIn("zone_state", "playback");
            if (type.equals("playback")) {
                playbacks++;
                continue;
            }
            int t = node.get("t").asInt();
            if (previousT != null) {
                assertThat(t).isEqualTo((previousT + 1) % 5);
                if (t == 0) {
                    assertThat(received.get(i - 1)).isEqualTo(MAPPER.readTree(
                            "{\"type\":\"playback\",\"zone_id\":\"zone-test\",\"state\":\"playing\",\"t\":0,"
                                    + "\"loop\":true}"));
                }
            }
            previousT = t;
        }
        assertThat(playbacks).isPositive();
    }

    @Test
    @DisplayName("t4 zone_state 값·키·frame_ts 형식이 맞다")
    void zoneStateMatchesFixtureAtT4() throws Exception {
        JsonNode state = connect("zone-test").zoneStateAt(4);

        assertThat(state.propertyNames()).hasSize(6);
        assertThat(state.get("frame_ts").asString()).matches(FRAME_TS);
        JsonNode zone = state.get("zone");
        assertThat(zone.get("grade").asString()).isEqualTo("CAUTION");
        assertThat(zone.get("max_density").asDouble()).isEqualTo(4.2);
        assertThat(zone.get("inflow_ratio").asDouble()).isEqualTo(0.65);
        assertThat(zone.get("inflow_alert").asBoolean()).isFalse();
        assertThat(zone.has("count")).isTrue();
        assertThat(zone.get("count").isNull()).isTrue();
        JsonNode cells = state.get("cells");
        assertThat(cells.values().stream().map(c -> c.get("grade").asString()))
                .containsExactly("CAUTION", "NORMAL", "ALERT");
        assertThat(cells.values().stream().map(c -> c.get("grade_pred_60s").asString()))
                .containsExactly("ALERT", "NORMAL", "CRITICAL");
        for (JsonNode cell : cells.values()) {
            assertThat(cell.propertyNames()).hasSize(10);
        }
        assertThat(cells.get(1).get("counterflow").isNull()).isTrue();
    }

    @Test
    @DisplayName("없는 구역은 4404 unknown zone으로 닫는다")
    void unknownZoneClosedWith4404() throws Exception {
        Inbox inbox = connect("nope");

        CloseStatus status = inbox.closed.get(3, TimeUnit.SECONDS);

        assertThat(status.getCode()).isEqualTo(4404);
        assertThat(status.getReason()).isEqualTo("unknown zone");
        assertThat(inbox.messages).isEmpty();
    }

    @Test
    @DisplayName("두 화면이 같은 tick에 같은 메시지를 받는다")
    void twoClientsReceiveSameMessage() throws Exception {
        Inbox a = connect("zone-test");
        a.next();                                            // hello
        Inbox b = connect("zone-test");
        b.next();                                            // hello

        JsonNode fromB = b.nextZoneState();

        List<JsonNode> fromA = new ArrayList<>();
        for (int i = 0; i < MAX_SKIP && !fromA.contains(fromB); i++) {
            fromA.add(a.next());
        }
        assertThat(fromA).contains(fromB);
    }

    @Test
    @DisplayName("화면이 보낸 메시지는 무시하고 연결을 유지한다")
    void ignoresClientMessages() throws Exception {
        Inbox inbox = connect("zone-test");
        WebSocketSession session = opened.get(opened.size() - 1);
        inbox.next();                                        // hello

        session.sendMessage(new TextMessage("{\"type\":\"ack\"}"));
        session.sendMessage(new TextMessage("not json"));

        for (int i = 0; i < 3; i++) {
            inbox.nextZoneState();
        }
        assertThat(session.isOpen()).isTrue();
    }

    @ParameterizedTest
    @ValueSource(strings = {"http://localhost:5173", "http://127.0.0.1:5173"})
    @DisplayName("허용 출처 패턴의 화면은 접속한다")
    void allowsLocalhostOrigin(String origin) throws Exception {
        Inbox inbox = new Inbox();
        opened.add(connectWithOrigin(inbox, origin).get(5, TimeUnit.SECONDS));

        assertThat(inbox.next().get("type").asString()).isEqualTo("hello");
    }

    @Test
    @DisplayName("허용하지 않는 출처는 핸드셰이크에서 거절한다")
    void rejectsForeignOrigin() {
        CompletableFuture<WebSocketSession> future = connectWithOrigin(new Inbox(), "http://example.com");

        assertThatThrownBy(() -> future.get(5, TimeUnit.SECONDS)).isInstanceOf(ExecutionException.class);
    }

    @Test
    @DisplayName("실제 Tomcat 세션에 차단 전송 제한 2000ms가 걸린다")
    void setsTomcatBlockingSendTimeout() throws Exception {
        connect("zone-test").next();
        await().atMost(WAIT).until(() -> sessions.sessionCount("zone-test") == 1);

        WebSocketSession raw = WebSocketSessionDecorator.unwrap(sessions.sessions("zone-test").get(0));
        Session tomcat = ((NativeWebSocketSession) raw).getNativeSession(Session.class);

        assertThat(tomcat.getUserProperties().get(Constants.BLOCKING_SEND_TIMEOUT_PROPERTY)).isEqualTo(2000L);
    }

    @Test
    @DisplayName("화면이 닫으면 방송 대상에서 빠진다")
    void removesSessionOnClose() throws Exception {
        connect("zone-test");
        await().atMost(WAIT).until(() -> sessions.sessionCount() == 1);

        opened.get(0).close();

        await().atMost(WAIT).until(() -> sessions.sessionCount() == 0);
    }
}
