import { createContext, useEffect, useRef, useState, type ReactNode } from 'react';
import { DEFAULT_CENTER, DEFAULT_MAP_LEVEL, KAKAO_JS_KEY } from '../config/app';
import { loadKakaoSdk } from '../lib/kakao';
import type { ZoneMeta } from '../types/timeline';

/** 지도 인스턴스를 레이어 컴포넌트(DensityLayer 등)에 전달한다. */
export const MapContext = createContext<kakao.maps.Map | null>(null);

interface Props {
  zones: ZoneMeta[];
  /** 지도 로드 실패(키 누락 등) 시 대신 보여줄 화면 */
  fallback?: ReactNode;
  children?: ReactNode;
}

export function KakaoMap({ zones, fallback, children }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [map, setMap] = useState<kakao.maps.Map | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    loadKakaoSdk(KAKAO_JS_KEY)
      .then(() => {
        if (cancelled || !containerRef.current) return;
        setMap(
          new kakao.maps.Map(containerRef.current, {
            center: new kakao.maps.LatLng(DEFAULT_CENTER.lat, DEFAULT_CENTER.lng),
            level: DEFAULT_MAP_LEVEL,
          }),
        );
      })
      .catch((e: Error) => !cancelled && setError(e.message));
    return () => {
      cancelled = true;
    };
  }, []);

  // 컨테이너 크기가 바뀌면(창 크기, 모바일 회전, 하단 컨트롤바 높이 변화 등) 지도를 다시 맞춘다.
  // relayout() 만 부르면 중심이 밀릴 수 있어 호출 전후로 중심을 유지한다.
  useEffect(() => {
    const el = containerRef.current;
    if (!map || !el || typeof ResizeObserver === 'undefined') return;
    let raf = 0;
    const ro = new ResizeObserver(() => {
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(() => {
        const center = map.getCenter();
        map.relayout();
        map.setCenter(center);
      });
    });
    ro.observe(el);
    return () => {
      ro.disconnect();
      cancelAnimationFrame(raf);
    };
  }, [map]);

  // 구역이 바뀌면 모든 구역이 보이도록 지도 범위를 맞춘다.
  useEffect(() => {
    if (!map || zones.length === 0) return;
    const bounds = new kakao.maps.LatLngBounds();
    for (const z of zones) {
      bounds.extend(new kakao.maps.LatLng(z.bounds.south, z.bounds.west));
      bounds.extend(new kakao.maps.LatLng(z.bounds.north, z.bounds.east));
    }
    map.setBounds(bounds, 60, 40, 60, 40);
  }, [map, zones]);

  if (error) {
    return (
      <div className="map-wrap">
        <div className="map-error" role="alert">
          지도를 불러오지 못했습니다: {error}
        </div>
        {fallback}
      </div>
    );
  }

  return (
    <div className="map-wrap">
      <div ref={containerRef} className="map" />
      <MapContext.Provider value={map}>{children}</MapContext.Provider>
    </div>
  );
}
