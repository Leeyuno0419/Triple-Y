import { useContext, useEffect } from 'react';
import { ZONE_OUTLINE } from '../config/density';
import type { ZoneMeta } from '../types/timeline';
import { MapContext } from './KakaoMap';

/** 기본 지도 모드에서 데이터가 있는 구역의 위치만 가는 점선 테두리로 알려 준다 (밀도 색은 칠하지 않음). */
export function ZoneBounds({ zones, active, hiddenZones }: { zones: ZoneMeta[]; active: boolean; hiddenZones?: Set<string> }) {
  const map = useContext(MapContext);

  useEffect(() => {
    if (!map || !active) return;
    const lines = zones
      .filter((z) => !hiddenZones?.has(z.zone_id))
      .map((z) => {
        const { south, west, north, east } = z.bounds;
        const path = [
          new kakao.maps.LatLng(north, west),
          new kakao.maps.LatLng(north, east),
          new kakao.maps.LatLng(south, east),
          new kakao.maps.LatLng(south, west),
          new kakao.maps.LatLng(north, west),
        ];
        return new kakao.maps.Polyline({ map, path, ...ZONE_OUTLINE });
      });
    return () => lines.forEach((l) => l.setMap(null));
  }, [map, active, zones, hiddenZones]);

  return null;
}
