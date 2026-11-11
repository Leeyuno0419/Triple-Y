/**
 * 국내/해외 판정과 해외 샘플 장소.
 * 국내 = 대한민국 영토를 감싸는 위·경도 상자(제주·울릉도·독도 포함)로 근사한다.
 * 상자라서 대마도 등 국경 바로 밖 일부도 국내로 판정될 수 있다 (시뮬레이션 전환 용도로는 충분).
 */
const KOREA_BOX = { south: 32.0, north: 39.0, west: 124.0, east: 132.2 };

export function isDomestic(lat: number, lng: number): boolean {
  return lat >= KOREA_BOX.south && lat <= KOREA_BOX.north && lng >= KOREA_BOX.west && lng <= KOREA_BOX.east;
}

export interface OverseasSample {
  name: string;
  lat: number;
  lng: number;
  /** 검색어로 쓸 수 있는 이름 (소문자) */
  aliases: string[];
}

/** 해외 가상 시뮬레이션을 체험할 수 있는 샘플 장소 (카카오 장소 검색은 해외를 지원하지 않아 직접 둔다). 좌표는 대략적인 위치. */
export const OVERSEAS_SAMPLES: OverseasSample[] = [
  { name: '시부야 스크램블 교차로 (도쿄)', lat: 35.65951, lng: 139.70045, aliases: ['도쿄', '시부야', 'tokyo', 'shibuya'] },
  { name: '타임스스퀘어 (뉴욕)', lat: 40.75798, lng: -73.98554, aliases: ['뉴욕', '타임스스퀘어', '타임스퀘어', 'new york', 'newyork', 'times square'] },
  { name: '피카딜리 서커스 (런던)', lat: 51.51004, lng: -0.13441, aliases: ['런던', '피카딜리', 'london', 'piccadilly'] },
  { name: '에펠탑 광장 (파리)', lat: 48.85837, lng: 2.29448, aliases: ['파리', '에펠탑', 'paris', 'eiffel'] },
  { name: '마리나 베이 (싱가포르)', lat: 1.28236, lng: 103.85875, aliases: ['싱가포르', '마리나베이', 'singapore', 'marina bay'] },
];

/** 검색어가 해외 샘플 장소의 이름이나 별칭과 맞으면 그 장소를 돌려준다. */
export function findOverseasSample(query: string): OverseasSample | null {
  const q = query.trim().toLowerCase();
  if (!q) return null;
  return OVERSEAS_SAMPLES.find((s) => s.name.toLowerCase().includes(q) || s.aliases.some((a) => a.includes(q) || q.includes(a))) ?? null;
}
