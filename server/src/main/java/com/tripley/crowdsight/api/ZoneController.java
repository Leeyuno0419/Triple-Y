package com.tripley.crowdsight.api;

import java.util.List;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import com.tripley.crowdsight.replay.ZoneRegistry;

import lombok.RequiredArgsConstructor;
import tools.jackson.databind.JsonNode;

/**
 * 카메라·구역 목록과 구역 meta 조회 (api-spec 2절·5절). 화면은 목록에서 카메라를 골라 /ws/zones/{zone_id}에 접속한다.
 * 없는 구역은 404(본문 없음).
 * 스레드 규칙: Tomcat 요청 스레드에서 동시에 불린다. 상태가 없고 ZoneRegistry는 바뀌지 않는다.
 */
@RestController
@RequestMapping("/api/zones")
@RequiredArgsConstructor
public class ZoneController {

    private final ZoneRegistry zones;

    /** 카메라·구역 목록 (설정 순서). */
    @GetMapping
    public List<ZoneSummary> list() {
        return zones.all().stream().map(z -> ZoneSummary.of(z.player().timeline())).toList();
    }

    /** 타임라인 meta 원본 (hello.meta와 같다). 없는 구역은 404. */
    @GetMapping("/{zoneId}/meta")
    public ResponseEntity<JsonNode> meta(@PathVariable String zoneId) {
        return zones.find(zoneId)
                .map(z -> ResponseEntity.ok(z.player().timeline().metaJson()))
                .orElseGet(() -> ResponseEntity.notFound().build());
    }
}
