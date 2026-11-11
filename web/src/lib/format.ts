import type { Frame } from '../types/timeline';

/** "관측 · 10:00:05" / "예측 +60초 · 10:01:05" */
export function frameLabel(frame: Frame | undefined): string {
  if (!frame) return '';
  const time = new Date(frame.t).toLocaleTimeString('ko-KR', { hour12: false });
  return frame.kind === 'predicted' ? `예측 +${frame.horizon_s ?? '?'}초 · ${time}` : `관측 · ${time}`;
}

/** 화면 상단의 간결한 상태 표시 (● 실시간 / ● 관측 / ● 예측 / ● 지난 시점) */
export interface StatusInfo {
  text: string;
  kind: 'live' | 'obs' | 'pred' | 'past' | 'sim';
}

/** 시각 없이 프레임 종류만: "관측 데이터" / "예측 +60초 · 추정" */
export function frameKindLabel(frame: Frame | undefined): string {
  if (!frame) return '';
  return frame.kind === 'predicted' ? `예측 +${frame.horizon_s ?? '?'}초 · 추정` : '관측 데이터';
}
