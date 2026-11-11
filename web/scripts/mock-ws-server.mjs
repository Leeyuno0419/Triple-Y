// 개발용 mock WebSocket 서버 (실제 server/ 가 준비되기 전 웹 연동 테스트용).
//   npm run mock:ws            → ws://localhost:8787
//   .env.local 에  VITE_WS_URL=ws://localhost:8787  설정 후 npm run dev
//
// 메시지 규격은 src/lib/liveFeed.ts 의 가정안과 같다 (timeline.json 규격 v0.1, docs/timeline-spec.md):
//   연결 직후  { type: 'timeline', timeline }   (meta + 빈 frames)
//   매 1초     { type: 'frame', frame }          (t = 영상 시작 뒤 경과 초, 0 부터 1씩 증가)
//   영상 끝(t = DURATION_S)에 닿으면 timeline 을 다시 보내 처음부터 반복한다.
import { WebSocketServer } from 'ws';

const PORT = Number(process.env.PORT ?? 8787);
const TICK_MS = 1000;
const ROWS = 6, COLS = 10, CELL_M = 2, DURATION_S = 150;
const HISTORY_S = 30, HORIZON_S = 60;
const SPEED_CELLS_PER_S = 0.05, SPEED_VAR = 0.004, PEAK = 6.2;

const cellId = (r, c) => `c-${String(r).padStart(2, '0')}${String(c).padStart(2, '0')}`;
const round = (v, d) => Math.round(v * 10 ** d) / 10 ** d;
const densityAt = (t, r, c) =>
  round(PEAK * Math.exp(-(((c - (1.5 + SPEED_CELLS_PER_S * t)) ** 2) / 4 + ((r - 2.5) ** 2) / 3)), 2);

const cells = [];
for (let r = 0; r < ROWS; r++) {
  for (let c = 0; c < COLS; c++) {
    const x0 = c / COLS, x1 = (c + 1) / COLS, y0 = r / ROWS, y1 = (r + 1) / ROWS;
    cells.push({
      cell_id: cellId(r, c), row: r, col: c,
      walkable_area_m2: CELL_M ** 2 * (r === 0 ? 0.8 : 1),
      image_polygon: [[x0, y0], [x1, y0], [x1, y1], [x0, y1]],
    });
  }
}
const meta = {
  zone_id: 'zone-mock-ws', camera_id: 'cam-mock-ws', video_id: 'MOCK-WS',
  duration_s: DURATION_S, interval_s: 1, cell_size_m: CELL_M,
  models: { counter: 'mock', flow: 'mock', predictor: 'mock' },
  prediction: { history_s: HISTORY_S, horizon_s: HORIZON_S },
  cells,
};

function makeFrame(t) {
  return {
    t,
    inflow_ratio: round(Math.min(0.1 + 0.002 * t, 0.4), 4),
    cells: cells.map((cm) => {
      const d = densityAt(t, cm.row, cm.col);
      const pred = t >= HISTORY_S - 1 ? densityAt(t + HORIZON_S, cm.row, cm.col) : null;
      return d > 0
        ? { cell_id: cm.cell_id, density: d, vx: round(SPEED_CELLS_PER_S * CELL_M, 2), vy: 0, speed_var: SPEED_VAR, pressure: round(d * SPEED_VAR, 4), density_pred_60s: pred }
        : { cell_id: cm.cell_id, density: 0, vx: null, vy: null, speed_var: null, pressure: 0, density_pred_60s: pred };
    }),
  };
}

const timelineMsg = () => JSON.stringify({ type: 'timeline', timeline: { schema_version: '0.1', meta, frames: [] } });

let tick = 0;
const wss = new WebSocketServer({ port: PORT });
wss.on('connection', (ws) => {
  console.log(`[mock-ws] 클라이언트 연결 (현재 ${wss.clients.size}명)`);
  ws.send(timelineMsg());
  ws.on('close', () => console.log(`[mock-ws] 연결 종료 (현재 ${wss.clients.size}명)`));
});
setInterval(() => {
  if (tick >= DURATION_S) {
    tick = 0; // 영상이 끝나면 처음부터 다시: 클라이언트가 이전 프레임을 비우도록 timeline 을 다시 보낸다
    for (const client of wss.clients) if (client.readyState === 1) client.send(timelineMsg());
  }
  const msg = JSON.stringify({ type: 'frame', frame: makeFrame(tick) });
  for (const client of wss.clients) if (client.readyState === 1) client.send(msg);
  tick += 1;
}, TICK_MS);

console.log(`[mock-ws] ws://localhost:${PORT} 에서 대기 중 (${TICK_MS}ms 간격 전송, ${DURATION_S}초 반복)`);
