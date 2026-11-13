package com.tripley.crowdsight.ws;

import org.springframework.stereotype.Component;

import com.tripley.crowdsight.replay.PlaybackSnapshot;
import com.tripley.crowdsight.replay.ZoneBroadcaster;
import com.tripley.crowdsight.replay.ZoneStep;

import lombok.RequiredArgsConstructor;
import tools.jackson.databind.json.JsonMapper;

/**
 * 재생 결과를 메시지당 JSON 한 번으로 바꿔 그 구역 화면 모두에 보낸다.
 * 스레드 규칙: 재생 작업에서만 불린다. 세션별 전송 안전은 ZoneSessions가 맡는다.
 */
@Component
@RequiredArgsConstructor
public class WsZoneBroadcaster implements ZoneBroadcaster {

    private final MessageFactory messages;
    private final ZoneSessions sessions;
    private final JsonMapper jsonMapper;

    @Override
    public void playback(String zoneId, PlaybackSnapshot snapshot) {
        send(zoneId, messages.playback(zoneId, snapshot));
    }

    @Override
    public void zoneState(String zoneId, ZoneStep step) {
        send(zoneId, messages.zoneState(zoneId, step, messages.frameTs()));
    }

    private void send(String zoneId, Object message) {
        sessions.broadcast(zoneId, jsonMapper.writeValueAsString(message));
    }
}
