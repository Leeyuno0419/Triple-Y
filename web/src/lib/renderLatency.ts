/**
 * G2 지연 검증용: 알림이 실제로 화면에 그려진 시각과 서버 frame_ts 의 차이를 브라우저 콘솔에 남긴다.
 *
 * G2 수용 기준은 "알림이 5초 이내에 화면에 표시된다" 이다 (docs/api-spec.md 7절, E8).
 * 서버가 받은 시각이 아니라 DOM 에 그려진 시각을 재야 하므로 시각을 세 군데에서 잡는다.
 *   frame_ts    서버가 그 초를 보낸 시각 (alert.frame_ts)
 *   receivedAt  WebSocket onmessage 에서 alert 를 받은 시각 (noteAlertReceived, useLiveFeed 가 호출)
 *   renderedAt  알림 행이 DOM 에 들어가고 브라우저가 한 번 그린 직후 (AlertFeed 가 호출)
 *
 * 지연 = renderedAt - frame_ts. 서버와 브라우저 시계가 같아야 의미가 있다 (같은 PC 의 localhost 이면 같다).
 * 다른 PC 에서 재면 시계 차이(NTP 오차)가 그대로 지연에 더해진다.
 *
 * hello.unacked_alerts 로 받은 알림은 이미 오래된 것이라 재지 않는다 (alert 메시지로 받은 알림만 잰다).
 */

/** G2 수용 기준: 서버가 보낸 뒤 화면에 표시되기까지 (ms) */
export const G2_LIMIT_MS = 5000;

/** 로그 앞에 붙이는 표식. 콘솔 필터에 이 문자열을 넣으면 이 로그만 본다. */
export const LATENCY_LOG_TAG = '[G2-latency]';

/** 기억하는 알림 ID 최대 개수 (화면에 한 번도 그려지지 않은 알림이 쌓여도 메모리가 늘지 않게) */
const MAX_TRACKED = 300;

/** alert_id → WebSocket 으로 받은 시각(ms). alert 메시지로 온 것만 담는다. */
const receivedAt = new Map<string, number>();
/** 이미 로그를 남긴 alert_id. 같은 알림이 다시 그려져도(화면 전환 등) 한 번만 남긴다. */
const logged = new Set<string>();

function trim<T>(coll: Map<string, T> | Set<string>): void {
  while (coll.size > MAX_TRACKED) {
    const oldest = coll.keys().next();
    if (oldest.done) return;
    coll.delete(oldest.value);
  }
}

/** frame_ts(ISO 8601, 예: 2026-11-18T14:02:32.508+09:00)를 epoch ms 로. 해석할 수 없으면 null. */
export function parseFrameTs(frameTs: string): number | null {
  if (!frameTs) return null;
  const ms = Date.parse(frameTs);
  return Number.isFinite(ms) ? ms : null;
}

/** alert 메시지를 받은 순간을 기록한다. 같은 알림이 두 번 와도 처음 시각만 남긴다. */
export function noteAlertReceived(alertId: string, atMs: number = Date.now()): void {
  if (receivedAt.has(alertId)) return;
  receivedAt.set(alertId, atMs);
  trim(receivedAt);
}

/** 이 알림의 수신 시각. alert 메시지로 받지 않았거나(hello 로 받음) 이미 로그를 남겼으면 undefined. */
export function pendingReceivedAt(alertId: string): number | undefined {
  return logged.has(alertId) ? undefined : receivedAt.get(alertId);
}

export interface RenderLatency {
  /** 서버가 보낸 시각 → 화면에 그려진 시각 (G2 판정 값). frame_ts 를 해석할 수 없으면 null */
  totalMs: number | null;
  /** 서버가 보낸 시각 → 브라우저가 받은 시각 (네트워크 + 서버 전송 큐) */
  networkMs: number | null;
  /** 브라우저가 받은 시각 → 화면에 그려진 시각 (React 상태 반영 + 렌더) */
  renderMs: number;
  /** total 이 G2 기준 이내인가. total 을 모르면 null */
  withinLimit: boolean | null;
}

/** 세 시각(epoch ms)으로 지연을 계산한다. */
export function computeRenderLatency(frameTsMs: number | null, receivedMs: number, renderedMs: number): RenderLatency {
  const totalMs = frameTsMs === null ? null : renderedMs - frameTsMs;
  return {
    totalMs,
    networkMs: frameTsMs === null ? null : receivedMs - frameTsMs,
    renderMs: renderedMs - receivedMs,
    withinLimit: totalMs === null ? null : totalMs <= G2_LIMIT_MS,
  };
}

interface LoggedAlert {
  alert_id: string;
  t: number;
  frame_ts: string;
  level: string;
  reason: string;
}

const ms = (v: number | null) => (v === null ? '?' : `${Math.round(v)}ms`);

/**
 * 알림이 화면에 그려진 뒤 콘솔에 한 줄 남긴다 (알림마다 한 번). G2 기준을 넘으면 console.warn.
 * renderedMs 는 그려진 직후의 Date.now() 다 (waitForPaint 가 정한다).
 */
export function logAlertRendered(alert: LoggedAlert, renderedMs: number): void {
  const received = receivedAt.get(alert.alert_id);
  if (received === undefined || logged.has(alert.alert_id)) return;
  logged.add(alert.alert_id);
  trim(logged);

  const frameTsMs = parseFrameTs(alert.frame_ts);
  const lat = computeRenderLatency(frameTsMs, received, renderedMs);
  const verdict = lat.withinLimit === null ? '판정 불가(frame_ts 없음)' : lat.withinLimit ? `OK ≤ ${G2_LIMIT_MS}ms` : `초과 > ${G2_LIMIT_MS}ms`;
  const line =
    `${LATENCY_LOG_TAG} ${alert.alert_id} ${alert.reason}/${alert.level} t=${alert.t} | ` +
    `frame_ts → 화면 표시 ${ms(lat.totalMs)} (수신까지 ${ms(lat.networkMs)} + 렌더 ${ms(lat.renderMs)}) · ${verdict}`;
  const detail = {
    alert_id: alert.alert_id,
    frame_ts: alert.frame_ts,
    received_at: new Date(received).toISOString(),
    rendered_at: new Date(renderedMs).toISOString(),
    total_ms: lat.totalMs,
    network_ms: lat.networkMs,
    render_ms: lat.renderMs,
    within_limit: lat.withinLimit,
    tab_hidden: typeof document !== 'undefined' ? document.hidden : null,
  };
  if (lat.withinLimit === false) console.warn(line, detail);
  else console.info(line, detail);
}

/**
 * 브라우저가 지금까지의 DOM 변경을 한 번 그린 직후에 cb(그 시각 ms)를 부른다. 취소 함수를 돌려준다.
 * requestAnimationFrame 콜백은 다음 그리기 직전에 돌고, 그 안에서 건 setTimeout 은 그 그리기가 끝난 뒤에 돈다.
 * 탭이 가려져 있으면 rAF 가 멈추므로 다시 보일 때까지 기다린다 (그때까지는 실제로 화면에 없다).
 */
export function waitForPaint(cb: (renderedMs: number) => void): () => void {
  let timer: ReturnType<typeof setTimeout> | undefined;
  const raf = requestAnimationFrame(() => {
    timer = setTimeout(() => cb(Date.now()), 0);
  });
  return () => {
    cancelAnimationFrame(raf);
    clearTimeout(timer);
  };
}
