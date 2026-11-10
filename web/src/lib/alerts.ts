import { DENSITY_LEVELS, RISK_MIN_LEVEL_INDEX, type DensityLevel } from '../config/density';
import type { Frame, ZoneMeta } from '../types/timeline';
import { levelOf } from './density';

/**
 * 프레임 이력에서 화면용 알림을 만들어 낸다.
 * !! 서버가 보내는 공식 알림이 아니라, 받은 프레임의 단계 변화를 클라이언트에서 해석한 것이다.
 *    알림 규격(기획서의 5초 이내 경보 등)이 확정되면 서버 알림을 받아 이 파생 로직을 대체한다.
 */
export type AlertKind = 'raise' | 'clear' | 'forecast';

export interface AlertItem {
  id: string;
  kind: AlertKind;
  /** 발생(또는 예측) 시각 ISO */
  t: string;
  zoneId: string;
  zoneName: string;
  level: DensityLevel;
  density: number;
  /** forecast 일 때: 마지막 관측으로부터의 시간(초) */
  horizon_s?: number;
}

const levelIndex = (v: number) => DENSITY_LEVELS.indexOf(levelOf(v));

function zoneMax(frame: Frame, zoneId: string): number | null {
  const zf = frame.zones.find((z) => z.zone_id === zoneId);
  if (!zf) return null;
  let max: number | null = null;
  for (const row of zf.density) for (const v of row) if (v !== null && Number.isFinite(v) && (max === null || v > max)) max = v;
  return max;
}

/**
 * - raise    : 관측에서 구역 단계가 올라 경고 이상이 됨(또는 더 높아짐)
 * - clear    : 경고 이상이던 구역이 그 아래로 내려감
 * - forecast : 예측 프레임에서 경고 이상(또는 현재보다 높은 단계)이 처음 예상되는 시점
 * 예측 알림이 먼저, 그 뒤로 최근 순.
 */
export function deriveAlerts(zones: ZoneMeta[], frames: Frame[], limit = 8): AlertItem[] {
  const observed = frames.filter((f) => f.kind === 'observed');
  const predicted = frames.filter((f) => f.kind === 'predicted');
  const past: AlertItem[] = [];
  const upcoming: AlertItem[] = [];

  for (const zone of zones) {
    let prev = -1;
    for (const f of observed) {
      const v = zoneMax(f, zone.zone_id);
      if (v === null) continue;
      const idx = levelIndex(v);
      if (idx >= RISK_MIN_LEVEL_INDEX && idx > prev) {
        past.push({ id: `raise:${zone.zone_id}:${f.t}`, kind: 'raise', t: f.t, zoneId: zone.zone_id, zoneName: zone.name, level: DENSITY_LEVELS[idx], density: v });
      } else if (prev >= RISK_MIN_LEVEL_INDEX && idx < RISK_MIN_LEVEL_INDEX) {
        past.push({ id: `clear:${zone.zone_id}:${f.t}`, kind: 'clear', t: f.t, zoneId: zone.zone_id, zoneName: zone.name, level: DENSITY_LEVELS[idx], density: v });
      }
      prev = idx;
    }

    // 예측: 마지막 관측 단계(prev) 대비 처음 위험 이상으로 올라가는 프레임 하나
    for (const f of predicted) {
      const v = zoneMax(f, zone.zone_id);
      if (v === null) continue;
      const idx = levelIndex(v);
      if (idx >= RISK_MIN_LEVEL_INDEX && idx > prev) {
        upcoming.push({ id: `forecast:${zone.zone_id}:${f.t}`, kind: 'forecast', t: f.t, zoneId: zone.zone_id, zoneName: zone.name, level: DENSITY_LEVELS[idx], density: v, horizon_s: f.horizon_s });
        break;
      }
    }
  }

  upcoming.sort((a, b) => (a.horizon_s ?? 0) - (b.horizon_s ?? 0));
  past.sort((a, b) => b.t.localeCompare(a.t));
  return [...upcoming, ...past].slice(0, limit);
}
