/**
 * 실시간(WebSocket) 메시지 규격과 반영 로직. 환경변수/브라우저 API 의존 없는 순수 함수.
 *
 * !! 가정(ASSUMPTION) !!
 * 서버(Spring Boot → WebSocket)의 메시지 규격이 정해지지 않아(docs/timeline-spec.md 8절 6번) 아래처럼 가정했다.
 * 규격 확정 시 **이 파일의 parseLiveMessage / applyLiveMessage 만** 고치면 된다.
 *
 *   서버 → 클라이언트 (JSON 텍스트 프레임, 1초에 1회 이상)
 *   { "type": "timeline", "timeline": <Timeline> }     연결 직후 meta + (지금까지의) frames
 *   { "type": "frames",   "frames": [<Frame>, ...] }   갱신: 새 프레임 N개
 *   { "type": "frame",    "frame": <Frame> }           frames 의 단일 버전
 *   (type 없이 Timeline 객체 자체를 보내도 timeline 으로 취급)
 *
 * 반영 규칙
 *   - 같은 t 의 프레임은 교체하고, t 오름차순을 유지한다.
 *   - 프레임은 최대 maxFrames 개까지만 유지한다 (오래된 것부터 버림).
 *   - 영상이 처음으로 돌아가 t 가 줄어들면(재생 반복) 서버가 timeline 메시지를 다시 보내 초기화한다고 가정한다.
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
      return { type: 'timeline', timeline: validateTimeline(obj.timeline, { partial: true }) };
    case 'frames':
      if (!Array.isArray(obj.frames)) throw new Error('frames 배열이 필요합니다.');
      return { type: 'frames', frames: obj.frames as Frame[] };
    case 'frame':
      return { type: 'frames', frames: [obj.frame as Frame] };
    case undefined:
      return { type: 'timeline', timeline: validateTimeline(obj, { partial: true }) };
    default:
      throw new Error(`알 수 없는 메시지 type: ${String(obj.type)}`);
  }
}

function keepLast(frames: Frame[], maxFrames: number): Frame[] {
  return frames.length > maxFrames ? frames.slice(frames.length - maxFrames) : frames;
}

/**
 * 메시지를 현재 timeline 에 반영한 새 timeline 을 돌려준다 (입력은 변경하지 않음).
 * frames 메시지인데 아직 timeline(meta)이 없으면 null 을 돌려준다.
 */
export function applyLiveMessage(current: Timeline | null, msg: LiveMessage, maxFrames: number): Timeline | null {
  if (msg.type === 'timeline') {
    return { ...msg.timeline, frames: keepLast(msg.timeline.frames, maxFrames) };
  }
  if (!current) return null;

  const incoming = msg.frames.map((f) => validateFrame(f, current.meta));
  const newTimes = new Set(incoming.map((f) => f.t));
  const merged = [...current.frames.filter((f) => !newTimes.has(f.t)), ...incoming].sort((a, b) => a.t - b.t);
  return { ...current, frames: keepLast(merged, maxFrames) };
}
