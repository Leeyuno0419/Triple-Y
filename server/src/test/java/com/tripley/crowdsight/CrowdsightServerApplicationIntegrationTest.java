package com.tripley.crowdsight;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Clock;
import java.time.ZoneId;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import com.tripley.crowdsight.config.CrowdsightProperties;
import com.tripley.crowdsight.config.TestProperties;

@SpringBootTest(properties = {
        "crowdsight.timeline-dir=src/test/resources/timeline",
        "crowdsight.timeline-files=valid_v02.json"
})
class CrowdsightServerApplicationIntegrationTest {

    @Autowired
    private CrowdsightProperties props;

    @Autowired
    private Clock clock;

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

    @Test
    @DisplayName("application.yml의 등급 기본값을 읽는다")
    void bindsDefaultGradeSettings() {
        assertThat(props.grade()).isEqualTo(TestProperties.GRADE);
    }

    @Test
    @DisplayName("application.yml의 불안정·유입 기본값을 읽는다")
    void bindsDefaultInstabilityInflowSettings() {
        assertThat(props.instability()).isEqualTo(TestProperties.INSTABILITY);
        assertThat(props.inflow()).isEqualTo(TestProperties.INFLOW);
    }

    @Test
    @DisplayName("application.yml의 ws·허용 출처·시간대 기본값을 읽는다")
    void bindsDefaultWsSettings() {
        assertThat(props.ws()).isEqualTo(TestProperties.WS);
        assertThat(props.corsOriginPatterns()).isEqualTo(TestProperties.CORS);
        assertThat(props.timeZone()).isEqualTo("Asia/Seoul");
    }

    @Test
    @DisplayName("Clock 빈은 설정 시간대를 쓴다")
    void clockUsesConfiguredZone() {
        assertThat(clock.getZone()).isEqualTo(ZoneId.of("Asia/Seoul"));
    }
}
