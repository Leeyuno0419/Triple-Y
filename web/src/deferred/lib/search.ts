import type { ZoneMeta } from '../types/timeline';

/**
 * 검색어가 구역 이름·구역 ID 에 들어 있는지 본다 (대소문자 무시).
 * 공백으로 나눈 단어가 모두 포함되어야 일치한다. 검색어가 비어 있으면 항상 일치.
 */
export function matchZone(zone: ZoneMeta, query: string): boolean {
  const tokens = query.toLowerCase().split(/\s+/).filter(Boolean);
  if (tokens.length === 0) return true;
  const hay = `${zone.name} ${zone.zone_id}`.toLowerCase();
  return tokens.every((t) => hay.includes(t));
}
