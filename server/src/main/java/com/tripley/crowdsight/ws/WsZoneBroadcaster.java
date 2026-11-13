package com.tripley.crowdsight.ws;

import org.springframework.stereotype.Component;

import com.tripley.crowdsight.alert.Alert;
import com.tripley.crowdsight.alert.AlertEvent;
import com.tripley.crowdsight.alert.AlertStore;
import com.tripley.crowdsight.replay.PlaybackSnapshot;
import com.tripley.crowdsight.replay.ZoneBroadcaster;
import com.tripley.crowdsight.replay.ZoneStep;

import lombok.RequiredArgsConstructor;
import tools.jackson.databind.json.JsonMapper;

/**
 * 재생 결과를 메시지당 JSON 한 번으로 바꿔 그 구역 화면 모두에 보낸다.
 * zoneState: frame_ts를 tick마다 한 번 만들고, zone_state 다음에 그 초 알림을 발급(AlertStore)해 alert로 보낸다.
 * 화면이 없어도 알림은 발급·저장한다 (다음 hello의 unacked_alerts).
 * 스레드 규칙: 재생 작업에서만 불린다. 세션별 전송 안전은 ZoneSessions, 저장 안전은 AlertStore가 맡는다.
 */
@Component
@RequiredArgsConstructor
public class WsZoneBroadcaster implements ZoneBroadcaster {

    private final MessageFactory messages;
    private final ZoneSessions sessions;
    private final JsonMapper jsonMapper;
    private final AlertStore alerts;

    @Override
    public void playback(String zoneId, PlaybackSnapshot snapshot) {
        send(zoneId, messages.playback(zoneId, snapshot));
    }

    @Override
    public void zoneState(String zoneId, ZoneStep step) {
        String frameTs = messages.frameTs();
        send(zoneId, messages.zoneState(zoneId, step, frameTs));
        for (AlertEvent event : step.alerts()) {
            Alert alert = alerts.issue(zoneId, step.evaluation().t(), frameTs, event);
            send(zoneId, messages.alert(alert));
        }
    }

    private void send(String zoneId, Object message) {
        sessions.broadcast(zoneId, jsonMapper.writeValueAsString(message));
    }
}
