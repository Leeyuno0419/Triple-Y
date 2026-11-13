package com.tripley.crowdsight.grade;

import java.util.Arrays;
import java.util.Objects;

/**
 * 구역 유입 경보 (api-spec 4.4, 결정 6, 결정 기록 8).
 * 평균: 생성·reset 뒤 관측이 windowSeconds개 쌓이기 전에는 null (창이 다 찬 뒤에만 계산).
 *       그 뒤 최근 windowSeconds초(이번 초 포함) 중 null이 아닌 값이 minSamples개 이상이면 그 평균, 아니면 null.
 *       inflow_ratio null인 초도 창 한 칸을 차지한다.
 * 조건: 평균 != null && 평균 > ratio && count != null && count >= minCount.
 * 켬: 조건이 참인 초. 끔: 켜진 뒤 조건이 offSeconds초 연속 거짓 (평균 null·count 부족·count null인 초도 거짓).
 * 스레드 규칙: 재생 스레드 하나만 부른다. 잠금 없음.
 */
public final class InflowMonitor {

    private final InflowSettings settings;
    private final Double[] window;   // 원형 버퍼. null = 그 초 관측 없음 (ArrayDeque는 null을 못 넣는다)
    private int next;                // 다음에 쓸 칸
    private int observed;            // 생성·reset 뒤 관측 수. 창 크기에서 멈춘다
    private boolean on;
    private int falseStreak;         // 켜진 뒤 조건이 거짓인 연속 초

    /** @param settings 유입 경보 설정 (값 검사는 InflowSettings가 한다) */
    public InflowMonitor(InflowSettings settings) {
        this.settings = Objects.requireNonNull(settings, "settings");
        this.window = new Double[settings.windowSeconds()];
    }

    /** 이번 초 값을 창에 넣고 평균·경보 상태를 돌려준다. */
    public InflowStatus update(Double inflowRatio, Double count) {
        window[next] = inflowRatio;
        next = (next + 1) % window.length;
        if (observed < window.length) {
            observed++;
        }
        Double average = average();
        boolean condition = average != null && average > settings.ratio()
                && count != null && count >= settings.minCount();
        if (condition) {
            on = true;
            falseStreak = 0;
        } else if (on && ++falseStreak >= settings.offSeconds()) {
            on = false;
            falseStreak = 0;
        }
        return new InflowStatus(average, on);
    }

    /** 창·연속·경보를 모두 비운다 (반복·이동). */
    public void reset() {
        Arrays.fill(window, null);
        next = 0;
        observed = 0;
        on = false;
        falseStreak = 0;
    }

    private Double average() {
        if (observed < window.length) {
            return null;
        }
        double sum = 0;
        int n = 0;
        for (Double v : window) {
            if (v != null) {
                sum += v;
                n++;
            }
        }
        return n >= settings.minSamples() ? sum / n : null;
    }
}
