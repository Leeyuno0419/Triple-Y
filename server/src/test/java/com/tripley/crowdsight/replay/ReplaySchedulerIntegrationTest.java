package com.tripley.crowdsight.replay;

import static org.assertj.core.api.Assertions.assertThat;
import static org.awaitility.Awaitility.await;

import java.time.Duration;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest(properties = {
        "crowdsight.timeline-dir=src/test/resources/timeline",
        "crowdsight.timeline-files=valid_v02.json",
        "crowdsight.replay.interval-ms=50"
})
class ReplaySchedulerIntegrationTest {

    @Autowired
    private ZoneRegistry registry;

    @Autowired
    private ReplayScheduler scheduler;

    @Test
    @DisplayName("설정한 fixture 구역을 등록한다")
    void loadsFixtureZone() {
        assertThat(registry.all()).hasSize(1);
        ZonePlayer player = registry.all().get(0);
        assertThat(player.zoneId()).isEqualTo("zone-test");
        assertThat(player.timeline().source().isAbsolute()).isTrue();
        assertThat(player.timeline().source().toString()).endsWith("valid_v02.json");
    }

    @Test
    @DisplayName("컨텍스트가 뜨면 재생이 저절로 시작된다")
    void advancesOnSchedule() {
        assertThat(scheduler.isRunning()).isTrue();
        ZonePlayer player = registry.all().get(0);
        Set<Integer> seen = ConcurrentHashMap.newKeySet();

        await().pollInterval(Duration.ofMillis(10)).atMost(Duration.ofSeconds(2)).until(() -> {
            seen.add(player.snapshot().t());
            return seen.size() >= 3;
        });
    }
}
