package com.tripley.crowdsight.replay;

import static com.tripley.crowdsight.timeline.TimelineFixtures.MAPPER;
import static com.tripley.crowdsight.timeline.TimelineFixtures.fixturePath;
import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import com.tripley.crowdsight.config.CrowdsightProperties;
import com.tripley.crowdsight.config.TestProperties;
import com.tripley.crowdsight.timeline.TimelineLoader;

class ZoneRegistryTest {

    @Test
    @DisplayName("구역 ID로 찾는다")
    void findsById() {
        CrowdsightProperties props = TestProperties.of(fixturePath().getParent().toString(),
                List.of("valid_v02.json"), 1000, true);
        ZoneRegistry registry = new ZoneRegistry(new TimelineLoader(MAPPER, props), props);

        assertThat(registry.find("zone-test")).containsSame(registry.all().get(0));
        assertThat(registry.find("nope")).isEmpty();
        assertThat(registry.find(null)).isEmpty();
        assertThat(registry.find("")).isEmpty();
    }
}
