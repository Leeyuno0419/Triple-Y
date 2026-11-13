package com.tripley.crowdsight.grade;

import java.util.List;

/**
 * 구역 1개의 한 초 판정 결과. zone_state(S3)·알림(S5)의 입력이다.
 *
 * @param t           프레임 t
 * @param zoneGrade   판정 대상 셀 등급의 최댓값. 대상 셀이 없으면 NORMAL
 * @param maxDensity  판정 대상 셀 중 null이 아닌 밀도의 최댓값. 없으면 null
 * @param inflowAvg   inflow_ratio 최근 5초 평균 (InflowMonitor). 창이 덜 찼거나 값이 모자라면 null
 * @param inflowAlert 유입 경보가 켜져 있는지
 * @param cells       셀별 결과 (meta 순서)
 */
public record ZoneEvaluation(int t, Grade zoneGrade, Double maxDensity, Double inflowAvg, boolean inflowAlert,
                             List<CellEvaluation> cells) {

    public ZoneEvaluation {
        cells = List.copyOf(cells);
    }
}
