import { DENSITY_LEVELS, RISK_MIN_LEVEL_INDEX, type DensityLevel } from '../config/density';
import type { CellMeta, CellState, Frame, Meta } from '../types/timeline';
import { levelOf } from './density';
import { cellValue, frameMaxDensity, pairCells, type ViewMode } from './model';
import { summarizeFrame, type ZoneSummary } from './region';

export interface HotCell {
  meta: CellMeta;
  state: CellState;
  value: number;
  level: DensityLevel;
}

export interface Dashboard {
  summary: ZoneSummary;
  /** 경고(RISK_MIN_LEVEL_INDEX) 이상인 셀 수 */
  riskCells: number;
  /** 심각 셀 수 */
  severeCells: number;
  hotCells: HotCell[];
}

const HOT_CELL_LIMIT = 5;

/** 한 프레임에서 밀도가 높은 셀 상위 limit 개. level 을 주면 그 단계의 셀만 대상으로 한다. */
export function hotCellsFor(
  meta: Meta,
  frame: Frame | undefined,
  mode: ViewMode = 'now',
  level: DensityLevel | null = null,
  limit = HOT_CELL_LIMIT,
): HotCell[] {
  const hot: HotCell[] = [];
  for (const { meta: cm, state } of pairCells(meta, frame)) {
    const value = cellValue(state, mode);
    if (value === null) continue;
    const lv = levelOf(value);
    if (level && lv !== level) continue;
    hot.push({ meta: cm, state, value, level: lv });
  }
  hot.sort((a, b) => b.value - a.value);
  return hot.slice(0, limit);
}

/** 한 프레임을 대시보드 지표로 요약한다. */
export function buildDashboard(meta: Meta, frame: Frame | undefined, mode: ViewMode = 'now'): Dashboard {
  const summary = summarizeFrame(meta, frame, mode);
  const risk = summary.levelCounts.slice(RISK_MIN_LEVEL_INDEX).reduce((a, b) => a + b, 0);
  return {
    summary,
    riskCells: risk,
    severeCells: summary.levelCounts[DENSITY_LEVELS.length - 1] ?? 0,
    hotCells: hotCellsFor(meta, frame, mode),
  };
}

/** 프레임마다 구역의 최대 밀도 (추이 그래프용). 값이 없으면 0. */
export function peakSeries(frames: Frame[], mode: ViewMode = 'now'): number[] {
  return frames.map((f) => frameMaxDensity(f, mode) ?? 0);
}

/**
 * 60초 뒤 예측의 최대 밀도를 "예측 대상 시각" 기준으로 배치한 시계열. 길이 = frames.length + horizonS.
 * 프레임 i 의 예측(i 시점 기준 horizonS 초 뒤)은 인덱스 i + horizonS 에 놓인다. 그래서 frames.length 이전 구간에서는
 * 예측과 실제 관측을 겹쳐 비교할 수 있고, 그 뒤 horizonS 개는 아직 오지 않은 미래의 예측이다. 예측이 없으면 null.
 */
export function predictedPeakSeries(frames: Frame[], horizonS: number): Array<number | null> {
  const out: Array<number | null> = Array.from({ length: frames.length + horizonS }, () => null);
  frames.forEach((f, i) => {
    out[i + horizonS] = frameMaxDensity(f, 'pred');
  });
  return out;
}

/** 아직 오지 않은 미래(마지막 프레임 이후 horizonS 초)의 예측 최대 밀도. 하나라도 비면(프레임이 horizonS 개 미만) 빈 배열. */
export function futurePeaks(frames: Frame[], horizonS: number): number[] {
  const future = predictedPeakSeries(frames, horizonS).slice(frames.length);
  return future.every((v): v is number => v !== null) ? (future as number[]) : [];
}

/** 프레임별 요약 (분석 뷰의 추이 그래프/기록 표용). frames 와 같은 순서. */
export function zoneSeries(meta: Meta, frames: Frame[], mode: ViewMode = 'now'): ZoneSummary[] {
  return frames.map((f) => summarizeFrame(meta, f, mode));
}
