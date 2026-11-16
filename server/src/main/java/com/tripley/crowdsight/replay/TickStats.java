package com.tripley.crowdsight.replay;

import org.springframework.stereotype.Component;

/**
 * 재생 tick 1번(모든 구역 판정 + 방송) 처리 시간의 마지막 값과 최댓값 (/api/health, api-spec 7절 E8 참고).
 * 시간은 System.nanoTime() 차이로 잰 경과 시간이다 (벽시계 아님, CLAUDE.md).
 * 스레드 규칙: record는 재생 스레드 하나만 부른다. lastMs·maxMs는 요청 스레드가 읽는다.
 * 쓰는 스레드가 하나라 volatile로 충분하다 (last와 max가 같은 tick 값일 필요는 없다).
 * 다만 last를 읽은 뒤 max를 읽으면 max ≥ last가 지켜진다 (쓰는 순서: max 먼저, last 나중).
 */
@Component
public final class TickStats {

    private volatile long lastNanos = -1;     // -1: 아직 tick 없음
    private volatile long maxNanos = -1;

    /** tick 1번의 처리 시간(나노초)을 기록한다. */
    public void record(long elapsedNanos) {
        if (elapsedNanos < 0) {
            throw new IllegalArgumentException("처리 시간은 0 이상이어야 합니다: " + elapsedNanos);
        }
        if (elapsedNanos > maxNanos) {
            maxNanos = elapsedNanos;
        }
        lastNanos = elapsedNanos;
    }

    /** 마지막 tick 처리 시간(ms, 소수 3자리). tick 전이면 null. */
    public Double lastMs() {
        return toMs(lastNanos);
    }

    /** 서버 시작부터 가장 긴 tick 처리 시간(ms, 소수 3자리). tick 전이면 null. */
    public Double maxMs() {
        return toMs(maxNanos);
    }

    private static Double toMs(long nanos) {
        return nanos < 0 ? null : Math.round(nanos / 1_000.0) / 1_000.0;
    }
}
