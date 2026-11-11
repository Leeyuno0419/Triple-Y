/**
 * timeline.json 규격 v0.2 타입.
 *
 * 기준 문서: docs/timeline-spec.md (확정 v0.2, 11-11).
 * 규격이 바뀌면 이 파일, lib/validate.ts 와 src/predict/schema.py 를 함께 수정한다.
 *
 * v0.1 → v0.2: frames[].count(구역 인원)와 frames[].cells[].counterflow(역방향 비율) 추가.
 * 추가만 했으므로 v0.1 파일도 읽는다. lib/validate.ts 가 읽을 때 빠진 두 필드를 null 로 채우므로,
 * 이 타입을 쓰는 코드는 v0.1·v0.2 를 구분하지 않고 두 필드를 항상 있는 것(값은 null 가능)으로 다룬다.
 *
 * - 파일 1개 = 영상 1개 = 구역 1개 = 카메라 1대. 분석 간격 1초.
 * - 값이 없으면 null 이다. 0은 실제로 측정한 0일 때만 쓴다.
 * - 셀·구역 집계값만 담는다. 등급·알림은 서버가 판정하며 파일에 없다.
 */
export const SCHEMA_MAJOR = '0';
/** 이 코드가 만들고 기대하는 규격 버전 */
export const SCHEMA_VERSION = '0.2';
/** count, counterflow 가 들어온 버전. 이 버전부터 두 필드는 필수(값은 null 가능)이고, v0.1 에서는 없어도 된다. */
export const SCHEMA_V02_MINOR = 2;

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
  /** B 역방향 비율(0~1). 셀 평균 흐름과 반대로 움직이는 픽셀 비율. 주 흐름이 없거나 아직 만들지 않았으면 null (v0.2) */
  counterflow: number | null;
  /** ρ(t+60) 60초 뒤 밀도 예측(명/㎡). 예측 입력이 30초 미만(t < 29)이면 null */
  density_pred_60s: number | null;
}

/** 1초에 1개 */
export interface Frame {
  /** 영상 시작 뒤 경과 시간(초). 0부터 빠짐없이 증가 */
  t: number;
  /** 화각 경계에서 안쪽으로 향하는 흐름 비율(0~1). 구역 전체 값 */
  inflow_ratio: number | null;
  /** 구역 인원(명) = 셀 인원의 합. 5장 평균이라 소수. 아직 만들지 않았으면 null (v0.2) */
  count: number | null;
  /** meta.cells 와 같은 순서로 모든 셀을 담는다 */
  cells: CellState[];
}

export interface Timeline {
  schema_version: string;
  meta: Meta;
  frames: Frame[];
}
