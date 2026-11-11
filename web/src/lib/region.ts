import { DENSITY_LEVELS, type DensityLevel } from '../config/density';
import type { CellMeta, Frame, Meta } from '../types/timeline';
import { levelOf } from './density';
import { cellValue, pairCells, type ViewMode } from './model';

export interface ZoneSummary {
  meta: Meta;
  /** 추정 인원(명) = Σ 밀도 × 보행 가능 면적. 값이 있는 셀이 없으면 null */
  count: number | null;
  /** 값이 있는 셀 수 (예측 모드에서 예측이 없으면 0) */
  observedCells: number;
  totalCells: number;
  /** 값이 있는 셀의 면적 가중 평균 밀도(명/m²). 없으면 null */
  meanDensity: number | null;
  maxDensity: number | null;
  maxCell: CellMeta | null;
  /**
   * 구역 위험 단계 = 값이 있는 셀 중 가장 높은 밀도의 단계 (가장 위험한 곳 기준).
   * !! 서버가 판정하는 공식 등급이 아니라 클라이언트 임계값 해석이다 (docs/server-alignment.md Q3). 값이 없으면 null.
   */
  level: DensityLevel | null;
  /** DENSITY_LEVELS 순서대로 각 단계에 속한 셀 수 */
  levelCounts: number[];
  /** 프레임의 경계 유입 비율(0~1). 구역 전체 값 */
  inflowRatio: number | null;
  /** 셀 중 가장 큰 불안정 지표 P (1/s²). 값이 없으면 null */
  maxPressure: number | null;
}

/** 한 프레임을 요약한다. frame 이 없으면 전부 "값 없음". */
export function summarizeFrame(meta: Meta, frame: Frame | undefined, mode: ViewMode = 'now'): ZoneSummary {
  const levelCounts = DENSITY_LEVELS.map(() => 0);
  let observedCells = 0;
  let people = 0;
  let area = 0;
  let maxDensity: number | null = null;
  let maxCell: CellMeta | null = null;
  let maxPressure: number | null = null;

  for (const { meta: cm, state } of pairCells(meta, frame)) {
    if (state.pressure !== null && Number.isFinite(state.pressure) && (maxPressure === null || state.pressure > maxPressure)) {
      maxPressure = state.pressure;
    }
    const value = cellValue(state, mode);
    if (value === null) continue;
    observedCells += 1;
    people += value * cm.walkable_area_m2;
    area += cm.walkable_area_m2;
    levelCounts[DENSITY_LEVELS.indexOf(levelOf(value))] += 1;
    if (maxDensity === null || value > maxDensity) {
      maxDensity = value;
      maxCell = cm;
    }
  }

  return {
    meta,
    count: observedCells > 0 ? people : null,
    observedCells,
    totalCells: meta.cells.length,
    meanDensity: observedCells > 0 && area > 0 ? people / area : null,
    maxDensity,
    maxCell,
    level: maxDensity === null ? null : levelOf(maxDensity),
    levelCounts,
    inflowRatio: frame?.inflow_ratio ?? null,
    maxPressure,
  };
}
