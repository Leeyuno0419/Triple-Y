/**
 * timeline.json 규격 타입.
 *
 * !! 가정(ASSUMPTION) !!
 * 기획서 3.4 / timeline.json 정식 규격을 확인하지 못해 임시로 가정한 구조다.
 * 규격 확정 시 이 파일과 src/predict/schema.py 두 곳만 수정한다.
 *
 * 좌표 규약: row 0 = 북쪽, col 0 = 서쪽. 셀 값이 null 이면 화각 밖(미관측).
 */
export const SCHEMA_MAJOR = '0';

export interface Bounds {
  south: number;
  west: number;
  north: number;
  east: number;
}

export interface ZoneMeta {
  zone_id: string;
  name: string;
  bounds: Bounds;
  rows: number;
  cols: number;
  cell_size_m: number;
}

/** (rows x cols) 격자. null = 화각 밖 */
export type Grid = Array<Array<number | null>>;

export interface ZoneFrame {
  zone_id: string;
  /** 구역 집계값(명) */
  count?: number | null;
  /** 셀 밀도(명/m²) */
  density: Grid;
  /** 셀 흐름(셀/초) */
  flow?: { u: Grid; v: Grid };
}

export type FrameKind = 'observed' | 'predicted';

export interface Frame {
  /** ISO8601 */
  t: string;
  kind: FrameKind;
  /** predicted 프레임일 때만: 마지막 관측으로부터의 예측 시간(초) */
  horizon_s?: number;
  zones: ZoneFrame[];
}

export interface Timeline {
  schema_version: string;
  zones: ZoneMeta[];
  frames: Frame[];
}
