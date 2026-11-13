package com.tripley.crowdsight.grade;

import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

import com.tripley.crowdsight.timeline.CellMeta;
import com.tripley.crowdsight.timeline.CellState;
import com.tripley.crowdsight.timeline.Frame;

/**
 * 구역 1개의 셀 등급·구역 등급·유입 경보 판정 (api-spec 4.1~4.4).
 * 셀마다 GradeHysteresis·InstabilityTracker를, 구역에 InflowMonitor 1개를 가진다.
 * 셀 관측 등급 = 불안정이면 CRITICAL, 아니면 밀도 등급. 여기에 히스테리시스를 적용한다.
 * 스레드 규칙: evaluate·reset은 재생 스레드 하나만 부른다. 잠금 없음.
 */
public final class ZoneGrader {

    private final List<String> cellIds;
    private final boolean[] eligible;
    private final GradeHysteresis[] hysteresis;
    private final InstabilityTracker[] trackers;
    private final InflowMonitor inflow;
    private final DensityThresholds thresholds;
    private final int eligibleCount;

    /**
     * @param cells       meta.cells (frame.cells와 같은 순서)
     * @param grade       등급 설정
     * @param instability 불안정 설정
     * @param inflow      유입 경보 설정
     */
    public ZoneGrader(List<CellMeta> cells, GradeSettings grade, InstabilitySettings instability,
                      InflowSettings inflow) {
        Objects.requireNonNull(cells, "cells");
        Objects.requireNonNull(grade, "grade");
        Objects.requireNonNull(instability, "instability");
        int n = cells.size();
        this.cellIds = cells.stream().map(CellMeta::cellId).toList();
        this.eligible = new boolean[n];
        this.hysteresis = new GradeHysteresis[n];
        this.trackers = new InstabilityTracker[n];
        int count = 0;
        for (int i = 0; i < n; i++) {
            eligible[i] = cells.get(i).walkableAreaM2() >= grade.minWalkableAreaM2();
            hysteresis[i] = new GradeHysteresis(grade.upSeconds(), grade.downSeconds());
            trackers[i] = new InstabilityTracker(instability);
            if (eligible[i]) {
                count++;
            }
        }
        this.eligibleCount = count;
        this.thresholds = grade.density();
        this.inflow = new InflowMonitor(inflow);   // null이면 InflowMonitor가 NPE
    }

    /** 판정 대상 셀 수 (등록 로그용). */
    public int eligibleCount() {
        return eligibleCount;
    }

    /**
     * 한 프레임을 판정한다. 셀 수·순서가 meta와 다르면 상태를 바꾸지 않고 IllegalArgumentException을 던진다.
     */
    public ZoneEvaluation evaluate(Frame frame) {
        List<CellState> states = frame.cells();
        requireSameCells(frame.t(), states);
        List<CellEvaluation> cells = new ArrayList<>(states.size());
        Grade zoneGrade = Grade.NORMAL;
        Double maxDensity = null;
        for (int i = 0; i < states.size(); i++) {
            CellState state = states.get(i);
            Double density = state.density();
            boolean unstable = trackers[i].update(state.pressure());
            Grade grade = hysteresis[i].update(observedGrade(density, unstable));
            if (eligible[i]) {
                zoneGrade = Grade.max(zoneGrade, grade);
                if (density != null && (maxDensity == null || density > maxDensity)) {
                    maxDensity = density;
                }
            }
            Grade predicted = GradeRule.ofPrediction(state.densityPred60s(), thresholds);
            cells.add(new CellEvaluation(state.cellId(), grade, predicted, eligible[i], unstable, state));
        }
        InflowStatus status = inflow.update(frame.inflowRatio(), frame.count());
        return new ZoneEvaluation(frame.t(), zoneGrade, maxDensity, status.average(), status.on(), cells);
    }

    /** 모든 셀을 NORMAL로, 불안정 연속·유입 창·경보를 처음으로 되돌린다 (첫 프레임·반복·이동). */
    public void reset() {
        for (GradeHysteresis h : hysteresis) {
            h.reset();
        }
        for (InstabilityTracker tracker : trackers) {
            tracker.reset();
        }
        inflow.reset();
    }

    /** 셀 관측 등급. 불안정이면 CRITICAL, 아니면 밀도 등급. 밀도 null이면 null(그 초는 건너뜀, 결정 기록 4). */
    private Grade observedGrade(Double density, boolean unstable) {
        if (unstable) {
            return Grade.CRITICAL;
        }
        return density == null ? null : GradeRule.ofDensity(density, thresholds);
    }

    private void requireSameCells(int t, List<CellState> states) {
        if (states.size() != cellIds.size()) {
            throw new IllegalArgumentException("t=" + t + ": 셀 수가 meta와 다릅니다: "
                    + states.size() + " != " + cellIds.size());
        }
        for (int i = 0; i < states.size(); i++) {
            if (!cellIds.get(i).equals(states.get(i).cellId())) {
                throw new IllegalArgumentException("t=" + t + ": " + i + "번째 셀이 meta와 다릅니다: "
                        + states.get(i).cellId() + " != " + cellIds.get(i));
            }
        }
    }
}
