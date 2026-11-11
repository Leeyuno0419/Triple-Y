import type { Frame, Grid, Timeline, ZoneMeta } from '../types/timeline';
import { DEFAULT_CENTER } from '../config/app';
import { metersToDegrees } from './grid';

/**
 * 개발용 mock timeline: 한 구역(8x12 셀) 위를 인파 덩어리가 동쪽으로 이동.
 * 오른쪽 4열은 화각 밖(null)이며, 예측 프레임에서는 그 구간까지 채워진다.
 * 실제 데이터 연동 시 이 파일은 사용되지 않는다 (VITE_USE_MOCK=false).
 */
const ROWS = 8;
const COLS = 12;
const CELL_M = 12;
const VISIBLE_COLS = 8;

function makeZone(): ZoneMeta {
  const { dLat, dLng } = metersToDegrees(DEFAULT_CENTER.lat, (COLS * CELL_M) / 2, (ROWS * CELL_M) / 2);
  return {
    zone_id: 'Z01',
    name: '기본 구역',
    bounds: {
      south: DEFAULT_CENTER.lat - dLat,
      north: DEFAULT_CENTER.lat + dLat,
      west: DEFAULT_CENTER.lng - dLng,
      east: DEFAULT_CENTER.lng + dLng,
    },
    rows: ROWS,
    cols: COLS,
    cell_size_m: CELL_M,
  };
}

function blob(centerCol: number, peak: number, maskUnobserved: boolean): Grid {
  const grid: Grid = [];
  for (let r = 0; r < ROWS; r++) {
    const row: Array<number | null> = [];
    for (let c = 0; c < COLS; c++) {
      if (maskUnobserved && c >= VISIBLE_COLS) {
        row.push(null);
        continue;
      }
      const d2 = (c - centerCol) ** 2 / 4 + (r - 3.5) ** 2 / 3;
      row.push(Math.round(peak * Math.exp(-d2) * 1000) / 1000);
    }
    grid.push(row);
  }
  return grid;
}

const sumCount = (g: Grid, area: number) =>
  g.flat().reduce<number>((s, v) => s + (v ?? 0), 0) * area;

export function makeMockTimeline(): Timeline {
  const zone = makeZone();
  const area = zone.cell_size_m ** 2;
  const t0 = Date.now();
  const iso = (offsetS: number) => new Date(t0 + offsetS * 1000).toISOString();

  const frames: Frame[] = [];
  // 관측 5개 (30초 간격, 과거→현재)
  for (let i = 0; i < 5; i++) {
    const density = blob(1.5 + i * 0.9, 3.0 + i * 0.85, true); // 셀 최대 ≈2.6 → 5.9 (정상→심각)
    frames.push({
      t: iso((i - 4) * 30),
      kind: 'observed',
      zones: [{ zone_id: zone.zone_id, density, count: sumCount(density, area) }],
    });
  }
  // 예측 3개 (+30s, +60s, +120s)
  [30, 60, 120].forEach((h, k) => {
    const density = blob(1.5 + 4 * 0.9 + (k + 1) * 1.6, 6.7 - (k + 1) * 0.2, false); // 셀 최대 ≈5.6~5.9
    frames.push({
      t: iso(h),
      kind: 'predicted',
      horizon_s: h,
      zones: [{ zone_id: zone.zone_id, density, count: sumCount(density, area) }],
    });
  });

  return { schema_version: '0.1', zones: [zone], frames };
}
