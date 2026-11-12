package com.tripley.crowdsight.timeline;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import org.springframework.stereotype.Component;

import com.tripley.crowdsight.config.CrowdsightProperties;

import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import tools.jackson.core.JacksonException;
import tools.jackson.core.type.TypeReference;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.json.JsonMapper;

/**
 * 설정한 타임라인 파일을 읽고 검증해 record로 바꾼다. 하나라도 틀리면 예외를 던져 서버 시작을 멈춘다.
 * 상태가 없어 여러 스레드에서 불러도 된다 (서버 시작 때 한 번 쓴다).
 */
@Slf4j
@Component
@RequiredArgsConstructor
public class TimelineLoader {

    private static final TypeReference<List<Frame>> FRAME_LIST = new TypeReference<>() {
    };

    private final JsonMapper jsonMapper;
    private final CrowdsightProperties props;

    /** timeline-dir 안의 timeline-files를 설정 순서대로 읽는다. 같은 zone_id가 두 번 나오면 예외. */
    public List<ZoneTimeline> loadAll() {
        Path dir = Path.of(props.timelineDir()).toAbsolutePath().normalize();
        log.info("타임라인 폴더: {} (crowdsight.timeline-dir={})", dir, props.timelineDir());
        Map<String, ZoneTimeline> byZone = new LinkedHashMap<>();
        for (String name : props.timelineFiles()) {
            ZoneTimeline timeline = load(dir.resolve(name));
            ZoneTimeline previous = byZone.putIfAbsent(timeline.zoneId(), timeline);
            if (previous != null) {
                throw new InvalidTimelineException(timeline.source(),
                        "zone_id 중복: " + timeline.zoneId() + " (먼저 읽은 파일 " + previous.source() + ")");
            }
            log.info("타임라인 읽음 zone={} 길이={}초 셀={}개 버전={} 파일={}", timeline.zoneId(),
                    timeline.durationS(), timeline.meta().cells().size(), timeline.schemaVersion(), timeline.source());
        }
        return List.copyOf(byZone.values());
    }

    /** 파일 하나: 존재 확인 → readTree → 검증 → record. */
    ZoneTimeline load(Path file) {
        Path abs = file.toAbsolutePath().normalize();
        if (!Files.isRegularFile(abs)) {
            throw new InvalidTimelineException(abs, "파일이 없습니다. crowdsight.timeline-dir·timeline-files 설정과 "
                    + "작업 폴더(" + Path.of("").toAbsolutePath() + ")를 확인하세요.");
        }
        JsonNode root;
        try {
            root = jsonMapper.readTree(abs);
        } catch (JacksonException e) {
            throw new InvalidTimelineException(abs, "JSON을 읽을 수 없습니다: " + e.getOriginalMessage(), e);
        }
        return fromTree(root, abs);
    }

    /** 이미 읽은 트리를 검증해 record로 바꾼다. 테스트는 고친 트리로 이것을 부른다. */
    ZoneTimeline fromTree(JsonNode root, Path source) {
        TimelineValidator.validate(root, source);
        try {
            Meta meta = jsonMapper.treeToValue(root.get("meta"), Meta.class);
            List<Frame> frames = jsonMapper.treeToValue(root.get("frames"), FRAME_LIST);
            return new ZoneTimeline(root.get("schema_version").asString(), meta, frames, root.get("meta"), source);
        } catch (JacksonException e) {
            throw new InvalidTimelineException(source, "record 변환 실패: " + e.getOriginalMessage(), e);
        }
    }
}
