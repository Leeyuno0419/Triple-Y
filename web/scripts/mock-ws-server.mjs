// 개발용 mock 서버 (실제 server/ 없이 웹 연동을 시험한다). docs/api-spec.md v0.2 의 메시지를 흉내 낸다.
//   npm run mock:ws            → ws://localhost:8787, REST http://localhost:8787
//   .env.local 에  VITE_WS_URL=ws://localhost:8787/ws/zones/{zone_id}  와  VITE_ZONE_ID=zone-mock-ws  설정 후 npm run dev
//
// WebSocket /ws/zones/{zone_id}  (구역 ID 가 다르면 닫기 코드 4404)
//   연결 직후  hello       meta·재생 상태·thresholds·미확인 알림(unacked_alerts)
//   매 1초     zone_state  구역 등급·최대 밀도·인원 + 셀별 밀도·예측·서버 판정 등급(grade, grade_pred_60s)
//   사건       alert       구역 등급이 경계 이상으로 오를 때(GRADE_UP), t=40 에 유입 경보(INFLOW) 1번
//   반복       playback    영상이 끝나면 { state: 'playing', t: 0 } 을 보내고 처음부터 다시 (알림도 새로 만든다)
// REST
//   POST /api/alerts/{alert_id}/ack   확인 → 200 {alert_id, acked_at}, 없는 ID 면 404
//   GET  /api/zones                   구역 목록
//
// 환경변수: PORT(8787), TICK_MS(1000), DUP_ALERTS=1 (alert 를 hello 와 겹치게 두 번 보내 중복 거르기 시험), ACK_FAIL=1 (ack 에 500 응답)
// ※ 등급은 mock 이 임계값(3·4·5)으로 단순 판정한다. 실제 서버는 히스테리시스·불안정 판정을 더한다 (api-spec.md 4절).
import http from 'node:http';
import { WebSocketServer } from 'ws';

const PORT = Number(process.env.PORT ?? 8787);
const TICK_MS = Number(process.env.TICK_MS ?? 1000);
const DUP_ALERTS = process.env.DUP_ALERTS === '1';
const ACK_FAIL = process.env.ACK_FAIL === '1';

const ZONE_ID = 'zone-mock-ws';
const ROWS = 6, COLS = 10, CELL_M = 2, DURATION_S = 150;
const HISTORY_S = 30, HORIZON_S = 60;
const SPEED_CELLS_PER_S = 0.05, SPEED_VAR = 0.004, PEAK = 6.2;
const THRESHOLDS = { density: { caution: 3.0, alert: 4.0, critical: 5.0 }, pressure: 0.02, inflow_ratio: 0.6 };
const MIN_JUDGED_AREA_M2 = 2.0; // 판정 대상 셀 (결정 4)

const GRADES = ['NORMAL', 'CAUTION', 'ALERT', 'CRITICAL'];
const LABEL = { NORMAL: '정상', CAUTION: '주의', ALERT: '경계', CRITICAL: '심각' };
const gradeOf = (d) => (d >= THRESHOLDS.density.critical ? 'CRITICAL' : d >= THRESHOLDS.density.alert ? 'ALERT' : d >= THRESHOLDS.density.caution ? 'CAUTION' : 'NORMAL');

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
  zone_id: ZONE_ID, camera_id: 'cam-mock-ws', video_id: 'MOCK-WS',
  duration_s: DURATION_S, interval_s: 1, cell_size_m: CELL_M,
  models: { counter: 'mock', flow: 'mock', predictor: 'mock' },
  prediction: { history_s: HISTORY_S, horizon_s: HORIZON_S },
  cells,
};

// ---- 상태 ----
let t = 0;
let seq = 0;
let episodeMax = -1; // 이번 사건에서 보낸 가장 높은 구역 등급 (경계 아래로 내려가면 -1)
const alerts = new Map(); // alert_id → { alert, acked_at }

const nowIso = () => new Date().toISOString();
const send = (client, obj) => client.readyState === 1 && client.send(JSON.stringify(obj));
const broadcast = (obj) => { for (const client of wss.clients) send(client, obj); };

function newAlert(level, reason, message, value, cellIds) {
  const day = nowIso().slice(0, 10).replaceAll('-', '');
  const alert = {
    type: 'alert', alert_id: `a-${day}-${String(++seq).padStart(4, '0')}`, zone_id: ZONE_ID,
    t, frame_ts: nowIso(), level, reason, message, value, cell_ids: cellIds,
  };
  alerts.set(alert.alert_id, { alert, acked_at: null });
  broadcast(alert);
  if (DUP_ALERTS) setTimeout(() => broadcast(alert), 50); // 같은 알림이 두 번 오는 경우 (hello 와 alert 겹침)
}

function zoneState() {
  const cellsOut = cells.map((cm) => {
    const d = densityAt(t, cm.row, cm.col);
    const pred = t >= HISTORY_S - 1 ? densityAt(t + HORIZON_S, cm.row, cm.col) : null;
    return {
      cell_id: cm.cell_id, grade: gradeOf(d), density: d,
      vx: d > 0 ? round(SPEED_CELLS_PER_S * CELL_M, 2) : null, vy: d > 0 ? 0 : null,
      speed_var: d > 0 ? SPEED_VAR : null, pressure: d > 0 ? round(d * SPEED_VAR, 4) : 0,
      counterflow: null, density_pred_60s: pred, grade_pred_60s: pred === null ? null : gradeOf(pred),
    };
  });
  const judged = cellsOut.filter((_, i) => cells[i].walkable_area_m2 >= MIN_JUDGED_AREA_M2);
  const maxDensity = judged.length ? Math.max(...judged.map((c) => c.density)) : null;
  const grade = maxDensity === null ? 'NORMAL' : gradeOf(maxDensity);
  const count = round(cellsOut.reduce((sum, c, i) => sum + c.density * cells[i].walkable_area_m2, 0), 2);
  return {
    type: 'zone_state', zone_id: ZONE_ID, t, frame_ts: nowIso(),
    zone: { grade, max_density: maxDensity, inflow_ratio: round(Math.min(0.1 + 0.002 * t, 0.4), 4), inflow_alert: false, count },
    cells: cellsOut,
  };
}

function tick() {
  if (t >= DURATION_S) {
    t = 0; // 영상이 끝나면 처음부터: 먼저 playback(playing, t=0) 을 보내 화면이 쌓아 둔 프레임을 비우게 한다
    episodeMax = -1;
    broadcast({ type: 'playback', zone_id: ZONE_ID, state: 'playing', t: 0, loop: true });
  }
  const msg = zoneState();
  broadcast(msg);

  // 알림은 같은 초의 zone_state 다음에 보낸다 (api-spec.md 3.3절)
  const rank = GRADES.indexOf(msg.zone.grade);
  if (rank >= 2 && rank > episodeMax) {
    episodeMax = rank;
    const ids = msg.cells.filter((c) => GRADES.indexOf(c.grade) >= rank).map((c) => c.cell_id);
    newAlert(msg.zone.grade, 'GRADE_UP', `구역 등급이 ${LABEL[GRADES[rank - 1]]} → ${LABEL[msg.zone.grade]} 단계로 올랐다`, msg.zone.max_density, ids);
  } else if (rank < 2) {
    episodeMax = -1;
  }
  if (t === 40) newAlert('CAUTION', 'INFLOW', '화각 경계에서 안쪽으로 향하는 흐름이 늘었다', 0.65, []);
  t += 1;
}

// ---- HTTP (REST) + WebSocket ----
const cors = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Methods': 'GET,POST,OPTIONS',
  'Access-Control-Allow-Headers': 'Content-Type',
};
const json = (res, status, body) => {
  res.writeHead(status, { 'Content-Type': 'application/json; charset=utf-8', ...cors });
  res.end(body === undefined ? '' : JSON.stringify(body));
};

const server = http.createServer((req, res) => {
  const url = new URL(req.url ?? '/', 'http://localhost');
  if (req.method === 'OPTIONS') { res.writeHead(204, cors); return res.end(); }
  const ack = /^\/api\/alerts\/([^/]+)\/ack$/.exec(url.pathname);
  if (req.method === 'POST' && ack) {
    if (ACK_FAIL) return json(res, 500, { error: 'ACK_FAIL=1' });
    const entry = alerts.get(decodeURIComponent(ack[1]));
    if (!entry) { console.log(`[mock] ack 404 ${ack[1]}`); return json(res, 404); }
    entry.acked_at ??= nowIso(); // 이미 확인한 알림이면 처음 확인 시각을 그대로 준다
    console.log(`[mock] ack 200 ${entry.alert.alert_id}`);
    return json(res, 200, { alert_id: entry.alert.alert_id, acked_at: entry.acked_at });
  }
  if (req.method === 'GET' && url.pathname === '/api/zones') {
    return json(res, 200, [{ zone_id: ZONE_ID, camera_id: meta.camera_id, video_id: meta.video_id }]);
  }
  return json(res, 404);
});

const wss = new WebSocketServer({ server });
wss.on('connection', (ws, req) => {
  const m = /^\/ws\/zones\/([^/?]+)/.exec(req.url ?? '');
  if (m && decodeURIComponent(m[1]) !== ZONE_ID) { ws.close(4404, 'unknown zone'); return; }
  console.log(`[mock] WebSocket 연결 (현재 ${wss.clients.size}명)`);
  send(ws, {
    type: 'hello', schema_version: '0.2', zone_id: ZONE_ID, meta,
    playback: { state: 'playing', t: Math.max(t - 1, 0), loop: true, duration_s: DURATION_S },
    thresholds: THRESHOLDS,
    unacked_alerts: [...alerts.values()].filter((e) => e.acked_at === null).map((e) => e.alert),
  });
  ws.on('close', () => console.log(`[mock] 연결 종료 (현재 ${wss.clients.size}명)`));
});

setInterval(tick, TICK_MS);
server.listen(PORT, () => console.log(`[mock] ws://localhost:${PORT}/ws/zones/${ZONE_ID} · REST http://localhost:${PORT} (${TICK_MS}ms 간격, ${DURATION_S}초 반복${DUP_ALERTS ? ', 알림 중복 전송' : ''}${ACK_FAIL ? ', ack 실패' : ''})`));
