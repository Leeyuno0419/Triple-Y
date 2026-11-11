import type { CellMeta, CellState, Frame, Meta, Timeline } from '../types/timeline';

/**
 * 개발용 mock timeline (규격 v0.1): 인파 덩어리가 6×10 셀 구역을 동쪽으로 일정 속도로 이동한다. 1초 간격.
 * src/predict/sample.py 의 합성 데이터와 같은 장면이며, 60초 뒤 예측(density_pred_60s)은 같은 이동을 60초 더 진행한 값이다.
 * 실제 데이터 연동 시 이 파일은 사용되지 않는다 (VITE_USE_MOCK=false).
 */
const ROWS = 6;
const COLS = 10;
const CELL_M = 2;
const HISTORY_S = 30;
const HORIZON_S = 60;
const SPEED_CELLS_PER_S = 0.05;
const SPEED_VAR = 0.004;
const PEAK = 6.2; // 셀 최대 밀도(명/m²), 기획서 3.2 "심각" 수준

const cellId = (r: number, c: number) => `c-${String(r).padStart(2, '0')}${String(c).padStart(2, '0')}`;
const round = (v: number, d: number) => Math.round(v * 10 ** d) / 10 ** d;

/** 시각 t 의 셀 (r, c) 밀도 */
function densityAt(t: number, r: number, c: number): number {
  const center = 1.5 + SPEED_CELLS_PER_S * t;
  return round(PEAK * Math.exp(-((c - center) ** 2 / 4 + (r - 2.5) ** 2 / 3)), 2);
}

function makeMeta(durationS: number): Meta {
  const cells: CellMeta[] = [];
  for (let r = 0; r < ROWS; r++) {
    for (let c = 0; c < COLS; c++) {
      const x0 = c / COLS, x1 = (c + 1) / COLS, y0 = r / ROWS, y1 = (r + 1) / ROWS;
      cells.push({
        cell_id: cellId(r, c),
        row: r,
        col: c,
        walkable_area_m2: CELL_M ** 2 * (r === 0 ? 0.8 : 1), // 첫 행은 보행 면적이 작다
        image_polygon: [[x0, y0], [x1, y0], [x1, y1], [x0, y1]],
      });
    }
  }
  return {
    zone_id: 'zone-mock',
    camera_id: 'cam-mock',
    video_id: 'MOCK',
    duration_s: durationS,
    interval_s: 1,
    cell_size_m: CELL_M,
    models: { counter: 'mock', flow: 'mock', predictor: 'mock' },
    prediction: { history_s: HISTORY_S, horizon_s: HORIZON_S },
    cells,
  };
}

function makeFrame(meta: Meta, t: number): Frame {
  const cells: CellState[] = meta.cells.map((cm) => {
    const d = densityAt(t, cm.row, cm.col);
    const pred = t >= HISTORY_S - 1 ? densityAt(t + HORIZON_S, cm.row, cm.col) : null;
    return d > 0
      ? { cell_id: cm.cell_id, density: d, vx: round(SPEED_CELLS_PER_S * CELL_M, 2), vy: 0, speed_var: SPEED_VAR, pressure: round(d * SPEED_VAR, 4), density_pred_60s: pred }
      : { cell_id: cm.cell_id, density: 0, vx: null, vy: null, speed_var: null, pressure: 0, density_pred_60s: pred };
  });
  return { t, inflow_ratio: round(Math.min(0.1 + 0.002 * t, 0.4), 4), cells };
}

export function makeMockTimeline(durationS = 150): Timeline {
  const meta = makeMeta(durationS);
  return {
    schema_version: '0.1',
    meta,
    frames: Array.from({ length: durationS }, (_, t) => makeFrame(meta, t)),
  };
}
