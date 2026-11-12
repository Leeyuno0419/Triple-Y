package com.tripley.crowdsight.config;

import java.util.List;

/** 테스트용 CrowdsightProperties. S2~S6이 성분을 늘리면 여기만 고친다. */
public final class TestProperties {

    private TestProperties() {
    }

    /** 모든 값을 지정해 만든다. */
    public static CrowdsightProperties of(String timelineDir, List<String> files, long intervalMs, boolean loop) {
        return new CrowdsightProperties(timelineDir, files, new CrowdsightProperties.Replay(intervalMs, loop));
    }

    /** test 리소스 fixture를 쓰고 재생 설정만 지정한다. */
    public static CrowdsightProperties replay(long intervalMs, boolean loop) {
        return of("src/test/resources/timeline", List.of("valid_v02.json"), intervalMs, loop);
    }
}
