// 개발용 mock WebSocket 서버 (실제 server/ 가 준비되기 전 웹 연동 테스트용).
//   npm run mock:ws            → ws://localhost:8787
//   .env.local 에  VITE_WS_URL=ws://localhost:8787  설정 후 npm run dev
//
// 메시지 규격은 src/lib/liveFeed.ts 의 가정안과 같다:
//   연결 직후  { type: 'timeline', timeline }           (zones 메타 + 빈 frames)
//   매 1초     { type: 'frames', frames: [관측 1개, 예측 3개] }
import { WebSocketServer } from 'ws';

const PORT = Number(process.env.PORT ?? 8787);
const TICK_MS = 1000;
const ROWS = 8, COLS = 12, CELL_M = 12, VISIBLE_COLS = 8;
const HORIZONS = [30, 60, 120];
const CENTER = { lat: 37.5663, lng: 126.9779 }; // 서울시청 (web/src/config/app.ts 와 동일)

const dLat = (ROWS * CELL_M) / 2 / 111_320;
const dLng = (COLS * CELL_M) / 2 / (111_320 * Math.cos((CENTER.lat * Math.PI) / 180));
const zone = {
  zone_id: 'Z01',
  name: '실시간 데모 구역 (mock-ws)',
  bounds: { south: CENTER.lat - dLat, north: CENTER.lat + dLat, west: CENTER.lng - dLng, east: CENTER.lng + dLng },
  rows: ROWS,
  cols: COLS,
  cell_size_m: CELL_M,
};

/** 인파 덩어리 격자. maskUnobserved=true 면 화각 밖(오른쪽 열)은 null */
function blob(centerCol, peak, maskUnobserved) {
  const grid = [];
  for (let r = 0; r < ROWS; r++) {
    const row = [];
    for (let c = 0; c < COLS; c++) {
      if (maskUnobserved && c >= VISIBLE_COLS) row.push(null);
      else row.push(Math.round(peak * Math.exp(-((c - centerCol) ** 2 / 4 + (r - 3.5) ** 2 / 3)) * 1000) / 1000);
    }
    grid.push(row);
  }
  return grid;
}
const total = (g) => g.flat().reduce((s, v) => s + (v ?? 0), 0) * CELL_M ** 2;
const zoneFrame = (density) => ({ zone_id: zone.zone_id, density, count: Math.round(total(density) * 10) / 10 });

let tick = 0;
function makeBundle() {
  const now = Date.now();
  // 덩어리가 0.35열/초로 동쪽으로 이동(약 25초 주기로 반복), 밀도는 정상→심각 사이를 오간다.
  const pos = (tick * 0.35) % (VISIBLE_COLS + 1);
  const peak = 4.6 + 1.6 * Math.sin(tick / 6);
  const observed = {
    t: new Date(now).toISOString(),
    kind: 'observed',
    zones: [zoneFrame(blob(pos, peak, true))],
  };
  const predicted = HORIZONS.map((h, k) => ({
    t: new Date(now + h * 1000).toISOString(),
    kind: 'predicted',
    horizon_s: h,
    zones: [zoneFrame(blob(pos + 0.35 * h * 0.6, peak * (1 - 0.12 * (k + 1)), false))],
  }));
  tick += 1;
  return { type: 'frames', frames: [observed, ...predicted] };
}

const wss = new WebSocketServer({ port: PORT });
wss.on('connection', (ws) => {
  console.log(`[mock-ws] 클라이언트 연결 (현재 ${wss.clients.size}명)`);
  ws.send(JSON.stringify({ type: 'timeline', timeline: { schema_version: '0.1', zones: [zone], frames: [] } }));
  ws.on('close', () => console.log(`[mock-ws] 연결 종료 (현재 ${wss.clients.size}명)`));
});
setInterval(() => {
  const msg = JSON.stringify(makeBundle());
  for (const client of wss.clients) if (client.readyState === 1) client.send(msg);
}, TICK_MS);

console.log(`[mock-ws] ws://localhost:${PORT} 에서 대기 중 (${TICK_MS}ms 간격 전송)`);
