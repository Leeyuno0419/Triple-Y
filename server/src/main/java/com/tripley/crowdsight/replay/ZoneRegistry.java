package com.tripley.crowdsight.replay;

import java.util.List;

import org.springframework.stereotype.Component;

import com.tripley.crowdsight.config.CrowdsightProperties;
import com.tripley.crowdsight.grade.ZoneGrader;
import com.tripley.crowdsight.timeline.TimelineLoader;
import com.tripley.crowdsight.timeline.ZoneTimeline;

import lombok.extern.slf4j.Slf4j;

/**
 * 서버가 재생하는 구역 목록. 생성할 때 타임라인을 모두 읽고, 하나라도 틀리면 예외로 서버 시작을 멈춘다.
 * 목록은 만든 뒤 바뀌지 않으므로 여러 스레드에서 읽어도 된다.
 */
@Slf4j
@Component
public class ZoneRegistry {

    private final List<ZoneRuntime> zones;

    public ZoneRegistry(TimelineLoader loader, CrowdsightProperties props) {
        this.zones = loader.loadAll().stream()
                .map(timeline -> register(timeline, props))
                .toList();
    }

    /** 설정 순서의 모든 구역. */
    public List<ZoneRuntime> all() {
        return zones;
    }

    private static ZoneRuntime register(ZoneTimeline timeline, CrowdsightProperties props) {
        ZoneGrader grader = new ZoneGrader(timeline.meta().cells(), props.grade());
        int cells = timeline.meta().cells().size();
        double minArea = props.grade().minWalkableAreaM2();
        log.info("구역 등록 zone={} 길이={}초 반복={} 판정 대상 셀={}/{} (면적 ≥ {}㎡)", timeline.zoneId(),
                timeline.durationS(), props.replay().loop(), grader.eligibleCount(), cells, minArea);
        if (grader.eligibleCount() == 0) {
            log.warn("판정 대상 셀이 없어 구역 등급은 늘 정상입니다 zone={} (min-walkable-area-m2={})",
                    timeline.zoneId(), minArea);
        }
        return new ZoneRuntime(new ZonePlayer(timeline, props.replay().loop()), grader);
    }
}
