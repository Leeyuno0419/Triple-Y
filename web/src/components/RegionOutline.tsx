import { useContext, useEffect } from 'react';
import { REGION_OUTLINE } from '../config/density';
import type { ZoneMeta } from '../types/timeline';
import { MapContext } from './KakaoMap';

/**
 * 선택한 구역의 테두리를 지도에 강조한다.
 * 채움이 있는 Rectangle 이 아니라 Polyline 을 쓰는 이유: 구역 안쪽 셀의 클릭을 가로채지 않기 위해서.
 */
export function RegionOutline({ zone }: { zone: ZoneMeta | null }) {
  const map = useContext(MapContext);

  useEffect(() => {
    if (!map || !zone) return;
    const { south, west, north, east } = zone.bounds;
    const path = [
      new kakao.maps.LatLng(north, west),
      new kakao.maps.LatLng(north, east),
      new kakao.maps.LatLng(south, east),
      new kakao.maps.LatLng(south, west),
      new kakao.maps.LatLng(north, west),
    ];
    const line = new kakao.maps.Polyline({ map, path, ...REGION_OUTLINE });
    return () => line.setMap(null);
  }, [map, zone]);

  return null;
}
