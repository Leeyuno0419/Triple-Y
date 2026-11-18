// E8: 서버 WebSocket에 화면처럼 접속해 알림 지연(p95)과 반복 재생 무중단을 잰다.
//
//   node infra/e8/measure_alert_latency.mjs --zone zone-e04-039 --minutes 30
//
// 옵션: --url ws://localhost:8080 (서버 주소), --timeline <파일> (기본 data/processed/timeline/{video_id}.json),
//       --out <폴더> (기본 outputs/e8)
// Node 22 이상이 필요하다 (내장 WebSocket). 따로 설치할 패키지는 없다.
//
// 지연을 두 가지로 잰다 (docs/api-spec.md 7절).
// - 전송 지연: 메시지를 받은 시각 − frame_ts (서버가 그 초를 재생한 시각)
// - 알림 지연: 조건이 처음 충족된 초(onset)를 재생한 시각부터 알림을 받은 시각까지.
//   = (alert.t − onset_t) × interval_s + 전송 지연. 히스테리시스 확인 시간이 여기에 들어간다.
//   onset_t는 서버가 주지 않으므로 타임라인 파일에서 거꾸로 찾는다 (findOnset).
// 재는 범위는 메시지 도착까지다. 브라우저가 화면에 그리는 시간은 들어가지 않는다.
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..');

/** `--이름 값` 형식의 실행 인자를 읽는다. */
function parseArgs(argv) {
  const args = { url: 'ws://localhost:8080', zone: 'zone-e04-039', minutes: 30, timeline: null, out: join(ROOT, 'outputs', 'e8') };
  for (let i = 0; i < argv.length; i += 2) {
    const key = argv[i].replace(/^--/, '');
    if (!(key in args) || argv[i + 1] === undefined) throw new Error(`알 수 없는 인자: ${argv[i]}`);
    args[key] = key === 'minutes' ? Number(argv[i + 1]) : argv[i + 1];
  }
  return args;
}

/** 정렬된 배열에서 p 분위수(0~1)를 고른다 (nearest-rank). 비어 있으면 null. */
export function percentile(sorted, p) {
  if (sorted.length === 0) return null;
  return sorted[Math.min(sorted.length - 1, Math.max(0, Math.ceil(p * sorted.length) - 1))];
}

/** 숫자 목록의 개수·p50·p95·최대를 낸다. */
export function summarize(values) {
  const sorted = [...values].sort((a, b) => a - b);
  const round = (v) => (v === null ? null : Math.round(v * 10) / 10);
  return { n: sorted.length, p50: round(percentile(sorted, 0.5)), p95: round(percentile(sorted, 0.95)), max: round(sorted.at(-1) ?? null) };
}

/**
 * 알림 조건이 처음 충족된 초(onset_t)를 타임라인에서 찾는다.
 * alert.t에서 거꾸로 가며 조건이 연속으로 참인 구간의 시작을 고른다. 셀이 여럿이면 가장 이른 시작을 쓴다(지연이 길게 나오는 쪽).
 * - GRADE_UP: cell_ids 셀의 밀도가 level 기준 이상 (심각은 pressure 기준 초과도 포함)
 * - INSTABILITY: cell_ids 셀의 pressure가 기준 초과
 * - INFLOW: 5초 평균 창(t-4 ~ t) 안에서 inflow_ratio가 기준을 처음 넘은 초
 */
export function findOnset(alert, frames, thresholds) {
  const cellAt = (t, id) => frames[t]?.cells.find((c) => c.cell_id === id);
  const overPressure = (c) => c?.pressure != null && c.pressure > thresholds.pressure;
  if (alert.reason === 'INFLOW') {
    for (let t = Math.max(0, alert.t - 4); t <= alert.t; t++) {
      const v = frames[t]?.inflow_ratio;
      if (v != null && v > thresholds.inflow_ratio) return t;
    }
    return alert.t;
  }
  const limit = { CAUTION: thresholds.density.caution, ALERT: thresholds.density.alert, CRITICAL: thresholds.density.critical }[alert.level];
  const holds = (c) => {
    if (alert.reason === 'INSTABILITY') return overPressure(c);
    return (c?.density != null && c.density >= limit) || (alert.level === 'CRITICAL' && overPressure(c));
  };
  let onset = alert.t;
  for (const id of alert.cell_ids ?? []) {
    let t = alert.t;
    while (t > 0 && holds(cellAt(t - 1, id))) t--;
    if (holds(cellAt(alert.t, id))) onset = Math.min(onset, t);
  }
  return onset;
}

/** 측정 결과를 마크다운 표로 만든다. */
function toMarkdown(r) {
  const row = (name, s) => `| ${name} | ${s.n} | ${s.p50 ?? '-'} | ${s.p95 ?? '-'} | ${s.max ?? '-'} |`;
  const reasons = Object.entries(r.alert_delay_ms_by_reason).map(([k, s]) => row(`알림 지연 ${k}`, s));
  const pass = (ok) => (ok === null ? '판정 불가 (알림 없음)' : ok ? '통과' : '미통과');
  return [
    `# E8 알림 지연·무중단 (${r.zone_id})`,
    '',
    `- 측정: ${r.started_at} ~ ${r.ended_at} (${r.elapsed_min}분), 타임라인 ${r.video_id} ${r.duration_s}초 반복 ${r.loops}회`,
    `- 판정 → 알림 p95 ≤ 5초: **${pass(r.pass_alert_p95)}** (p95 ${r.alert_delay_ms.p95 ?? '-'} ms)`,
    `- 반복 재생 무중단: **${pass(r.pass_no_interruption)}** (끊김 ${r.disconnects}회, 빠진 초 ${r.missing_seconds}개, 가장 긴 수신 간격 ${r.max_gap_ms} ms)`,
    '',
    '| 항목 (ms) | 개수 | p50 | p95 | 최대 |',
    '|---|---|---|---|---|',
    row('전송 지연 zone_state', r.transport_delay_ms),
    row('알림 지연 전체', r.alert_delay_ms),
    ...reasons,
    '',
    '- 전송 지연 = 받은 시각 − `frame_ts`. 알림 지연 = 조건이 처음 충족된 초의 재생 시각부터 알림을 받기까지.',
    '- Node 클라이언트가 메시지를 받은 시각까지 잰 값이다. 브라우저가 화면에 그리는 시간은 들어가지 않는다.',
    '',
  ].join('\n');
}

/** 서버에 접속해 정해진 시간 동안 메시지를 받고, 지연과 끊김을 기록해 저장한다. */
async function main() {
  const args = parseArgs(process.argv.slice(2));
  const endAt = Date.now() + args.minutes * 60_000;
  const startedAt = new Date();
  const transport = [];
  const alerts = [];
  let hello = null, frames = null, lastT = null, lastRecv = null;
  let loops = 0, disconnects = 0, missing = 0, maxGap = 0, states = 0;

  const onMessage = (raw) => {
    const recv = Date.now();
    const msg = JSON.parse(raw);
    if (msg.type === 'hello') {
      hello ??= msg;
      const file = args.timeline ?? join(ROOT, 'data', 'processed', 'timeline', `${msg.meta.video_id}.json`);
      frames ??= JSON.parse(readFileSync(file, 'utf8')).frames;
    } else if (msg.type === 'playback' && msg.t === 0) {
      loops++;
      lastT = null;
    } else if (msg.type === 'zone_state') {
      states++;
      transport.push(recv - Date.parse(msg.frame_ts));
      if (lastT !== null && msg.t > lastT + 1) missing += msg.t - lastT - 1;
      if (lastRecv !== null) maxGap = Math.max(maxGap, recv - lastRecv);
      lastT = msg.t;
      lastRecv = recv;
    } else if (msg.type === 'alert') {
      const onsetT = findOnset(msg, frames, hello.thresholds);
      const transportMs = recv - Date.parse(msg.frame_ts);
      const delayMs = (msg.t - onsetT) * hello.meta.interval_s * 1000 + transportMs;
      alerts.push({ alert_id: msg.alert_id, reason: msg.reason, level: msg.level, t: msg.t, onset_t: onsetT, transport_ms: transportMs, delay_ms: delayMs });
      console.log(`알림 t=${msg.t} ${msg.reason} ${msg.level} onset_t=${onsetT} 지연=${delayMs}ms`);
    }
  };

  // 끊기면 1초 뒤 다시 접속한다. 끊김 횟수는 무중단 판정에 쓴다.
  while (Date.now() < endAt) {
    await new Promise((done) => {
      const ws = new WebSocket(`${args.url}/ws/zones/${args.zone}`);
      const timer = setTimeout(() => ws.close(1000), Math.max(0, endAt - Date.now()));
      ws.onmessage = (e) => onMessage(e.data);
      ws.onerror = () => {};
      ws.onclose = (e) => {
        clearTimeout(timer);
        if (Date.now() < endAt - 500) {
          disconnects++;
          console.log(`끊김 code=${e.code} (${disconnects}회)`);
          lastT = null;
          setTimeout(done, 1000);
        } else done();
      };
    });
  }
  if (!hello) throw new Error(`서버에 접속하지 못했다: ${args.url}/ws/zones/${args.zone}`);

  const byReason = {};
  for (const a of alerts) (byReason[a.reason] ??= []).push(a.delay_ms);
  const alertSummary = summarize(alerts.map((a) => a.delay_ms));
  const result = {
    zone_id: args.zone, video_id: hello.meta.video_id, duration_s: hello.meta.duration_s,
    started_at: startedAt.toISOString(), ended_at: new Date().toISOString(),
    elapsed_min: Math.round((Date.now() - startedAt.getTime()) / 6000) / 10,
    zone_states: states, loops, disconnects, missing_seconds: missing, max_gap_ms: maxGap,
    transport_delay_ms: summarize(transport),
    alert_delay_ms: alertSummary,
    alert_delay_ms_by_reason: Object.fromEntries(Object.entries(byReason).map(([k, v]) => [k, summarize(v)])),
    pass_alert_p95: alertSummary.n === 0 ? null : alertSummary.p95 <= 5000,
    pass_no_interruption: disconnects === 0 && missing === 0,
    thresholds: hello.thresholds,
    environment: { node: process.version, platform: process.platform, client: 'node WebSocket (화면 표시 시간 제외)' },
    alerts,
  };
  mkdirSync(args.out, { recursive: true });
  const base = join(args.out, `${hello.meta.video_id}_alert_latency`);
  writeFileSync(`${base}.json`, JSON.stringify(result, null, 2), 'utf8');
  writeFileSync(`${base}.md`, toMarkdown(result), 'utf8');
  console.log(`저장: ${base}.json, ${base}.md`);
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main().catch((e) => {
    console.error(e.message);
    process.exit(1);
  });
}
