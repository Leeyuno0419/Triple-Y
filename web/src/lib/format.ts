import type { ViewMode } from './model';

/** 영상 시작 뒤 경과 초 → "m:ss" (예: 75 → "1:15") */
export function fmtClock(t: number): string {
  const s = Math.max(0, Math.floor(t));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
}

/** 화면 상단의 간결한 상태 표시 (● 실시간 / ● 관측 / ● 예측 / ● 지난 시점) */
export interface StatusInfo {
  text: string;
  kind: 'live' | 'obs' | 'pred' | 'past';
}

/** 표시 모드 이름: "관측 데이터" / "예측 +60초 · 추정" */
export function modeLabel(mode: ViewMode, horizonS: number): string {
  return mode === 'pred' ? `예측 +${horizonS}초 · 추정` : '관측 데이터';
}
