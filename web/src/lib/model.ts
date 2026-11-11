import type { CellMeta, CellState, Frame, Meta } from '../types/timeline';

/**
 * 화면이 보여 주는 값.
 * - 'now'  : 그 시각의 관측 밀도 (density)
 * - 'pred' : 그 시각 기준 60초 뒤 예측 밀도 (density_pred_60s)
 */
export type ViewMode = 'now' | 'pred';

/** 셀 상태에서 모드에 맞는 밀도(명/m²)를 꺼낸다. 값이 없으면 null. */
export function cellValue(state: CellState, mode: ViewMode): number | null {
  const v = mode === 'pred' ? state.density_pred_60s : state.density;
  return v === null || v === undefined || !Number.isFinite(v) ? null : v;
}

export interface CellPair {
  meta: CellMeta;
  state: CellState;
}

/** meta.cells 와 프레임의 셀 상태를 cell_id 로 짝지어 meta.cells 순서로 돌려준다. 프레임에 없는 셀은 뺀다. */
export function pairCells(meta: Meta, frame: Frame | undefined): CellPair[] {
  if (!frame) return [];
  const byId = new Map(frame.cells.map((c) => [c.cell_id, c]));
  const out: CellPair[] = [];
  for (const m of meta.cells) {
    const state = byId.get(m.cell_id);
    if (state) out.push({ meta: m, state });
  }
  return out;
}

/** 프레임 전체에서 가장 큰 밀도 (값이 하나도 없으면 null). 셀 순서·meta 가 필요 없다. */
export function frameMaxDensity(frame: Frame, mode: ViewMode): number | null {
  let max: number | null = null;
  for (const c of frame.cells) {
    const v = cellValue(c, mode);
    if (v !== null && (max === null || v > max)) max = v;
  }
  return max;
}
