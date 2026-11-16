package com.tripley.crowdsight.api;

import java.util.List;

/**
 * GET /api/health 응답.
 *
 * @param status     늘 "UP" (응답하면 살아 있다)
 * @param zones      구역별 재생 상태 (설정 순서)
 * @param sessions   모든 구역 WebSocket 접속 수
 * @param lastTickMs 마지막 tick 처리 시간(ms). tick 전이면 null
 * @param maxTickMs  서버 시작부터 가장 긴 tick 처리 시간(ms). tick 전이면 null
 */
public record HealthResponse(String status, List<ZoneHealth> zones, int sessions, Double lastTickMs,
                             Double maxTickMs) {

    public static final String UP = "UP";

    public HealthResponse {
        zones = List.copyOf(zones);
    }
}
