package com.tripley.crowdsight.replay;

import java.util.List;

import org.springframework.stereotype.Component;

import com.tripley.crowdsight.config.CrowdsightProperties;
import com.tripley.crowdsight.timeline.TimelineLoader;

import lombok.extern.slf4j.Slf4j;

/**
 * 서버가 재생하는 구역 목록. 생성할 때 타임라인을 모두 읽고, 하나라도 틀리면 예외로 서버 시작을 멈춘다.
 * 목록은 만든 뒤 바뀌지 않으므로 여러 스레드에서 읽어도 된다. S2에서 ZonePlayer 대신 ZoneRuntime을 담는다.
 */
@Slf4j
@Component
public class ZoneRegistry {

    private final List<ZonePlayer> players;

    public ZoneRegistry(TimelineLoader loader, CrowdsightProperties props) {
        this.players = loader.loadAll().stream()
                .map(timeline -> new ZonePlayer(timeline, props.replay().loop()))
                .toList();
        players.forEach(p -> log.info("구역 등록 zone={} 길이={}초 반복={}",
                p.zoneId(), p.timeline().durationS(), props.replay().loop()));
    }

    /** 설정 순서의 모든 구역. */
    public List<ZonePlayer> all() {
        return players;
    }
}
