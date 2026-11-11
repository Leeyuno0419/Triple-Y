/**
 * timeline.json 규격 v0.1 타입.
 *
 * 기준 문서: docs/timeline-spec.md (확정 v0.1, 11-11).
 * 규격이 바뀌면 이 파일과 src/predict/schema.py 두 곳을 함께 수정한다.
 *
 * - 파일 1개 = 영상 1개 = 구역 1개 = 카메라 1대. 분석 간격 1초.
 * - 값이 없으면 null 이다. 0은 실제로 측정한 0일 때만 쓴다.
 * - 셀·구역 집계값만 담는다. 등급·알림은 서버가 판정하며 파일에 없다.
 */
export const SCHEMA_MAJOR = '0';

/** 영상 가로·세로로 나눈 0~1 좌표 [x, y] */
export type Point = [number, number];

export interface Models {
  /** 예: "p2pnet-vgg16" */
  counter: string;
  /** 예: "farneback" */
  flow: string;
  /** 예: "persistence" */
  predictor: string;
}

export interface PredictionMeta {
  /** 예측 입력 기간(초). 30 */
  history_s: number;
  /** 예측 시점(초). 60 */
  horizon_s: number;
}

/** meta.cells[] — 셀 고정 정보 */
export interface CellMeta {
  /** "c-{행 2자리}{열 2자리}". c-0412 는 4행 12열 */
  cell_id: string;
  /** 0부터 */
  row: number;
  /** 0부터 */
  col: number;
  /** 보행 가능 면적(㎡). 0인 셀은 목록에서 뺀다 */
  walkable_area_m2: number;
  /** 영상 위에 히트맵을 그릴 셀 네 모서리 */
  image_polygon: [Point, Point, Point, Point];
}

/** 파일당 1번 나오는 고정 정보 */
export interface Meta {
  zone_id: string;
  camera_id: string;
  /** 원본 영상 이름. 화면이 재생할 영상을 찾는 값 */
  video_id: string;
  /** 분석 길이(초). frames 개수와 같다 */
  duration_s: number;
  /** 분석 간격(초). MVP 에서는 1 */
  interval_s: number;
  /** 셀 한 변 길이(m). 기본 2 */
  cell_size_m: number;
  models: Models;
  prediction: PredictionMeta;
  cells: CellMeta[];
}

/** frames[].cells[] — 1초 시점의 셀 상태 */
export interface CellState {
  cell_id: string;
  /** ρ 밀도(명/㎡) */
  density: number;
  /** V 속도 x성분(m/s). 사람이 없으면 null */
  vx: number | null;
  /** V 속도 y성분(m/s). 사람이 없으면 null */
  vy: number | null;
  /** Var(v) 속도 분산(m²/s²) */
  speed_var: number | null;
  /** P = ρ × Var(v) 불안정 지표(1/s²) */
  pressure: number | null;
  /** ρ(t+60) 60초 뒤 밀도 예측(명/㎡). 예측 입력이 30초 미만(t < 29)이면 null */
  density_pred_60s: number | null;
}

/** 1초에 1개 */
export interface Frame {
  /** 영상 시작 뒤 경과 시간(초). 0부터 빠짐없이 증가 */
  t: number;
  /** 화각 경계에서 안쪽으로 향하는 흐름 비율(0~1). 구역 전체 값 */
  inflow_ratio: number | null;
  /** meta.cells 와 같은 순서로 모든 셀을 담는다 */
  cells: CellState[];
}

export interface Timeline {
  schema_version: string;
  meta: Meta;
  frames: Frame[];
}
