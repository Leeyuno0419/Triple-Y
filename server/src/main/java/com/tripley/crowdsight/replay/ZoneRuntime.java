package com.tripley.crowdsight.replay;

import java.util.Objects;
import java.util.Optional;

import com.tripley.crowdsight.alert.AlertDetector;
import com.tripley.crowdsight.grade.ZoneEvaluation;
import com.tripley.crowdsight.grade.ZoneGrader;

/**
 * 구역 1개의 재생기·판정기·알림 판정기를 묶는다. 불연속 tick(첫 프레임·반복·이동)이면 판정·알림 상태를 먼저 초기화한다.
 * 스레드 규칙: tick()은 재생 스레드만 부른다 (ZoneGrader·AlertDetector는 잠금 없음).
 * player()가 주는 ZonePlayer는 synchronized라 다른 스레드(S3 hello, S7 제어)에서 써도 된다.
 */
public final class ZoneRuntime {

    private final ZonePlayer player;
    private final ZoneGrader grader;
    private final AlertDetector alerts = new AlertDetector();   // 설정이 없어 주입하지 않는다

    public ZoneRuntime(ZonePlayer player, ZoneGrader grader) {
        this.player = Objects.requireNonNull(player, "player");
        this.grader = Objects.requireNonNull(grader, "grader");
    }

    /** 구역 ID. */
    public String zoneId() {
        return player.zoneId();
    }

    /** 재생기 (상태 조회·변화 확인용). */
    public ZonePlayer player() {
        return player;
    }

    /** 한 칸 재생하고 판정한다. 재생할 프레임이 없으면(PAUSED·ENDED) 빈 값. */
    public Optional<ZoneStep> tick() {
        return player.tick().map(this::evaluate);
    }

    private ZoneStep evaluate(Tick tick) {
        if (tick.discontinuity()) {
            grader.reset();
            alerts.reset();
        }
        ZoneEvaluation evaluation = grader.evaluate(tick.frame());
        return new ZoneStep(tick, evaluation, alerts.detect(evaluation));
    }
}
