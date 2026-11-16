package com.tripley.crowdsight.api;

import static com.tripley.crowdsight.timeline.TimelineFixtures.MAPPER;
import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import com.tripley.crowdsight.config.CrowdsightProperties;
import com.tripley.crowdsight.config.TestProperties;
import com.tripley.crowdsight.replay.TickStats;
import com.tripley.crowdsight.replay.ZoneRegistry;
import com.tripley.crowdsight.replay.ZoneRuntime;
import com.tripley.crowdsight.timeline.TimelineLoader;
import com.tripley.crowdsight.ws.ZoneSessions;

class HealthControllerTest {

    private final TickStats stats = new TickStats();

    /** 주어진 구역 목록·설정과 테스트 필드 TickStats로 만든 컨트롤러. */
    private HealthController controller(ZoneRegistry zones, CrowdsightProperties props) {
        return new HealthController(zones, new ZoneSessions(props), stats);
    }

    private static ZoneRegistry registry(CrowdsightProperties props) {
        return new ZoneRegistry(new TimelineLoader(MAPPER, props), props);
    }

    @Test
    @DisplayName("tick 전에는 처리 시간이 null이다")
    void healthBeforeFirstTick() {
        CrowdsightProperties props = TestProperties.replay(1000, true);

        HealthResponse health = controller(registry(props), props).health();

        assertThat(health).isEqualTo(new HealthResponse("UP",
                List.of(new ZoneHealth("zone-test", "playing", 0, true)), 0, null, null));
    }

    @Test
    @DisplayName("처리 시간 last·max를 준다")
    void healthReportsTickTime() {
        CrowdsightProperties props = TestProperties.replay(1000, true);
        HealthController controller = controller(registry(props), props);
        stats.record(1_234_567);
        stats.record(500_000);

        HealthResponse health = controller.health();

        assertThat(health.lastTickMs()).isEqualTo(0.5);
        assertThat(health.maxTickMs()).isEqualTo(1.235);
    }

    @Test
    @DisplayName("재생 상태를 반영한다")
    void healthReflectsPlaybackState() {
        CrowdsightProperties props = TestProperties.replay(1000, false);
        ZoneRegistry zones = registry(props);
        ZoneRuntime zone = zones.find("zone-test").orElseThrow();
        for (int i = 0; i < 6; i++) {
            zone.tick();
        }

        HealthResponse health = controller(zones, props).health();

        assertThat(health.zones()).containsExactly(new ZoneHealth("zone-test", "ended", 4, false));
    }
}
