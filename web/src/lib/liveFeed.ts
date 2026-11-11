/**
 * 실시간(WebSocket) 메시지 규격과 반영 로직. 환경변수/브라우저 API 의존 없는 순수 함수.
 *
 * !! 가정(ASSUMPTION) !!
 * 서버(Spring Boot → WebSocket)의 메시지 규격이 정해지지 않아 아래처럼 가정했다.
 * 규격 확정 시 **이 파일의 parseLiveMessage / applyLiveMessage 만** 고치면 된다.
 *
 *   서버 → 클라이언트 (JSON 텍스트 프레임, 1초에 1회 이상)
 *   { "type": "timeline", "timeline": <Timeline> }      연결 직후 전체 상태 (zones 메타 포함)
 *   { "type": "frames",   "frames": [<Frame>, ...] }    갱신: 관측 1개 + 그에 대한 예측 N개를 한 묶음으로
 *   { "type": "frame",    "frame": <Frame> }            frames 의 단일 버전
 *   (type 없이 Timeline 객체 자체를 보내도 timeline 으로 취급)
 *
 * 반영 규칙
 *   - 묶음에 observed 프레임이 있으면 기존 predicted 프레임은 낡은 것이므로 모두 버린다.
 *   - 같은 t 의 observed 는 교체, observed 는 최대 maxObserved 개까지만 유지한다.
 */
import type { Frame, Timeline } from '../types/timeline';
import { validateFrame, validateTimeline } from './validate';

export type LiveMessage =
  | { type: 'timeline'; timeline: Timeline }
  | { type: 'frames'; frames: Frame[] };

/** 수신한 텍스트를 해석한다. 형식이 맞지 않으면 Error 를 던진다. */
export function parseLiveMessage(raw: string): LiveMessage {
  const obj = JSON.parse(raw) as Record<string, unknown>;
  if (!obj || typeof obj !== 'object') throw new Error('메시지가 객체가 아닙니다.');

  switch (obj.type) {
    case 'timeline':
      return { type: 'timeline', timeline: validateTimeline(obj.timeline) };
    case 'frames':
      if (!Array.isArray(obj.frames)) throw new Error('frames 배열이 필요합니다.');
      return { type: 'frames', frames: obj.frames as Frame[] };
    case 'frame':
      return { type: 'frames', frames: [obj.frame as Frame] };
    case undefined:
      return { type: 'timeline', timeline: validateTimeline(obj) };
    default:
      throw new Error(`알 수 없는 메시지 type: ${String(obj.type)}`);
  }
}

function trimObserved(frames: Frame[], maxObserved: number): Frame[] {
  let excess = frames.filter((f) => f.kind === 'observed').length - maxObserved;
  if (excess <= 0) return frames;
  return frames.filter((f) => !(f.kind === 'observed' && excess-- > 0));
}

/**
 * 메시지를 현재 timeline 에 반영한 새 timeline 을 돌려준다 (입력은 변경하지 않음).
 * frames 메시지인데 아직 timeline(zones 메타)이 없으면 null 을 돌려준다.
 */
export function applyLiveMessage(
  current: Timeline | null,
  msg: LiveMessage,
  maxObserved: number,
): Timeline | null {
  if (msg.type === 'timeline') {
    return { ...msg.timeline, frames: trimObserved(msg.timeline.frames, maxObserved) };
  }
  if (!current) return null;

  const incoming = msg.frames.map((f) => validateFrame(f, current.zones));
  let kept = current.frames;
  if (incoming.some((f) => f.kind === 'observed')) {
    kept = kept.filter((f) => f.kind !== 'predicted'); // 낡은 예측 폐기
    const newTimes = new Set(incoming.filter((f) => f.kind === 'observed').map((f) => f.t));
    kept = kept.filter((f) => !(f.kind === 'observed' && newTimes.has(f.t)));
  }
  return { ...current, frames: trimObserved([...kept, ...incoming], maxObserved) };
}
