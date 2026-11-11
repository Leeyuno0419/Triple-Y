import { useContext, useEffect } from 'react';
import { MapContext } from './KakaoMap';

export interface PlaceTarget {
  name: string;
  lat: number;
  lng: number;
  /** 같은 장소를 다시 검색해도 다시 이동하도록 하는 번호 */
  seq: number;
}

const PLACE_MAP_LEVEL = 3;

/** 장소 검색 결과 위치로 지도를 이동하고 마커를 표시한다. target 이 바뀌거나 null 이 되면 마커를 지운다. */
export function MapPlace({ target }: { target: PlaceTarget | null }) {
  const map = useContext(MapContext);

  useEffect(() => {
    if (!map || !target) return;
    const position = new kakao.maps.LatLng(target.lat, target.lng);
    const marker = new kakao.maps.Marker({ map, position, title: target.name });
    // 다음 프레임에 이동: 지도 뷰가 막 보이게 된 경우 크기를 다시 잰 뒤 움직인다.
    const raf = requestAnimationFrame(() => {
      map.relayout();
      map.setLevel(PLACE_MAP_LEVEL);
      map.setCenter(position);
    });
    return () => {
      cancelAnimationFrame(raf);
      marker.setMap(null);
    };
  }, [map, target]);

  return null;
}
