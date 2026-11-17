import { DENSITY_LEVELS, type DensityLevel } from '../config/density';
import type { CellMeta, Frame, Meta } from '../types/timeline';
import { cellLevel, gradeLevel } from './grade';
import { cellValue, pairCells, type ViewMode } from './model';

export interface ZoneSummary {
  meta: Meta;
  /**
   * 구역 인원(명). 현재 관측 모드에서 프레임에 count(규격 v0.2, 이유노가 5장 평균으로 센 값)가 있으면 그 값을 쓰고,
   * 없으면(v0.1 파일·실시간 등) 셀의 Σ 밀도 × 보행 가능 면적으로 계산한다. 예측 모드는 예측 인원이 파일에 없어 항상 계산한다.
   * 값이 있는 셀이 없고 count 도 없으면 null.
   */
  count: number | null;
  /** count 의 출처: 'file' = 프레임의 count, 'cells' = 셀 합 계산, null = 값 없음 */
  countSource: 'file' | 'cells' | null;
  /** 값이 있는 셀 수 (예측 모드에서 예측이 없으면 0) */
  observedCells: number;
  totalCells: number;
  /** 값이 있는 셀의 면적 가중 평균 밀도(명/m²). 없으면 null */
  meanDensity: number | null;
  maxDensity: number | null;
  maxCell: CellMeta | null;
  /**
   * 구역 위험 단계.
   * - 실시간 관측(now): 서버가 판정한 구역 등급(frame.zone.grade)을 그대로 쓴다. 이때 maxDensity·maxCell 도 서버의
   *   zone.max_density(판정 대상 셀 중 최대)에 맞춘다.
   * - 그 밖(예측 모드, 서버 등급이 없는 timeline 파일): 값이 있는 셀 중 가장 높은 단계(가장 위험한 곳 기준).
   *   셀 단계는 서버 등급이 있으면 그 값, 없으면 밀도 임계값 해석이다 (lib/grade.ts cellLevel). 값이 없으면 null.
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
  let topLevelIndex = -1; // 값이 있는 셀 중 가장 높은 단계 (DENSITY_LEVELS 인덱스)

  for (const { meta: cm, state } of pairCells(meta, frame)) {
    if (state.pressure !== null && Number.isFinite(state.pressure) && (maxPressure === null || state.pressure > maxPressure)) {
      maxPressure = state.pressure;
    }
    const value = cellValue(state, mode);
    if (value === null) continue;
    observedCells += 1;
    people += value * cm.walkable_area_m2;
    area += cm.walkable_area_m2;
    const lv = cellLevel(state, mode, value);
    if (lv) {
      const li = DENSITY_LEVELS.indexOf(lv);
      levelCounts[li] += 1;
      topLevelIndex = Math.max(topLevelIndex, li);
    }
    if (maxDensity === null || value > maxDensity) {
      maxDensity = value;
      maxCell = cm;
    }
  }

  let level: DensityLevel | null = topLevelIndex >= 0 ? DENSITY_LEVELS[topLevelIndex] : null;
  // 서버가 구역 요약(zone)을 보냈으면 그대로 쓴다: 구역 등급, 판정 대상 셀 중 최대 밀도와 그 셀.
  if (mode === 'now' && frame?.zone) {
    level = gradeLevel(frame.zone.grade);
    maxDensity = frame.zone.max_density;
    const target = maxDensity;
    maxCell = target === null ? null : (pairCells(meta, frame).find((p) => p.state.density === target)?.meta ?? null);
  }

  // 파일의 구역 인원은 현재 관측에만 있다. 예측 모드는 셀 합으로 계산한다.
  const fileCount = mode === 'now' && frame?.count != null && Number.isFinite(frame.count) ? frame.count : null;
  const count = fileCount ?? (observedCells > 0 ? people : null);

  return {
    meta,
    count,
    countSource: fileCount !== null ? 'file' : count !== null ? 'cells' : null,
    observedCells,
    totalCells: meta.cells.length,
    meanDensity: observedCells > 0 && area > 0 ? people / area : null,
    maxDensity,
    maxCell,
    level,
    levelCounts,
    inflowRatio: frame?.inflow_ratio ?? null,
    maxPressure,
  };
}
