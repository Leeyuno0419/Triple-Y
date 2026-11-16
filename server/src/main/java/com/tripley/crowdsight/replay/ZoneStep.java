package com.tripley.crowdsight.replay;

import java.util.List;

import com.tripley.crowdsight.alert.AlertEvent;
import com.tripley.crowdsight.grade.ZoneEvaluation;

/**
 * 구역 1개의 tick 한 번 결과.
 *
 * @param tick       재생 결과. S3가 wrapped(→ playback)와 통과 필드(inflow_ratio·count)에 쓴다
 * @param evaluation 이번 프레임 판정
 * @param alerts     이번 초에 새로 생긴 알림 사건 (INSTABILITY → GRADE_UP → INFLOW). ID·frame_ts는 보낼 때 붙인다
 */
public record ZoneStep(Tick tick, ZoneEvaluation evaluation, List<AlertEvent> alerts) {

    public ZoneStep {
        alerts = List.copyOf(alerts);
    }
}
