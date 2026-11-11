import { VIDEO_BASE_URL } from '../config/app';
import type { Frame } from '../types/timeline';

/**
 * 영상 시간(video.currentTime)과 타임라인 시각 t(영상 시작 뒤 경과 초)를 맞추는 규칙. DOM 의존 없는 순수 함수.
 *
 * - 재생 중에는 영상이 시간의 기준이다: 영상 시각으로 프레임을 고른다 (frameIndexAtTime).
 * - 정지 중에 슬라이더로 프레임을 옮기면 영상을 그 t 로 옮긴다.
 * - 재생 중 영상과 t 가 1.0초 넘게 벌어지면 영상을 t 로 맞춘다 (docs/api-spec.md 6절).
 */
/** 재생 중 허용하는 영상-타임라인 시간 차(초). api-spec 6절의 1.0초 */
export const DRIFT_TOLERANCE_S = 1.0;
/** 정지 중 슬라이더 이동으로 보고 영상을 옮기는 최소 차이(초) */
export const SCRUB_EPS_S = 0.25;

/** meta.video_id 에 해당하는 영상 주소. 예: E04_022 → /videos/E04_022.mp4 */
export function videoUrl(videoId: string): string {
  return `${VIDEO_BASE_URL.replace(/\/+$/, '')}/${encodeURIComponent(videoId)}.mp4`;
}

/**
 * 영상 시각(초)에 해당하는 frames 배열 위치. 프레임은 1초 간격으로 t 가 연속이라고 본다
 * (파일은 t=0 부터, 실시간은 최근 N개라 frames[0].t 가 0 이 아닐 수 있다). 범위 밖이면 양 끝으로 맞춘다.
 */
export function frameIndexAtTime(frames: Frame[], sec: number): number {
  if (frames.length === 0) return 0;
  const idx = Math.floor(sec) - frames[0].t;
  return Math.min(Math.max(idx, 0), frames.length - 1);
}

export interface VideoSyncDecision {
  /** null 이 아니면 video.currentTime 을 이 값(초)으로 옮긴다 */
  seekTo: number | null;
  /** true 면 재생, false 면 정지 */
  play: boolean;
}

/** 지금 영상이 어떻게 움직여야 하는지 정한다. playing: 재생 중인가, currentTime: 영상 시각, t: 보여 주는 프레임의 t */
export function decideVideoSync(playing: boolean, currentTime: number, t: number): VideoSyncDecision {
  const drift = Math.abs(currentTime - t);
  if (playing) return { seekTo: drift > DRIFT_TOLERANCE_S ? t : null, play: true };
  return { seekTo: drift > SCRUB_EPS_S ? t : null, play: false };
}
