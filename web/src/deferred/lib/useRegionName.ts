import { useEffect, useState } from 'react';
import { KAKAO_JS_KEY } from '../config/app';
import { reverseRegion } from './place';

const cache = new Map<string, string | null>();
const UNKNOWN = '위치 정보 없음';

/**
 * 지도 중심 좌표의 지역 이름을 구한다 (예: "서울 중구 정동 일대").
 * 지도를 움직이는 동안 매번 요청하지 않도록 잠깐 기다렸다가 요청하고, 같은 위치는 캐시를 쓴다.
 */
export function useRegionName(center: { lat: number; lng: number } | null): string {
  const [name, setName] = useState('지도 중심 확인 중…');
  const lat = center?.lat;
  const lng = center?.lng;

  useEffect(() => {
    if (lat === undefined || lng === undefined) return;
    const key = `${lat.toFixed(3)},${lng.toFixed(3)}`;
    if (cache.has(key)) {
      setName(cache.get(key) ?? UNKNOWN);
      return;
    }
    let cancelled = false;
    const timer = setTimeout(() => {
      reverseRegion(lat, lng, KAKAO_JS_KEY)
        .then((n) => {
          cache.set(key, n);
          if (!cancelled) setName(n ?? UNKNOWN);
        })
        .catch(() => !cancelled && setName(UNKNOWN));
    }, 350);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [lat, lng]);

  return name;
}
