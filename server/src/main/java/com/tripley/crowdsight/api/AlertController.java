package com.tripley.crowdsight.api;

import java.time.Clock;
import java.util.List;
import java.util.Optional;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import com.tripley.crowdsight.alert.AlertAck;
import com.tripley.crowdsight.alert.AlertLogWriter;
import com.tripley.crowdsight.alert.AlertStore;
import com.tripley.crowdsight.replay.ZoneRegistry;
import com.tripley.crowdsight.ws.FrameTimestamps;

import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;

/**
 * 알림 확인과 알림 목록 REST (api-spec 2절·4.5).
 * 확인은 처음 시각만 남기고(멱등), 처음 확인일 때만 확인 기록 파일에 한 줄을 쓴다. 확인은 다른 화면에 방송하지 않는다.
 * 스레드 규칙: Tomcat 요청 스레드에서 동시에 불린다. 상태가 없고, 저장소·기록 파일이 각자 잠근다.
 */
@Slf4j
@RestController
@RequestMapping("/api")
@RequiredArgsConstructor
public class AlertController {

    private final AlertStore alerts;
    private final AlertLogWriter alertLog;
    private final ZoneRegistry zones;
    private final Clock clock;

    /** 알림 확인. 200 {alert_id, acked_at}, 이미 확인했으면 처음 시각, 보관 중이 아니면 404. */
    @PostMapping("/alerts/{alertId}/ack")
    public ResponseEntity<AckResponse> ack(@PathVariable String alertId) {
        Optional<AlertAck> result = alerts.ack(alertId, FrameTimestamps.now(clock));
        if (result.isEmpty()) {
            log.info("없는 알림 확인 요청 alert_id={}", alertId);
            return ResponseEntity.notFound().build();
        }
        AlertAck ack = result.get();
        if (ack.firstAck()) {
            alertLog.append(ack);
        }
        return ResponseEntity.ok(new AckResponse(alertId, ack.ackedAt()));
    }

    /** 구역 알림 목록 (오래된 것부터). unacked=true면 미확인만. 없는 구역은 404. */
    @GetMapping("/zones/{zoneId}/alerts")
    public ResponseEntity<List<AlertView>> alerts(@PathVariable String zoneId,
                                                  @RequestParam(defaultValue = "false") boolean unacked) {
        if (zones.find(zoneId).isEmpty()) {
            return ResponseEntity.notFound().build();
        }
        return ResponseEntity.ok(alerts.list(zoneId, unacked).stream().map(AlertView::of).toList());
    }
}
