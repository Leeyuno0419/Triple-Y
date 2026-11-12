package com.tripley.crowdsight.grade;

import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

import com.tripley.crowdsight.timeline.CellMeta;
import com.tripley.crowdsight.timeline.CellState;
import com.tripley.crowdsight.timeline.Frame;

/**
 * 구역 1개의 셀 등급·구역 등급 판정 (api-spec 4.1~4.2). 셀마다 GradeHysteresis를 가진다.
 * 스레드 규칙: evaluate·reset은 재생 스레드 하나만 부른다. 잠금 없음.
 */
public final class ZoneGrader {

    private final List<String> cellIds;
    private final boolean[] eligible;
    private final GradeHysteresis[] hysteresis;
    private final DensityThresholds thresholds;
    private final int eligibleCount;

    /**
     * @param cells    meta.cells (frame.cells와 같은 순서)
     * @param settings 등급 설정
     */
    public ZoneGrader(List<CellMeta> cells, GradeSettings settings) {
        Objects.requireNonNull(cells, "cells");
        Objects.requireNonNull(settings, "settings");
        int n = cells.size();
        this.cellIds = cells.stream().map(CellMeta::cellId).toList();
        this.eligible = new boolean[n];
        this.hysteresis = new GradeHysteresis[n];
        int count = 0;
        for (int i = 0; i < n; i++) {
            eligible[i] = cells.get(i).walkableAreaM2() >= settings.minWalkableAreaM2();
            hysteresis[i] = new GradeHysteresis(settings.upSeconds(), settings.downSeconds());
            if (eligible[i]) {
                count++;
            }
        }
        this.eligibleCount = count;
        this.thresholds = settings.density();
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
            Grade observed = density == null ? null : GradeRule.ofDensity(density, thresholds);
            Grade grade = hysteresis[i].update(observed);
            if (eligible[i]) {
                zoneGrade = Grade.max(zoneGrade, grade);
                if (density != null && (maxDensity == null || density > maxDensity)) {
                    maxDensity = density;
                }
            }
            Grade predicted = GradeRule.ofPrediction(state.densityPred60s(), thresholds);
            cells.add(new CellEvaluation(state.cellId(), grade, predicted, eligible[i], state));
        }
        return new ZoneEvaluation(frame.t(), zoneGrade, maxDensity, cells);
    }

    /** 모든 셀을 NORMAL로 되돌리고 기록을 비운다 (첫 프레임·반복·이동). */
    public void reset() {
        for (GradeHysteresis h : hysteresis) {
            h.reset();
        }
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
