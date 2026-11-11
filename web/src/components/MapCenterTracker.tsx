import { useContext, useEffect, useRef } from 'react';
import { MapContext } from './KakaoMap';

export interface MapCenter {
  lat: number;
  lng: number;
}

/** 지도 이동이 끝날 때마다(idle) 지도 중심 좌표를 위로 알려 준다. 사이드바의 중심지 뱃지가 쓴다. */
export function MapCenterTracker({ onCenter }: { onCenter: (center: MapCenter) => void }) {
  const map = useContext(MapContext);
  const cb = useRef(onCenter);
  cb.current = onCenter;

  useEffect(() => {
    if (!map) return;
    const emit = () => {
      const c = map.getCenter();
      cb.current({ lat: c.getLat(), lng: c.getLng() });
    };
    kakao.maps.event.addListener(map, 'idle', emit);
    emit();
    return () => kakao.maps.event.removeListener(map, 'idle', emit);
  }, [map]);

  return null;
}
