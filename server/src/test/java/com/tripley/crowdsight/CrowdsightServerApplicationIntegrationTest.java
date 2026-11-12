package com.tripley.crowdsight;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import com.tripley.crowdsight.config.CrowdsightProperties;

@SpringBootTest(properties = {
        "crowdsight.timeline-dir=src/test/resources/timeline",
        "crowdsight.timeline-files=valid_v02.json"
})
class CrowdsightServerApplicationIntegrationTest {

    @Autowired
    private CrowdsightProperties props;

    @Test
    @DisplayName("스프링 컨텍스트가 오류 없이 뜬다")
    void contextLoads() {
    }

    @Test
    @DisplayName("application.yml의 재생 기본값을 읽는다")
    void bindsDefaultReplaySettings() {
        assertThat(props.replay().intervalMs()).isEqualTo(1000);
        assertThat(props.replay().loop()).isTrue();
    }

}
