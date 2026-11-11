import { DENSITY_LEVELS, type DensityLevel } from '../config/density';
import type { ZoneFrame, ZoneMeta } from '../types/timeline';
import { levelOf } from './density';

export interface RegionSummary {
  zone: ZoneMeta;
  /** 구역 집계 인원(명). 값이 없으면 null */
  count: number | null;
  observedCells: number;
  totalCells: number;
  /** 관측된 셀의 평균 밀도(명/m²). 관측 셀이 없으면 null */
  meanDensity: number | null;
  maxDensity: number | null;
  maxCell: { row: number; col: number } | null;
  /**
   * 구역 위험 단계 = 관측된 셀 중 가장 높은 밀도의 단계 (가장 위험한 곳 기준).
   * 평균 기준으로 바꾸려면 여기서 meanDensity 로 계산하면 된다. 관측 셀이 없으면 null.
   */
  level: DensityLevel | null;
  /** DENSITY_LEVELS 순서대로 각 단계에 속한 관측 셀 수 */
  levelCounts: number[];
}

/** 한 프레임의 구역 데이터(zf)를 상세 패널용 요약으로 만든다. zf 가 없으면 전부 "미관측". */
export function summarizeZone(zone: ZoneMeta, zf: ZoneFrame | undefined): RegionSummary {
  const levelCounts = DENSITY_LEVELS.map(() => 0);
  let observedCells = 0;
  let sum = 0;
  let maxDensity: number | null = null;
  let maxCell: RegionSummary['maxCell'] = null;

  zf?.density.forEach((rowVals, row) =>
    rowVals.forEach((value, col) => {
      if (value === null || !Number.isFinite(value)) return; // null = 화각 밖
      observedCells += 1;
      sum += value;
      levelCounts[DENSITY_LEVELS.indexOf(levelOf(value))] += 1;
      if (maxDensity === null || value > maxDensity) {
        maxDensity = value;
        maxCell = { row, col };
      }
    }),
  );

  return {
    zone,
    count: zf?.count ?? null,
    observedCells,
    totalCells: zone.rows * zone.cols,
    meanDensity: observedCells > 0 ? sum / observedCells : null,
    maxDensity,
    maxCell,
    level: maxDensity === null ? null : levelOf(maxDensity),
    levelCounts,
  };
}
