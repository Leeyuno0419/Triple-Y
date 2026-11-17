import { DENSITY_LEVELS, RISK_MIN_LEVEL_INDEX, type DensityLevel } from '../config/density';
import type { Frame, Meta } from '../types/timeline';
import { levelOf } from './density';
import { frameMaxDensity } from './model';

/**
 * 프레임 이력에서 화면용 알림을 만들어 낸다.
 * !! 서버가 보내는 공식 알림이 아니라, 받은 프레임의 단계 변화를 클라이언트에서 해석한 것이다.
 *    서버(WebSocket)에 연결되면 서버 alert 를 보여 주고(AlertFeed 의 liveAlerts) 이 파생 알림은 쓰지 않는다.
 *    서버 없이 timeline 파일만 열었을 때만 이 파생 로직을 쓴다.
 */
export type AlertKind = 'raise' | 'clear' | 'forecast';

export interface AlertItem {
  id: string;
  kind: AlertKind;
  /** 발생 시각: 영상 시작 뒤 경과 초 (forecast 는 예측을 낸 시각) */
  t: number;
  level: DensityLevel;
  density: number;
  /** forecast 일 때: 예측 시점(초) */
  horizon_s?: number;
}

const levelIndex = (v: number) => DENSITY_LEVELS.indexOf(levelOf(v));

/**
 * - raise    : 구역 단계가 올라 경계 이상이 됨(또는 더 높아짐)
 * - clear    : 경계 이상이던 구역이 그 아래로 내려감
 * - forecast : 가장 최근 프레임의 60초 뒤 예측이 현재보다 높은 경계 이상 단계일 때 (한 건)
 * 예측 알림이 먼저, 그 뒤로 최근 순.
 */
export function deriveAlerts(meta: Meta, frames: Frame[], limit = 8): AlertItem[] {
  const past: AlertItem[] = [];
  let prev = -1;
  for (const f of frames) {
    const v = frameMaxDensity(f, 'now');
    if (v === null) continue;
    const idx = levelIndex(v);
    if (idx >= RISK_MIN_LEVEL_INDEX && idx > prev) {
      past.push({ id: `raise:${f.t}`, kind: 'raise', t: f.t, level: DENSITY_LEVELS[idx], density: v });
    } else if (prev >= RISK_MIN_LEVEL_INDEX && idx < RISK_MIN_LEVEL_INDEX) {
      past.push({ id: `clear:${f.t}`, kind: 'clear', t: f.t, level: DENSITY_LEVELS[idx], density: v });
    }
    prev = idx;
  }

  const upcoming: AlertItem[] = [];
  const last = frames[frames.length - 1];
  const pv = last ? frameMaxDensity(last, 'pred') : null;
  if (last && pv !== null) {
    const idx = levelIndex(pv);
    if (idx >= RISK_MIN_LEVEL_INDEX && idx > prev) {
      upcoming.push({
        id: `forecast:${last.t}`, kind: 'forecast', t: last.t, level: DENSITY_LEVELS[idx], density: pv,
        horizon_s: meta.prediction.horizon_s,
      });
    }
  }

  past.sort((a, b) => b.t - a.t);
  return [...upcoming, ...past].slice(0, limit);
}
