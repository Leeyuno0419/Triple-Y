package com.tripley.crowdsight.alert;

import java.time.Clock;
import java.util.ArrayDeque;
import java.util.Deque;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

import org.springframework.stereotype.Component;

import com.tripley.crowdsight.config.CrowdsightProperties;

import lombok.extern.slf4j.Slf4j;

/**
 * 구역별 미확인 알림 (api-spec 3.1·3.3). 메모리에만 두고 서버를 재시작하면 비워진다 (api-spec 4.5).
 * 구역당 unacked-alert-limit개까지 두고, 넘으면 가장 오래된 것부터 버린다.
 * S5에는 확인 기능이 없어 저장한 알림이 곧 미확인 알림이다. find·ack는 S6이 더한다.
 * 스레드 규칙: issue는 재생 스레드, unacked는 Tomcat 스레드(hello)가 부른다. 모든 공개 메서드는 this로 잠근다.
 * 덧붙이기·상한 확인·맨 앞 버리기를 한 번에 해야 해서 Concurrent 컬렉션 대신 잠금을 쓴다. 쓰기는 1초에 몇 번 이하다.
 */
@Slf4j
@Component
public final class AlertStore {

    private final int limit;
    private final AlertIdGenerator ids;
    private final Map<String, Deque<Alert>> byZone = new HashMap<>();   // this 잠금 안에서만 읽고 쓴다

    public AlertStore(CrowdsightProperties props, Clock clock) {
        this.limit = props.unackedAlertLimit();
        this.ids = new AlertIdGenerator(clock);
    }

    /** 사건에 ID·구역·t·frame_ts를 붙여 저장하고 돌려준다. 같은 초 zone_state의 t·frame_ts를 넘긴다. */
    public synchronized Alert issue(String zoneId, int t, String frameTs, AlertEvent event) {
        Alert alert = new Alert(ids.next(), zoneId, t, frameTs, event.level(), event.reason(), event.message(),
                event.value(), event.cellIds());
        Deque<Alert> alerts = byZone.computeIfAbsent(zoneId, k -> new ArrayDeque<>());
        alerts.addLast(alert);
        log.info("알림 zone={} t={} alert_id={} reason={} level={} value={}", zoneId, t, alert.alertId(),
                alert.reason(), alert.level(), alert.value());
        if (alerts.size() > limit) {
            Alert dropped = alerts.removeFirst();
            log.warn("미확인 알림이 {}개를 넘어 가장 오래된 알림을 버림 zone={} alert_id={}", limit, zoneId,
                    dropped.alertId());
        }
        return alert;
    }

    /** 구역의 미확인 알림 (오래된 것부터). 불변 복사본이라 받은 뒤 바뀌지 않는다. 없는 구역은 빈 목록. */
    public synchronized List<Alert> unacked(String zoneId) {
        Deque<Alert> alerts = byZone.get(zoneId);
        return alerts == null ? List.of() : List.copyOf(alerts);
    }
}
