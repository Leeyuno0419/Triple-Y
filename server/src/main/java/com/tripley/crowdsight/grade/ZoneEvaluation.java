package com.tripley.crowdsight.grade;

import java.util.List;

/**
 * 구역 1개의 한 초 판정 결과. zone_state(S3)·알림(S5)의 입력이다.
 * 불안정·유입 성분은 S4에서 더한다.
 *
 * @param t          프레임 t
 * @param zoneGrade  판정 대상 셀 등급의 최댓값. 대상 셀이 없으면 NORMAL
 * @param maxDensity 판정 대상 셀 중 null이 아닌 밀도의 최댓값. 없으면 null
 * @param cells      셀별 결과 (meta 순서)
 */
public record ZoneEvaluation(int t, Grade zoneGrade, Double maxDensity, List<CellEvaluation> cells) {

    public ZoneEvaluation {
        cells = List.copyOf(cells);
    }
}
