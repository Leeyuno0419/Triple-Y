import type { Frame } from '../types/timeline';

/** "관측 · 10:00:05" / "예측 +60초 · 10:01:05" */
export function frameLabel(frame: Frame | undefined): string {
  if (!frame) return '';
  const time = new Date(frame.t).toLocaleTimeString('ko-KR', { hour12: false });
  return frame.kind === 'predicted' ? `예측 +${frame.horizon_s ?? '?'}초 · ${time}` : `관측 · ${time}`;
}
