package com.tripley.crowdsight.alert;

import java.time.Clock;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;

import org.springframework.stereotype.Component;

import com.tripley.crowdsight.config.CrowdsightProperties;

import lombok.extern.slf4j.Slf4j;

/**
 * 구역별 알림 보관 (api-spec 3.1·3.3·4.5). 메모리에만 두고 서버를 재시작하면 비워진다.
 * 구역마다 발급 순 목록 하나에 미확인·확인한 알림을 함께 두고, unacked-alert-limit개를 넘으면
 * 확인한 것 중 가장 오래된 것을, 없으면 가장 오래된 미확인을 버린다. 그래서 미확인은 미확인만 limit개를 넘을 때 버려진다.
 * 확인(ack)은 처음 시각만 남기고, 다시 확인하면 그 시각을 돌려준다 (멱등).
 * 스레드 규칙: issue는 재생 스레드, unacked는 Tomcat WS 스레드(hello), ack·list는 Tomcat 요청 스레드가 부른다.
 * 모든 공개 메서드는 this로 잠근다. 덧붙이기·상한·확인 여부 판단을 한 번에 해야 해서 Concurrent 컬렉션 대신 잠금을 쓴다.
 * 잠금 안 작업은 최대 (구역 수 × limit)개 훑기이고 호출은 1초에 몇 번 이하다.
 */
@Slf4j
@Component
public final class AlertStore {

    private final int limit;
    private final AlertIdGenerator ids;
    private final Map<String, List<StoredAlert>> byZone = new HashMap<>();   // this 잠금 안에서만. 오래된 것 앞

    public AlertStore(CrowdsightProperties props, Clock clock) {
        this.limit = props.unackedAlertLimit();
        this.ids = new AlertIdGenerator(clock);
    }

    /** 사건에 ID·구역·t·frame_ts를 붙여 저장하고 돌려준다. 같은 초 zone_state의 t·frame_ts를 넘긴다. */
    public synchronized Alert issue(String zoneId, int t, String frameTs, AlertEvent event) {
        Alert alert = new Alert(ids.next(), zoneId, t, frameTs, event.level(), event.reason(), event.message(),
                event.value(), event.cellIds());
        List<StoredAlert> alerts = byZone.computeIfAbsent(zoneId, k -> new ArrayList<>());
        alerts.add(new StoredAlert(alert, null));
        log.info("알림 zone={} t={} alert_id={} reason={} level={} value={}", zoneId, t, alert.alertId(),
                alert.reason(), alert.level(), alert.value());
        if (alerts.size() > limit) {
            dropOne(zoneId, alerts);
        }
        return alert;
    }

    /** 구역의 미확인 알림 (오래된 것부터, hello용). 불변 목록이라 받은 뒤 바뀌지 않는다. 없는 구역은 빈 목록. */
    public synchronized List<Alert> unacked(String zoneId) {
        return byZone.getOrDefault(zoneId, List.of()).stream()
                .filter(s -> !s.acked())
                .map(StoredAlert::alert)
                .toList();
    }

    /** 구역의 보관 알림 (오래된 것부터). unackedOnly면 미확인만. 불변 목록. 없는 구역은 빈 목록. */
    public synchronized List<StoredAlert> list(String zoneId, boolean unackedOnly) {
        return byZone.getOrDefault(zoneId, List.of()).stream()
                .filter(s -> !unackedOnly || !s.acked())
                .toList();
    }

    /**
     * 알림을 확인한다. 처음이면 ackedAt을 기록하고 firstAck true, 이미 확인했으면 처음 시각과 false.
     * 보관 중이 아닌 ID(없음·상한으로 버려짐)는 빈 값.
     */
    public synchronized Optional<AlertAck> ack(String alertId, String ackedAt) {
        Objects.requireNonNull(ackedAt, "ackedAt");
        for (List<StoredAlert> alerts : byZone.values()) {
            for (int i = 0; i < alerts.size(); i++) {
                StoredAlert stored = alerts.get(i);
                if (!stored.alert().alertId().equals(alertId)) {
                    continue;
                }
                if (stored.acked()) {
                    return Optional.of(new AlertAck(stored.alert(), stored.ackedAt(), false));
                }
                alerts.set(i, new StoredAlert(stored.alert(), ackedAt));
                log.info("알림 확인 zone={} t={} alert_id={} acked_at={}", stored.alert().zoneId(), stored.alert().t(),
                        alertId, ackedAt);
                return Optional.of(new AlertAck(stored.alert(), ackedAt, true));
            }
        }
        return Optional.empty();
    }

    /** 상한을 넘은 목록에서 하나 버린다. 확인한 것 중 가장 오래된 것, 없으면 가장 오래된 미확인. */
    private void dropOne(String zoneId, List<StoredAlert> alerts) {
        for (int i = 0; i < alerts.size(); i++) {
            if (alerts.get(i).acked()) {
                StoredAlert dropped = alerts.remove(i);
                log.debug("보관 한도를 넘어 확인한 알림을 버림 zone={} alert_id={}", zoneId, dropped.alert().alertId());
                return;
            }
        }
        StoredAlert dropped = alerts.remove(0);
        log.warn("미확인 알림이 {}개를 넘어 가장 오래된 알림을 버림 zone={} alert_id={}", limit, zoneId,
                dropped.alert().alertId());
    }
}
