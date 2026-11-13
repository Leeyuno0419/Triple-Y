package com.tripley.crowdsight.config;

import java.util.List;

import com.tripley.crowdsight.grade.DensityThresholds;
import com.tripley.crowdsight.grade.GradeSettings;
import com.tripley.crowdsight.grade.InflowSettings;
import com.tripley.crowdsight.grade.InstabilitySettings;
import com.tripley.crowdsight.grade.ZoneGrader;
import com.tripley.crowdsight.timeline.CellMeta;

/** 테스트용 CrowdsightProperties·GradeSettings. S3~S6이 성분을 늘리면 여기만 고친다. */
public final class TestProperties {

    /** application.yml crowdsight.grade 기본값과 같다 (bindsDefaultGradeSettings가 확인). */
    public static final GradeSettings GRADE = new GradeSettings(new DensityThresholds(3.0, 4.0, 5.0), 2, 10, 2.0);

    /** application.yml crowdsight.instability 기본값과 같다 (bindsDefaultInstabilityInflowSettings가 확인). */
    public static final InstabilitySettings INSTABILITY = new InstabilitySettings(0.02, 3);

    /** application.yml crowdsight.inflow 기본값과 같다. */
    public static final InflowSettings INFLOW = new InflowSettings(0.6, 5, 3, 10, 3.0);

    /** application.yml crowdsight.time-zone 기본값. */
    public static final String TIME_ZONE = "Asia/Seoul";

    /** application.yml crowdsight.ws 기본값과 같다 (bindsDefaultWsSettings가 확인). */
    public static final CrowdsightProperties.Ws WS = new CrowdsightProperties.Ws(30000, 2000, 524288);

    /** application.yml crowdsight.cors-origin-patterns 기본값과 같다. */
    public static final List<String> CORS = List.of("http://localhost:*", "http://127.0.0.1:*");

    private TestProperties() {
    }

    /** 기본 설정(등급·불안정·유입)으로 판정기를 만든다. */
    public static ZoneGrader grader(List<CellMeta> cells) {
        return new ZoneGrader(cells, GRADE, INSTABILITY, INFLOW);
    }

    /** 모든 값을 지정해 만든다. 등급·ws·시간대·허용 출처는 기본값. */
    public static CrowdsightProperties of(String timelineDir, List<String> files, long intervalMs, boolean loop) {
        return full(timelineDir, files, intervalMs, loop, WS);
    }

    /** test 리소스 fixture를 쓰고 재생 설정만 지정한다. */
    public static CrowdsightProperties replay(long intervalMs, boolean loop) {
        return of("src/test/resources/timeline", List.of("valid_v02.json"), intervalMs, loop);
    }

    /** fixture 기본값에 WebSocket 설정만 바꾼다. */
    public static CrowdsightProperties ws(CrowdsightProperties.Ws ws) {
        return full("src/test/resources/timeline", List.of("valid_v02.json"), 1000, true, ws);
    }

    private static CrowdsightProperties full(String dir, List<String> files, long intervalMs, boolean loop,
                                             CrowdsightProperties.Ws ws) {
        return new CrowdsightProperties(dir, files, TIME_ZONE, new CrowdsightProperties.Replay(intervalMs, loop),
                GRADE, INSTABILITY, INFLOW, ws, CORS);
    }
}
