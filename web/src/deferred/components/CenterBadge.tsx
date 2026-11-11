import { useRegionName } from '../lib/useRegionName';
import { PinIcon } from './Icons';
import type { MapCenter } from './MapCenterTracker';

/** 📍 지금 지도 중심이 어느 지역인지 보여 주는 파스텔 위치 뱃지 */
export function CenterBadge({ center }: { center: MapCenter | null }) {
  const name = useRegionName(center);
  return (
    <div className="center-badge" title="지도 중심 위치" role="status">
      <PinIcon size={14} />
      <span>{name}</span>
    </div>
  );
}
