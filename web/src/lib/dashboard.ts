import { DENSITY_LEVELS, RISK_MIN_LEVEL_INDEX, type DensityLevel } from '../config/density';
import type { Frame, ZoneMeta } from '../types/timeline';
import { levelOf } from './density';
import { summarizeZone, type RegionSummary } from './region';

export interface HotCell {
  zone_id: string;
  zoneName: string;
  row: number;
  col: number;
  value: number;
  level: DensityLevel;
}

export interface Dashboard {
  /** 최대 밀도 내림차순 (미관측 구역은 뒤) */
  zones: RegionSummary[];
  /** 경고 이상(RISK_MIN_LEVEL_INDEX) 구역 수 */
  riskZones: number;
  /** 심각 구역 수 */
  severeZones: number;
  peak: { density: number; zone: ZoneMeta; row: number; col: number; level: DensityLevel } | null;
  /** 전 구역 인원 합(명). 집계값이 하나도 없으면 null */
  totalCount: number | null;
  observedCells: number;
  totalCells: number;
  /** DENSITY_LEVELS 순서대로 해당 단계인 구역 수 */
  zonesPerLevel: number[];
  /** 관측 셀이 없는 구역 수 */
  unobservedZones: number;
  hotCells: HotCell[];
}

const HOT_CELL_LIMIT = 5;

/** 한 프레임의 전체 구역을 대시보드 지표로 요약한다. */
export function buildDashboard(zones: ZoneMeta[], frame: Frame | undefined): Dashboard {
  const summaries = zones.map((z) => summarizeZone(z, frame?.zones.find((f) => f.zone_id === z.zone_id)));
  summaries.sort((a, b) => (b.maxDensity ?? -1) - (a.maxDensity ?? -1));

  const zonesPerLevel = DENSITY_LEVELS.map(() => 0);
  let unobservedZones = 0;
  let totalCount: number | null = null;
  let observedCells = 0;
  let totalCells = 0;
  let peak: Dashboard['peak'] = null;

  for (const s of summaries) {
    if (s.level) zonesPerLevel[DENSITY_LEVELS.indexOf(s.level)] += 1;
    else unobservedZones += 1;
    if (s.count !== null) totalCount = (totalCount ?? 0) + s.count;
    observedCells += s.observedCells;
    totalCells += s.totalCells;
    if (s.maxDensity !== null && s.maxCell && (!peak || s.maxDensity > peak.density)) {
      peak = { density: s.maxDensity, zone: s.zone, ...s.maxCell, level: levelOf(s.maxDensity) };
    }
  }

  const hot: HotCell[] = [];
  const nameOf = new Map(zones.map((z) => [z.zone_id, z.name]));
  frame?.zones.forEach((zf) =>
    zf.density.forEach((rowVals, row) =>
      rowVals.forEach((value, col) => {
        if (value === null || !Number.isFinite(value)) return;
        hot.push({ zone_id: zf.zone_id, zoneName: nameOf.get(zf.zone_id) ?? zf.zone_id, row, col, value, level: levelOf(value) });
      }),
    ),
  );
  hot.sort((a, b) => b.value - a.value);

  const riskLevels = DENSITY_LEVELS.slice(RISK_MIN_LEVEL_INDEX);
  return {
    zones: summaries,
    riskZones: summaries.filter((s) => s.level && riskLevels.includes(s.level)).length,
    severeZones: summaries.filter((s) => s.level === DENSITY_LEVELS[DENSITY_LEVELS.length - 1]).length,
    peak,
    totalCount,
    observedCells,
    totalCells,
    zonesPerLevel,
    unobservedZones,
    hotCells: hot.slice(0, HOT_CELL_LIMIT),
  };
}

/** 프레임마다 전체 구역의 최대 밀도 (추이 그래프용). 관측 셀이 없으면 0. */
export function peakSeries(frames: Frame[]): number[] {
  return frames.map((f) => {
    let max = 0;
    for (const zf of f.zones) for (const r of zf.density) for (const v of r) if (v !== null && v > max) max = v;
    return max;
  });
}

/** 한 구역의 프레임별 요약 (분석 뷰의 추이 그래프/기록 표용). frames 와 같은 순서. */
export function zoneSeries(zone: ZoneMeta, frames: Frame[]): RegionSummary[] {
  return frames.map((f) => summarizeZone(zone, f.zones.find((z) => z.zone_id === zone.zone_id)));
}
