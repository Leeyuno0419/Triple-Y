import { levelOf } from './density';
import { cellBounds } from './grid';
import { DENSITY_LEVELS, type DensityLevel } from '../config/density';
import type { Frame, ZoneMeta } from '../types/timeline';

export interface LatLngPoint {
  lat: number;
  lng: number;
}

/** 사용자가 지도에서 직접 지정한 구역. 사각형도 꼭짓점 4개의 다각형으로 통일해서 다룬다. */
export interface CustomArea {
  shape: 'rect' | 'polygon' | 'circle';
  /** 사각형·다각형의 꼭짓점. 원형은 외곽을 근사한 다각형(표시·내보내기용) */
  path: LatLngPoint[];
  /** 원형 전용: 중심과 반경(m) */
  center?: LatLngPoint;
  radiusM?: number;
}

/** 드래그한 두 점(대각선)으로 사각형(BBox) 구역을 만든다. 꼭짓점은 북서→북동→남동→남서 순서. */
export function rectArea(a: LatLngPoint, b: LatLngPoint): CustomArea {
  const north = Math.max(a.lat, b.lat);
  const south = Math.min(a.lat, b.lat);
  const west = Math.min(a.lng, b.lng);
  const east = Math.max(a.lng, b.lng);
  return {
    shape: 'rect',
    path: [
      { lat: north, lng: west },
      { lat: north, lng: east },
      { lat: south, lng: east },
      { lat: south, lng: west },
    ],
  };
}

const M_PER_DEG_LAT = 110_540;
const M_PER_DEG_LNG_AT_EQUATOR = 111_320;

/** 두 지점 사이 거리(m). 구역 규모(수 km 이하)에서는 평면 근사로 충분하다. */
export function distanceM(a: LatLngPoint, b: LatLngPoint): number {
  const dy = (b.lat - a.lat) * M_PER_DEG_LAT;
  const dx = (b.lng - a.lng) * M_PER_DEG_LNG_AT_EQUATOR * Math.cos(((a.lat + b.lat) / 2) * (Math.PI / 180));
  return Math.hypot(dx, dy);
}

/** 중심점과 반경(m)으로 원형 구역을 만든다. path 는 외곽을 48각형으로 근사한 값. */
export function circleArea(center: LatLngPoint, radiusM: number): CustomArea {
  const path: LatLngPoint[] = [];
  const cos = Math.cos(center.lat * (Math.PI / 180));
  for (let i = 0; i < 48; i++) {
    const t = (i / 48) * 2 * Math.PI;
    path.push({
      lat: center.lat + (radiusM * Math.sin(t)) / M_PER_DEG_LAT,
      lng: center.lng + (radiusM * Math.cos(t)) / (M_PER_DEG_LNG_AT_EQUATOR * cos),
    });
  }
  return { shape: 'circle', path, center, radiusM };
}

/** 반경 표기: 1km 미만은 m, 이상은 km (예: 300m, 1.5km) */
export function formatRadius(m: number): string {
  return m < 1000 ? `${Math.round(m)}m` : `${Number((m / 1000).toFixed(2))}km`;
}

/** 사이드바에 보여 줄 구역 설명 (예: "원형 · 반경 300m") */
export function areaLabel(area: CustomArea): string {
  if (area.shape === 'rect') return '사각형';
  if (area.shape === 'circle' && area.radiusM) return `원형 · 반경 ${formatRadius(area.radiusM)}`;
  return `다각형 ${area.path.length}점`;
}

/** 점이 다각형 안에 있는가 (ray casting). 소규모 영역이라 위·경도를 평면 좌표로 본다. */
export function pointInPolygon(p: LatLngPoint, poly: LatLngPoint[]): boolean {
  let inside = false;
  for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
    const a = poly[i];
    const b = poly[j];
    const crosses = a.lat > p.lat !== b.lat > p.lat && p.lng < ((b.lng - a.lng) * (p.lat - a.lat)) / (b.lat - a.lat) + a.lng;
    if (crosses) inside = !inside;
  }
  return inside;
}

/** 셀의 중심이 구역 안에 있으면 그 셀은 구역에 포함된 것으로 본다. */
export function cellInArea(zone: ZoneMeta, row: number, col: number, area: CustomArea): boolean {
  const b = cellBounds(zone, row, col);
  const p = { lat: (b.north + b.south) / 2, lng: (b.west + b.east) / 2 };
  if (area.shape === 'circle' && area.center && area.radiusM) return distanceM(area.center, p) <= area.radiusM;
  return pointInPolygon(p, area.path);
}

export interface AreaSummary {
  /** 구역 안에 들어온 분석 셀 수 / 그중 관측된(화각 안) 셀 수 */
  cells: number;
  observedCells: number;
  meanDensity: number | null;
  maxDensity: number | null;
  level: DensityLevel | null;
  /** 구역 안 추정 인원 = Σ(셀 밀도 × 셀 면적). 관측된 셀만 합산 */
  people: number;
  /** 구역에 포함된 셀의 면적 합(㎡) */
  areaM2: number;
}

/** 한 프레임 기준으로 사용자 지정 구역의 밀도 지표를 요약한다. */
export function summarizeArea(zones: ZoneMeta[], frame: Frame | undefined, area: CustomArea): AreaSummary {
  let cells = 0;
  let observed = 0;
  let sum = 0;
  let max: number | null = null;
  let people = 0;
  let areaM2 = 0;

  for (const zone of zones) {
    const zf = frame?.zones.find((z) => z.zone_id === zone.zone_id);
    const cellArea = zone.cell_size_m * zone.cell_size_m;
    for (let row = 0; row < zone.rows; row++) {
      for (let col = 0; col < zone.cols; col++) {
        if (!cellInArea(zone, row, col, area)) continue;
        cells += 1;
        areaM2 += cellArea;
        const v = zf?.density[row]?.[col];
        if (v === null || v === undefined || !Number.isFinite(v)) continue;
        observed += 1;
        sum += v;
        people += v * cellArea;
        if (max === null || v > max) max = v;
      }
    }
  }

  return {
    cells,
    observedCells: observed,
    meanDensity: observed > 0 ? sum / observed : null,
    maxDensity: max,
    level: max === null ? null : DENSITY_LEVELS[DENSITY_LEVELS.indexOf(levelOf(max))],
    people,
    areaM2,
  };
}
