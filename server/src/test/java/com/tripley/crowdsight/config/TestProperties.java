package com.tripley.crowdsight.config;

import java.util.List;

import com.tripley.crowdsight.grade.DensityThresholds;
import com.tripley.crowdsight.grade.GradeSettings;

/** 테스트용 CrowdsightProperties·GradeSettings. S3~S6이 성분을 늘리면 여기만 고친다. */
public final class TestProperties {

    /** application.yml crowdsight.grade 기본값과 같다 (bindsDefaultGradeSettings가 확인). */
    public static final GradeSettings GRADE = new GradeSettings(new DensityThresholds(3.0, 4.0, 5.0), 2, 10, 2.0);

    private TestProperties() {
    }

    /** 모든 값을 지정해 만든다. 등급 설정은 GRADE. */
    public static CrowdsightProperties of(String timelineDir, List<String> files, long intervalMs, boolean loop) {
        return new CrowdsightProperties(timelineDir, files, new CrowdsightProperties.Replay(intervalMs, loop), GRADE);
    }

    /** test 리소스 fixture를 쓰고 재생 설정만 지정한다. */
    public static CrowdsightProperties replay(long intervalMs, boolean loop) {
        return of("src/test/resources/timeline", List.of("valid_v02.json"), intervalMs, loop);
    }
}
