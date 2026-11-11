import type { ZoneMeta } from '../types/timeline';

/**
 * 관심 구역(즐겨찾기). 이동할 위치(lat, lng)는 항상 있고, 밀도 데이터가 있는 구역이면 zoneId 로 연결된다.
 * zoneId 가 있으면 클릭 시 그 구역의 실시간 데이터(지도 뷰 + 구역 상세)로, 없으면 지도만 그 위치로 이동한다.
 */
export interface Favorite {
  id: string;
  name: string;
  lat: number;
  lng: number;
  zoneId?: string;
}

interface Stored {
  items: Favorite[];
  /** 처음 한 번만 기본 목록을 채우기 위한 표시 (사용자가 다 지워도 다시 채우지 않는다) */
  seeded: boolean;
}

const STORAGE_KEY = 'crowd.favorites.v1';

/** 처음 사용할 때 채워 주는 예시 장소 (밀도 데이터가 연결되어 있지 않다). 목록에서 지울 수 있다. */
export const EXAMPLE_PLACES: Favorite[] = [
  { id: 'place:37.55704,126.92441', name: '홍대입구역', lat: 37.55704, lng: 126.92441 },
  { id: 'place:37.49794,127.02764', name: '강남역 메인거리', lat: 37.49794, lng: 127.02764 },
  { id: 'place:35.65951,139.70045', name: '시부야 스크램블 교차로 (도쿄)', lat: 35.65951, lng: 139.70045 },
  { id: 'place:40.75798,-73.98554', name: '타임스스퀘어 (뉴욕)', lat: 40.75798, lng: -73.98554 },
];

export function zoneFavorite(zone: ZoneMeta): Favorite {
  const b = zone.bounds;
  return { id: `zone:${zone.zone_id}`, name: zone.name, lat: (b.south + b.north) / 2, lng: (b.west + b.east) / 2, zoneId: zone.zone_id };
}

export function placeFavorite(name: string, lat: number, lng: number): Favorite {
  return { id: `place:${lat.toFixed(5)},${lng.toFixed(5)}`, name, lat, lng };
}

const isFavorite = (v: unknown): v is Favorite => {
  const f = v as Favorite;
  return !!f && typeof f.id === 'string' && typeof f.name === 'string' && Number.isFinite(f.lat) && Number.isFinite(f.lng);
};

/** localStorage 에서 읽는다. 막혀 있거나(비공개 모드 등) 형식이 맞지 않으면 빈 상태로 시작한다. */
export function loadFavorites(): Stored {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return { items: [], seeded: false };
    const parsed = JSON.parse(raw) as Partial<Stored>;
    return { items: Array.isArray(parsed.items) ? parsed.items.filter(isFavorite) : [], seeded: parsed.seeded === true };
  } catch {
    return { items: [], seeded: false };
  }
}

export function saveFavorites(state: Stored): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  } catch {
    /* 저장 공간을 쓸 수 없으면 이번 접속 동안만 유지된다 */
  }
}
