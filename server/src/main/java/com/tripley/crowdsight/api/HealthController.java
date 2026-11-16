package com.tripley.crowdsight.api;

import java.util.List;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import com.tripley.crowdsight.replay.PlaybackSnapshot;
import com.tripley.crowdsight.replay.TickStats;
import com.tripley.crowdsight.replay.ZoneRegistry;
import com.tripley.crowdsight.ws.MessageFactory;
import com.tripley.crowdsight.ws.ZoneSessions;

import lombok.RequiredArgsConstructor;

/**
 * 서버 상태 (api-spec 2절 GET /api/health). 구역별 재생 상태, WebSocket 접속 수, tick 처리 시간 last·max.
 * 스레드 규칙: Tomcat 요청 스레드에서 불린다. 상태가 없고, 읽는 대상(ZonePlayer·ZoneSessions·TickStats)이 각자 스레드 안전하다.
 */
@RestController
@RequestMapping("/api")
@RequiredArgsConstructor
public class HealthController {

    private final ZoneRegistry zones;
    private final ZoneSessions sessions;
    private final TickStats tickStats;

    /** 서버 상태. 응답하면 status는 늘 UP. */
    @GetMapping("/health")
    public HealthResponse health() {
        List<ZoneHealth> zoneHealth = zones.all().stream().map(z -> {
            PlaybackSnapshot s = z.player().snapshot();
            return new ZoneHealth(z.zoneId(), MessageFactory.stateName(s.state()), s.t(), s.loop());
        }).toList();
        return new HealthResponse(HealthResponse.UP, zoneHealth, sessions.sessionCount(), tickStats.lastMs(),
                tickStats.maxMs());
    }
}
