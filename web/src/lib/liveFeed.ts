/**
 * 실시간(WebSocket) 메시지 해석과 반영 로직. 환경변수/브라우저 API 의존 없는 순수 함수.
 *
 * 규격: docs/api-spec.md 3절 (서버 → 화면, JSON 텍스트 프레임). 모든 메시지는 type 으로 구분한다.
 *   hello       접속 직후 1번, 재접속 때마다: meta(셀 격자), 재생 상태, 표시용 기준값(thresholds), 미확인 알림
 *   zone_state  1초마다: 구역 등급·최대 밀도·인원, 셀별 밀도·예측·서버 판정 등급
 *   alert       사건이 생길 때: 알림 1건
 *   playback    재생 상태가 바뀔 때. { state: 'playing', t: 0 } 이면 반복으로 처음으로 돌아간 것이다
 *   (모르는 type 은 무시한다 — 뒤 호환)
 *
 * 반영 규칙
 *   - 등급은 서버가 판정한 값을 그대로 쓴다. 화면에서 밀도로 다시 계산하지 않는다.
 *   - hello 는 미확인 알림 목록을 통째로 바꾼다 (서버를 재시작하면 알림 번호가 1부터 다시 시작해 옛 ID 는 버린다, 4.5절).
 *   - 같은 알림이 hello 와 alert 로 두 번 올 수 있어 alert_id 로 거른다. 확인해서 지운 알림이 늦게 다시 와도 거른다.
 *   - 같은 t 의 프레임은 교체하고, t 오름차순을 유지하며, 최대 maxFrames 개만 둔다 (오래된 것부터 버림).
 *   - playback { playing, t: 0 } 을 받으면 쌓아 둔 프레임(그래프·이력)을 비운다. 그 뒤 t=0 의 zone_state 가 온다.
 *   - zone_state 의 t 가 이전보다 작아지면(서버 재시작 등) 이전 프레임을 비운다.
 */
import type { Frame, Meta, Timeline } from '../types/timeline';
import type {
  AckState, LiveAlert, LiveMessage, Playback, ServerAlert, Thresholds,
} from '../types/live';
import { parseGrade } from './grade';
import { validateFrame, validateMeta } from './validate';

const isObj = (v: unknown): v is Record<string, unknown> => typeof v === 'object' && v !== null && !Array.isArray(v);
const isNum = (v: unknown): v is number => typeof v === 'number' && Number.isFinite(v);

/** 구역당 보관하는 알림 최대 개수 (서버 crowdsight.unacked-alert-limit 과 같다) */
export const MAX_ALERTS = 100;
/** 확인해서 지운 알림 ID 를 기억하는 최대 개수 */
const MAX_ACKED_IDS = 200;

// --------------------------------------------------------------------------- //
// 해석 (문자열 → 메시지)
// --------------------------------------------------------------------------- //
function parsePlayback(v: unknown): Playback | null {
  if (!isObj(v) || (v.state !== 'playing' && v.state !== 'ended')) return null;
  if (!Number.isInteger(v.t) || (v.t as number) < 0) return null;
  return { state: v.state, t: v.t as number, loop: v.loop === true, duration_s: isNum(v.duration_s) ? v.duration_s : null };
}

function parseThresholds(v: unknown): Thresholds | null {
  if (!isObj(v) || !isObj(v.density)) return null;
  const { caution, alert, critical } = v.density;
  if (!isNum(caution) || !isNum(alert) || !isNum(critical) || !isNum(v.pressure) || !isNum(v.inflow_ratio)) return null;
  return { density: { caution, alert, critical }, pressure: v.pressure, inflow_ratio: v.inflow_ratio };
}

/** 알림 1건을 해석한다 (alert 메시지 본문, hello.unacked_alerts 원소 모두 같은 키). 형식이 맞지 않으면 Error. */
export function parseAlert(v: unknown): ServerAlert {
  if (!isObj(v)) throw new Error('alert 가 객체가 아닙니다.');
  if (typeof v.alert_id !== 'string' || v.alert_id === '') throw new Error('alert.alert_id 가 필요합니다.');
  const level = parseGrade(v.level);
  if (!level) throw new Error(`alert ${v.alert_id}: 알 수 없는 level ${String(v.level)}`);
  if (!Number.isInteger(v.t) || (v.t as number) < 0) throw new Error(`alert ${v.alert_id}: t 는 0 이상 정수입니다.`);
  return {
    alert_id: v.alert_id,
    zone_id: typeof v.zone_id === 'string' ? v.zone_id : '',
    t: v.t as number,
    frame_ts: typeof v.frame_ts === 'string' ? v.frame_ts : '',
    level,
    reason: typeof v.reason === 'string' ? v.reason : '',
    message: typeof v.message === 'string' ? v.message : '',
    value: isNum(v.value) ? v.value : null,
    cell_ids: Array.isArray(v.cell_ids) ? v.cell_ids.filter((c): c is string => typeof c === 'string') : [],
  };
}

/**
 * 수신한 텍스트를 해석한다. 모르는 type 은 null(무시), JSON 이 아니거나 알려진 type 의 형식이 틀리면 Error 를 던진다.
 * zone_state 의 셀 검증은 meta 가 필요해 applyLiveMessage 에서 한다.
 */
export function parseLiveMessage(raw: string): LiveMessage | null {
  const obj: unknown = JSON.parse(raw);
  if (!isObj(obj)) throw new Error('메시지가 객체가 아닙니다.');

  switch (obj.type) {
    case 'hello': {
      if (typeof obj.zone_id !== 'string') throw new Error('hello.zone_id 가 필요합니다.');
      const alerts: ServerAlert[] = [];
      for (const a of Array.isArray(obj.unacked_alerts) ? obj.unacked_alerts : []) {
        try {
          alerts.push(parseAlert(a));
        } catch {
          // 알림 하나가 잘못돼도 hello 전체(셀 격자)는 살린다
        }
      }
      return {
        type: 'hello',
        schema_version: String(obj.schema_version ?? ''),
        zone_id: obj.zone_id,
        meta: validateMeta(obj.meta),
        playback: parsePlayback(obj.playback),
        thresholds: parseThresholds(obj.thresholds),
        unacked_alerts: alerts,
      };
    }
    case 'zone_state': {
      if (!Number.isInteger(obj.t) || (obj.t as number) < 0) throw new Error('zone_state.t 는 0 이상 정수입니다.');
      if (!isObj(obj.zone)) throw new Error('zone_state.zone 이 필요합니다.');
      if (!Array.isArray(obj.cells)) throw new Error('zone_state.cells 배열이 필요합니다.');
      const z = obj.zone;
      return {
        type: 'zone_state',
        zone_id: typeof obj.zone_id === 'string' ? obj.zone_id : '',
        frame: {
          t: obj.t as number,
          inflow_ratio: (z.inflow_ratio as number | null | undefined) ?? null,
          count: (z.count as number | null | undefined) ?? null,
          zone: { grade: parseGrade(z.grade), max_density: isNum(z.max_density) ? z.max_density : null, inflow_alert: z.inflow_alert === true },
          cells: obj.cells,
        },
      };
    }
    case 'alert':
      return { type: 'alert', alert: parseAlert(obj) };
    case 'playback': {
      const playback = parsePlayback(obj);
      if (!playback) throw new Error('playback 형식 오류: state(playing|ended)와 t 가 필요합니다.');
      return { type: 'playback', zone_id: typeof obj.zone_id === 'string' ? obj.zone_id : '', playback };
    }
    default:
      return null; // 모르는 type 은 무시한다 (뒤 호환)
  }
}

// --------------------------------------------------------------------------- //
// 반영 (상태 + 메시지 → 새 상태)
// --------------------------------------------------------------------------- //
export interface LiveState {
  /** hello 로 meta(셀 격자)를 받은 뒤부터 있다. 그 전에는 null */
  timeline: Timeline | null;
  /** hello.thresholds: 범례·그래프 기준선 표시용 */
  thresholds: Thresholds | null;
  playback: Playback | null;
  /** 미확인 알림. 오래된 것부터 */
  alerts: LiveAlert[];
  /** 확인해서 지운 알림 ID (뒤늦게 다시 와도 걸러낸다) */
  ackedIds: string[];
}

export const INITIAL_LIVE_STATE: LiveState = { timeline: null, thresholds: null, playback: null, alerts: [], ackedIds: [] };

const sameLayout = (a: Meta, b: Meta) =>
  a.zone_id === b.zone_id &&
  a.cells.length === b.cells.length &&
  a.cells.every((c, i) => c.cell_id === b.cells[i].cell_id);

/** alert_id 가 겹치는 알림은 앞의 것만 남긴다. */
function dedupe(alerts: ServerAlert[]): ServerAlert[] {
  const seen = new Set<string>();
  return alerts.filter((a) => (seen.has(a.alert_id) ? false : (seen.add(a.alert_id), true)));
}

function applyHello(s: LiveState, msg: Extract<LiveMessage, { type: 'hello' }>): LiveState {
  // 같은 구역으로 재접속하면 쌓아 둔 프레임을 이어 쓴다 (그래프가 끊기지 않게). 구역이 바뀌면 비운다.
  const keep = s.timeline !== null && sameLayout(s.timeline.meta, msg.meta);
  return {
    timeline: { schema_version: msg.schema_version, meta: msg.meta, frames: keep && s.timeline ? s.timeline.frames : [] },
    thresholds: msg.thresholds,
    playback: msg.playback,
    alerts: dedupe(msg.unacked_alerts).map((a) => ({ ...a, ack: 'idle' as const })),
    ackedIds: [],
  };
}

function applyZoneState(s: LiveState, msg: Extract<LiveMessage, { type: 'zone_state' }>, maxFrames: number): LiveState {
  const tl = s.timeline;
  if (!tl) return s; // hello(meta) 가 오기 전의 zone_state 는 셀 격자를 몰라 쓸 수 없다
  if (msg.zone_id && msg.zone_id !== tl.meta.zone_id) return s;

  const checked = validateFrame(
    { t: msg.frame.t, inflow_ratio: msg.frame.inflow_ratio, count: msg.frame.count, cells: msg.frame.cells },
    tl.meta,
  );
  // 서버 판정 등급을 셀마다 붙인다. 키가 항상 있으므로(알 수 없는 값은 null) 화면은 이 값을 그대로 쓴다.
  const frame: Frame = {
    ...checked,
    zone: msg.frame.zone,
    cells: checked.cells.map((c) => ({ ...c, grade: parseGrade(c.grade), grade_pred_60s: parseGrade(c.grade_pred_60s) })),
  };

  const last = tl.frames[tl.frames.length - 1];
  const base = last && frame.t < last.t ? [] : tl.frames; // 시간이 되감겼으면(서버 재시작 등) 이전 프레임을 버린다
  const merged = [...base.filter((f) => f.t !== frame.t), frame].sort((a, b) => a.t - b.t);
  const frames = merged.length > maxFrames ? merged.slice(merged.length - maxFrames) : merged;
  return { ...s, timeline: { ...tl, frames } };
}

function addAlert(s: LiveState, alert: ServerAlert): LiveState {
  if (s.timeline && alert.zone_id && alert.zone_id !== s.timeline.meta.zone_id) return s;
  if (s.ackedIds.includes(alert.alert_id) || s.alerts.some((a) => a.alert_id === alert.alert_id)) return s; // hello 와 alert 로 두 번 온 것
  const alerts = [...s.alerts, { ...alert, ack: 'idle' as const }];
  return { ...s, alerts: alerts.length > MAX_ALERTS ? alerts.slice(alerts.length - MAX_ALERTS) : alerts };
}

function applyPlayback(s: LiveState, msg: Extract<LiveMessage, { type: 'playback' }>): LiveState {
  if (s.timeline && msg.zone_id && msg.zone_id !== s.timeline.meta.zone_id) return s;
  const { playback } = msg;
  // 반복으로 처음으로 돌아갔다: 쌓아 둔 프레임을 비운다 (그래프·이력 초기화). 알림은 아직 확인 전이라 남긴다.
  const restart = playback.state === 'playing' && playback.t === 0;
  return { ...s, playback, timeline: restart && s.timeline ? { ...s.timeline, frames: [] } : s.timeline };
}

/** 메시지를 상태에 반영한 새 상태를 돌려준다 (입력은 변경하지 않는다). zone_state 의 셀이 meta 와 안 맞으면 Error. */
export function applyLiveMessage(s: LiveState, msg: LiveMessage, maxFrames: number): LiveState {
  switch (msg.type) {
    case 'hello':
      return applyHello(s, msg);
    case 'zone_state':
      return applyZoneState(s, msg, maxFrames);
    case 'alert':
      return addAlert(s, msg.alert);
    case 'playback':
      return applyPlayback(s, msg);
  }
}

// --------------------------------------------------------------------------- //
// 알림 확인(ack) 상태
// --------------------------------------------------------------------------- //
/** 알림 하나의 확인 요청 상태를 바꾼다 (pending=요청 중, error=실패). */
export function markAck(s: LiveState, alertId: string, ack: AckState): LiveState {
  return { ...s, alerts: s.alerts.map((a) => (a.alert_id === alertId ? { ...a, ack } : a)) };
}

/** 확인이 끝난 알림을 목록에서 지우고 ID 를 기억한다 (같은 알림이 뒤늦게 다시 와도 걸러낸다). */
export function removeAlert(s: LiveState, alertId: string): LiveState {
  const ackedIds = [...s.ackedIds.filter((id) => id !== alertId), alertId].slice(-MAX_ACKED_IDS);
  return { ...s, alerts: s.alerts.filter((a) => a.alert_id !== alertId), ackedIds };
}

// --------------------------------------------------------------------------- //
// 접속 주소
// --------------------------------------------------------------------------- //
/**
 * VITE_WS_URL 과 구역 ID 로 접속 주소를 만든다. 서버 경로는 /ws/zones/{zone_id} 다 (docs/api-spec.md 2절).
 *   - 'ws://localhost:8080/ws/zones/{zone_id}' : {zone_id} 자리를 구역 ID 로 바꾼다 (구역 ID 가 없으면 접속하지 않는다)
 *   - 'ws://localhost:8080/ws/zones'           : 구역 ID 가 있으면 뒤에 붙인다
 *   - 'ws://localhost:8080/ws/zones/zone-x'    : 그대로 쓴다
 * 주소가 비어 있으면 '' (실시간 연결을 하지 않는다).
 */
export function resolveWsUrl(base: string, zoneId: string): string {
  const b = base.trim();
  const z = zoneId.trim();
  if (!b) return '';
  if (b.includes('{zone_id}')) return z ? b.replace('{zone_id}', encodeURIComponent(z)) : '';
  if (z && /\/ws\/zones\/?$/.test(b)) return `${b.replace(/\/$/, '')}/${encodeURIComponent(z)}`;
  return b;
}

/** WebSocket 주소에서 REST 서버 주소를 만든다 (ws://host:8080/... → http://host:8080). 해석할 수 없으면 '' (같은 출처). */
export function apiBaseFromWs(wsUrl: string): string {
  try {
    const u = new URL(wsUrl);
    const protocol = u.protocol === 'wss:' ? 'https:' : u.protocol === 'ws:' ? 'http:' : u.protocol;
    return `${protocol}//${u.host}`;
  } catch {
    return '';
  }
}
