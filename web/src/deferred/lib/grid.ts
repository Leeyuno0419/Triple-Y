import type { Bounds, ZoneMeta } from '../types/timeline';

/** 셀 (row, col) 의 지리 경계. row 0 = 북쪽, col 0 = 서쪽. */
export function cellBounds(zone: ZoneMeta, row: number, col: number): Bounds {
  const { south, west, north, east } = zone.bounds;
  const latStep = (north - south) / zone.rows;
  const lngStep = (east - west) / zone.cols;
  return {
    north: north - row * latStep,
    south: north - (row + 1) * latStep,
    west: west + col * lngStep,
    east: west + (col + 1) * lngStep,
  };
}

/** 구역 중심에서 가로/세로 미터를 위·경도 차이로 환산 (소규모 영역용 근사). */
export function metersToDegrees(latitude: number, dxMeters: number, dyMeters: number) {
  const dLat = dyMeters / 111_320;
  const dLng = dxMeters / (111_320 * Math.cos((latitude * Math.PI) / 180));
  return { dLat, dLng };
}

/** 위·경도가 어느 구역의 어느 셀 안인지 찾는다. 어느 구역에도 없으면 null. */
export function cellAt(zones: ZoneMeta[], lat: number, lng: number): { zone_id: string; row: number; col: number } | null {
  for (const z of zones) {
    const { south, west, north, east } = z.bounds;
    if (lat < south || lat > north || lng < west || lng > east) continue;
    const row = Math.min(z.rows - 1, Math.floor(((north - lat) / (north - south)) * z.rows));
    const col = Math.min(z.cols - 1, Math.floor(((lng - west) / (east - west)) * z.cols));
    return { zone_id: z.zone_id, row, col };
  }
  return null;
}
