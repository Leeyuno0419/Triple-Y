package com.tripley.crowdsight.alert;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

import org.springframework.stereotype.Component;

import com.tripley.crowdsight.config.CrowdsightProperties;

import lombok.extern.slf4j.Slf4j;
import tools.jackson.databind.json.JsonMapper;

/**
 * 알림 확인 기록을 crowdsight.alert-log 파일에 JSON 한 줄씩 덧붙인다 (api-spec 4.5, JSON Lines, UTF-8, LF).
 * 파일과 부모 폴더는 처음 쓸 때 만든다. 쓸 때마다 열고 닫아 파일을 잡고 있지 않는다.
 * 쓰기에 실패하면 예외를 내지 않고 ERROR 로그에 쓰려던 줄을 남긴다 (확인 자체는 이미 반영됨).
 * 스레드 규칙: Tomcat 요청 스레드가 부른다. append는 this로 잠가 줄이 섞이지 않는다. 재생 스레드는 부르지 않는다.
 */
@Slf4j
@Component
public final class AlertLogWriter {

    private final Path path;
    private final JsonMapper jsonMapper;

    public AlertLogWriter(CrowdsightProperties props, JsonMapper jsonMapper) {
        this.path = Path.of(props.alertLog()).toAbsolutePath().normalize();
        this.jsonMapper = jsonMapper;
        log.info("알림 확인 기록 파일 path={}", path);
    }

    /** 확인 한 건을 한 줄로 덧붙인다. 처음 확인(AlertAck.firstAck)일 때만 부른다. */
    public synchronized void append(AlertAck ack) {
        String line = jsonMapper.writeValueAsString(AlertLogLine.of(ack));
        try {
            Path parent = path.getParent();
            if (parent != null) {
                Files.createDirectories(parent);
            }
            Files.writeString(path, line + "\n", StandardCharsets.UTF_8, StandardOpenOption.CREATE,
                    StandardOpenOption.APPEND);
        } catch (IOException e) {
            log.error("알림 확인 기록을 쓰지 못함 path={} alert_id={} 줄={}", path, ack.alert().alertId(), line, e);
        }
    }
}
