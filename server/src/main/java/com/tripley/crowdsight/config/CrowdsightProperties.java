package com.tripley.crowdsight.config;

import java.time.DateTimeException;
import java.time.ZoneId;
import java.util.List;

import org.springframework.boot.context.properties.ConfigurationProperties;

import com.tripley.crowdsight.grade.GradeSettings;
import com.tripley.crowdsight.grade.InflowSettings;
import com.tripley.crowdsight.grade.InstabilitySettings;

/**
 * crowdsight.* 설정 (application.yml). 기준값·시간·경로는 이 record 한 곳에만 둔다.
 * 값 검사는 compact constructor에서 한다 (validation 스타터 안 씀). 틀리면 서버가 시작하지 않는다.
 * grade·instability·inflow는 grade 패키지의 record로 바로 묶고, 그 값 검사는 해당 record가 한다.
 * alert-log는 그 값을 쓰는 PR(S6)에서 추가한다.
 *
 * @param timelineDir        타임라인 폴더. 상대 경로면 작업 폴더(bootRun·test는 server/) 기준
 * @param timelineFiles      timelineDir 안의 파일 이름. 1개 이상, 파일당 구역 1개
 * @param timeZone           서버 시계의 시간대 (IANA 이름, 예: Asia/Seoul). frame_ts 오프셋이 된다
 * @param replay             재생 설정
 * @param grade              등급 판정 설정 (crowdsight.grade.*)
 * @param instability        셀 불안정 판정 설정 (crowdsight.instability.*)
 * @param inflow             유입 경보 설정 (crowdsight.inflow.*)
 * @param unackedAlertLimit  구역당 미확인 알림 최대 개수 (1 이상). 넘으면 가장 오래된 것부터 버린다
 * @param ws                 WebSocket 설정 (crowdsight.ws.*)
 * @param corsOriginPatterns 허용 출처 패턴. WebSocket(S3)과 REST(S6)가 같이 쓴다 (결정 기록 2)
 */
@ConfigurationProperties("crowdsight")
public record CrowdsightProperties(String timelineDir, List<String> timelineFiles, String timeZone, Replay replay,
                                   GradeSettings grade, InstabilitySettings instability, InflowSettings inflow,
                                   int unackedAlertLimit, Ws ws, List<String> corsOriginPatterns) {

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
        if (timeZone == null || timeZone.isBlank()) {
            throw new IllegalArgumentException("crowdsight.time-zone 이 없습니다.");
        }
        try {
            ZoneId.of(timeZone);
        } catch (DateTimeException e) {
            // 원인을 잇지 않는다: 시작 실패 로그의 root cause가 설정 키를 보여 주도록
            throw new IllegalArgumentException("crowdsight.time-zone 을 알 수 없습니다: " + timeZone
                    + " (" + e.getMessage() + ")");
        }
        if (replay == null) {
            throw new IllegalArgumentException("crowdsight.replay 가 없습니다.");
        }
        if (grade == null) {
            throw new IllegalArgumentException("crowdsight.grade 가 없습니다.");
        }
        if (instability == null) {
            throw new IllegalArgumentException("crowdsight.instability 가 없습니다.");
        }
        if (inflow == null) {
            throw new IllegalArgumentException("crowdsight.inflow 가 없습니다.");
        }
        if (unackedAlertLimit < 1) {     // 키가 없으면 0으로 묶여 여기서 거부된다
            throw new IllegalArgumentException(
                    "crowdsight.unacked-alert-limit 는 1 이상이어야 합니다: " + unackedAlertLimit);
        }
        if (ws == null) {
            throw new IllegalArgumentException("crowdsight.ws 가 없습니다.");
        }
        if (corsOriginPatterns == null || corsOriginPatterns.isEmpty()) {
            throw new IllegalArgumentException("crowdsight.cors-origin-patterns 에 패턴이 1개 이상 필요합니다.");
        }
        if (corsOriginPatterns.stream().anyMatch(p -> p == null || p.isBlank())) {
            throw new IllegalArgumentException("crowdsight.cors-origin-patterns 에 빈 패턴이 있습니다.");
        }
        timelineFiles = List.copyOf(timelineFiles);
        corsOriginPatterns = List.copyOf(corsOriginPatterns);
    }

    /** 서버 시계의 시간대. 생성할 때 검사했으므로 예외가 나지 않는다. */
    public ZoneId clockZone() {
        return ZoneId.of(timeZone);
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

    /**
     * WebSocket 설정 (api-spec 3.5).
     *
     * @param pingIntervalMs       ping 간격(ms)
     * @param sendTimeLimitMs      메시지 하나 보내기가 막히는 최대 시간(ms). Tomcat 차단 전송 제한과 데코레이터 한도에 쓴다
     * @param bufferSizeLimitBytes 못 보내고 쌓인 메시지 한도(바이트). 두 스레드가 겹쳐 보낼 때만 검사된다
     */
    public record Ws(long pingIntervalMs, int sendTimeLimitMs, int bufferSizeLimitBytes) {

        public Ws {
            if (pingIntervalMs <= 0) {
                throw new IllegalArgumentException("crowdsight.ws.ping-interval-ms 는 0보다 커야 합니다: " + pingIntervalMs);
            }
            if (sendTimeLimitMs <= 0) {
                throw new IllegalArgumentException(
                        "crowdsight.ws.send-time-limit-ms 는 0보다 커야 합니다: " + sendTimeLimitMs);
            }
            if (bufferSizeLimitBytes <= 0) {
                throw new IllegalArgumentException(
                        "crowdsight.ws.buffer-size-limit-bytes 는 0보다 커야 합니다: " + bufferSizeLimitBytes);
            }
        }
    }
}
