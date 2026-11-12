package com.tripley.crowdsight.timeline;

import java.nio.file.Path;

/** 타임라인 파일이 없거나 규격에 맞지 않을 때. 서버 시작을 멈춘다. 메시지에 파일 절대 경로가 들어간다. */
public final class InvalidTimelineException extends RuntimeException {

    private final Path file;

    public InvalidTimelineException(Path file, String reason) {
        this(file, reason, null);
    }

    public InvalidTimelineException(Path file, String reason, Throwable cause) {
        super("타임라인 파일 오류 [" + file + "]: " + reason, cause);
        this.file = file;
    }

    /** 문제가 된 파일의 절대 경로. */
    public Path file() {
        return file;
    }
}
