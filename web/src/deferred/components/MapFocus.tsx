import { useContext, useEffect } from 'react';
import type { ZoneMeta } from '../types/timeline';
import { MapContext } from './KakaoMap';

export interface FocusTarget {
  zone: ZoneMeta;
  /** 같은 구역을 다시 눌러도 다시 이동하도록 하는 번호 */
  seq: number;
}

/** 대시보드 목록에서 구역을 고르면 지도를 그 구역으로 이동한다. (지도에서 직접 클릭할 때는 움직이지 않는다) */
export function MapFocus({ target }: { target: FocusTarget | null }) {
  const map = useContext(MapContext);
  useEffect(() => {
    if (!map || !target) return;
    const { south, west, north, east } = target.zone.bounds;
    // 다음 프레임에 실행: (1) 지도 최초 생성 시 KakaoMap 의 전체 보기보다 나중에 적용되고,
    // (2) 숨겨져 있던 지도 뷰가 막 보이게 된 경우 크기를 다시 잰 뒤 이동한다.
    const raf = requestAnimationFrame(() => {
      map.relayout();
      const bounds = new kakao.maps.LatLngBounds();
      bounds.extend(new kakao.maps.LatLng(south, west));
      bounds.extend(new kakao.maps.LatLng(north, east));
      map.setBounds(bounds, 70, 40, 70, 40);
    });
    return () => cancelAnimationFrame(raf);
  }, [map, target]);
  return null;
}
