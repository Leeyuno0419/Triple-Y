package com.tripley.crowdsight.config;

import java.util.List;

import org.springframework.boot.context.properties.ConfigurationProperties;

/**
 * crowdsight.* 설정 (application.yml). 기준값·시간·경로는 이 record 한 곳에만 둔다.
 * 값 검사는 compact constructor에서 한다 (validation 스타터 안 씀). 틀리면 서버가 시작하지 않는다.
 * grade·instability·inflow·ws·alert-log·cors-origin-patterns·time-zone은 그 값을 쓰는 PR(S2~S6)에서 추가한다.
 *
 * @param timelineDir   타임라인 폴더. 상대 경로면 작업 폴더(bootRun·test는 server/) 기준
 * @param timelineFiles timelineDir 안의 파일 이름. 1개 이상, 파일당 구역 1개
 * @param replay        재생 설정
 */
@ConfigurationProperties("crowdsight")
public record CrowdsightProperties(String timelineDir, List<String> timelineFiles, Replay replay) {

    public CrowdsightProperties {
        if (timelineDir == null || timelineDir.isBlank()) {
            throw new IllegalArgumentException("crowdsight.timeline-dir 가 없습니다.");
        }
        if (timelineFiles == null || timelineFiles.isEmpty()) {
            throw new IllegalArgumentException("crowdsight.timeline-files 에 파일이 1개 이상 필요합니다.");
        }
        if (timelineFiles.stream().anyMatch(name -> name == null || name.isBlank())) {
            throw new IllegalArgumentException("crowdsight.timeline-files 에 빈 이름이 있습니다.");
        }
        if (replay == null) {
            throw new IllegalArgumentException("crowdsight.replay 가 없습니다.");
        }
        timelineFiles = List.copyOf(timelineFiles);
    }

    /**
     * 재생 설정.
     *
     * @param intervalMs 타임라인 1칸을 재생하는 간격(ms). 운영 1000, 테스트만 짧게
     * @param loop       끝에서 처음으로 돌아갈지
     */
    public record Replay(long intervalMs, boolean loop) {

        public Replay {
            if (intervalMs <= 0) {
                throw new IllegalArgumentException("crowdsight.replay.interval-ms 는 0보다 커야 합니다: " + intervalMs);
            }
        }
    }
}
