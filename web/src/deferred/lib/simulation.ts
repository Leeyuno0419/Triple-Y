import type { Frame, Grid, ZoneMeta } from '../types/timeline';
import { metersToDegrees } from './grid';

/**
 * 해외 지역용 가상 시뮬레이션 데이터.
 * 실제 관측이 없는 지역에서 화면 동작(타임라인 이동 → 인원·밀도·위험 단계·고밀도 셀 갱신)을 보여 주기 위한 것으로,
 * 위치(소수점 둘째 자리)로 시드를 정해 같은 장소는 항상 같은 값이 나온다.
 */
export interface Simulation {
  zone: ZoneMeta;
  frames: Frame[];
}

export interface SimAnchor {
  lat: number;
  lng: number;
  name?: string;
}

const ROWS = 8;
const COLS = 12;
const CELL_M = 12;
const FRAME_COUNT = 90;
const PEAK_DENSITY = 6.4; // 시간이 지나며 정상 → 심각 단계를 모두 지나가도록 최고 밀도를 이 정도까지 키운다

function hash(text: string): number {
  let h = 2166136261;
  for (let i = 0; i < text.length; i++) {
    h ^= text.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}

/** 시드가 같으면 같은 수열을 내는 간단한 난수 생성기 (mulberry32) */
function seeded(seed: number) {
  let a = seed;
  return () => {
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export function makeSimulation(anchor: SimAnchor): Simulation {
  const seed = hash(`${anchor.lat.toFixed(2)},${anchor.lng.toFixed(2)}`);
  const rand = seeded(seed);

  const { dLat, dLng } = metersToDegrees(anchor.lat, (COLS * CELL_M) / 2, (ROWS * CELL_M) / 2);
  const zone: ZoneMeta = {
    zone_id: `SIM-${seed.toString(16).slice(0, 6)}`,
    name: anchor.name ?? '해외 가상 구역',
    bounds: { south: anchor.lat - dLat, north: anchor.lat + dLat, west: anchor.lng - dLng, east: anchor.lng + dLng },
    rows: ROWS,
    cols: COLS,
    cell_size_m: CELL_M,
  };

  // 인파 덩어리 3개: 서로 다른 속도로 격자 안을 오가고, 크기가 커졌다 작아졌다 한다
  const blobs = Array.from({ length: 3 }, (_, k) => ({
    r0: 1.5 + rand() * (ROWS - 3),
    c0: 2 + rand() * (COLS - 4),
    ar: 0.8 + rand() * 1.6,          // 세로로 오가는 폭(칸)
    ac: 1.5 + rand() * 3,            // 가로로 오가는 폭(칸)
    speed: 0.6 + rand() * 1.2,       // 이동 속도(주기 배수)
    phase: rand() * Math.PI * 2,
    sigma: 1.3 + rand() * 1.1,
    amp: k === 0 ? PEAK_DENSITY : PEAK_DENSITY * (0.35 + rand() * 0.3),
    pulse: rand() * Math.PI * 2,
  }));
  const cellPhase = Array.from({ length: ROWS * COLS }, () => rand() * Math.PI * 2);
  const envelopePhase = rand() * Math.PI * 2;
  const cellArea = CELL_M * CELL_M;

  const start = Math.floor(Date.now() / 1000) - FRAME_COUNT; // 지금까지 FRAME_COUNT 초 동안의 가상 기록
  const frames: Frame[] = [];
  for (let i = 0; i < FRAME_COUNT; i++) {
    const u = i / FRAME_COUNT;
    // 전체 혼잡도: 한 번 올랐다 내려가는 곡선 (정상 ~ 심각을 오가도록)
    const envelope = 0.45 + 0.55 * (0.5 + 0.5 * Math.sin(2 * Math.PI * u + envelopePhase));
    const density: Grid = [];
    let people = 0;
    for (let r = 0; r < ROWS; r++) {
      const row: Array<number | null> = [];
      for (let c = 0; c < COLS; c++) {
        let v = 0;
        for (const b of blobs) {
          const pr = b.r0 + b.ar * Math.sin(2 * Math.PI * u * b.speed + b.phase);
          const pc = b.c0 + b.ac * Math.cos(2 * Math.PI * u * b.speed + b.phase);
          const pulse = 0.75 + 0.25 * Math.sin(2 * Math.PI * u * 2 + b.pulse);
          const d2 = (r - pr) ** 2 + (c - pc) ** 2;
          v += b.amp * envelope * pulse * Math.exp(-d2 / (2 * b.sigma ** 2));
        }
        v += 0.12 + 0.08 * Math.sin(2 * Math.PI * u * 3 + cellPhase[r * COLS + c]); // 잔잔한 흔들림
        v = Math.max(0, Math.round(v * 1000) / 1000);
        people += v * cellArea;
        row.push(v);
      }
      density.push(row);
    }
    const t = new Date((start + i) * 1000).toISOString();
    frames.push({ t, kind: 'observed', zones: [{ zone_id: zone.zone_id, count: Math.round(people), density }] });
  }
  return { zone, frames };
}
