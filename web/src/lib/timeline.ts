import { TIMELINE_URL, USE_MOCK } from '../config/app';
import type { Timeline } from '../types/timeline';
import { makeMockTimeline } from './mock';
import { validateTimeline } from './validate';

export { validateTimeline };

export interface LoadResult {
  timeline: Timeline;
  source: 'server' | 'mock' | 'live';
}

export async function loadTimeline(signal?: AbortSignal): Promise<LoadResult> {
  try {
    const res = await fetch(TIMELINE_URL, { signal, cache: 'no-store' });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return { timeline: validateTimeline(await res.json()), source: 'server' };
  } catch (err) {
    if (signal?.aborted) throw err;
    if (!USE_MOCK) throw err;
    console.warn('[timeline] 서버 로드 실패, mock 사용:', err);
    return { timeline: makeMockTimeline(), source: 'mock' };
  }
}
