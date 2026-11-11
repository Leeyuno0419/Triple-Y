import { SCHEMA_MAJOR, type Frame, type Meta, type Timeline } from '../types/timeline';

/**
 * timeline.json 규격 v0.1 검증 (docs/timeline-spec.md). src/predict/schema.py 의 validate_timeline 과 같은 규칙이다.
 * 환경변수/브라우저 API 의존 없는 순수 함수. 규격에 어긋나면 Error 를 던진다.
 */
const CELL_ID_RE = /^c-(\d{2})(\d{2})$/;
const CELL_FIELDS = ['vx', 'vy', 'speed_var', 'pressure', 'density_pred_60s'] as const;

const isObj = (v: unknown): v is Record<string, unknown> => typeof v === 'object' && v !== null && !Array.isArray(v);
const isNum = (v: unknown): v is number => typeof v === 'number' && Number.isFinite(v);

/** meta 를 검증한다. */
export function validateMeta(meta: unknown): Meta {
  if (!isObj(meta)) throw new Error('meta(객체)가 필요합니다.');
  for (const key of ['zone_id', 'camera_id', 'video_id', 'duration_s', 'interval_s', 'cell_size_m', 'models', 'prediction', 'cells']) {
    if (!(key in meta)) throw new Error(`meta.${key} 가 없습니다.`);
  }
  const pred = meta.prediction;
  if (!isObj(pred) || !Number.isInteger(pred.history_s) || (pred.history_s as number) < 1 || !isNum(pred.horizon_s)) {
    throw new Error('meta.prediction 은 history_s(1 이상 정수)와 horizon_s 가 필요합니다.');
  }
  if (!Array.isArray(meta.cells)) throw new Error('meta.cells 는 배열이어야 합니다.');

  const seen = new Set<string>();
  for (const c of meta.cells as unknown[]) {
    if (!isObj(c)) throw new Error('meta.cells 항목이 객체가 아닙니다.');
    const id = c.cell_id;
    const m = typeof id === 'string' ? CELL_ID_RE.exec(id) : null;
    if (!m) throw new Error(`cell_id 형식 오류: ${String(id)} (c-행2자리열2자리)`);
    if (Number(m[1]) !== c.row || Number(m[2]) !== c.col) throw new Error(`cell_id ${id} 와 row/col 이 다릅니다.`);
    if (!isNum(c.walkable_area_m2) || c.walkable_area_m2 <= 0) throw new Error(`${id}: walkable_area_m2 는 0보다 커야 합니다.`);
    const poly = c.image_polygon;
    const okPoly =
      Array.isArray(poly) && poly.length === 4 &&
      poly.every((p) => Array.isArray(p) && p.length === 2 && p.every((x) => isNum(x) && x >= 0 && x <= 1));
    if (!okPoly) throw new Error(`${id}: image_polygon 은 0~1 좌표 4개여야 합니다.`);
    if (seen.has(id as string)) throw new Error('meta.cells 에 중복 cell_id 가 있습니다.');
    seen.add(id as string);
  }
  return meta as unknown as Meta;
}

/**
 * 프레임 하나를 meta 에 대조해 검증한다. 실시간으로 받은 프레임에도 쓴다.
 * 예측 입력이 history_s 초 미만(t < history_s - 1)이면 density_pred_60s 는 null 이어야 한다.
 */
export function validateFrame(fr: unknown, meta: Meta): Frame {
  if (!isObj(fr) || !Number.isInteger(fr.t) || (fr.t as number) < 0 || !Array.isArray(fr.cells)) {
    throw new Error('프레임 형식 오류: t(0 이상 정수)와 cells 배열이 필요합니다.');
  }
  const t = fr.t as number;
  const ratio = fr.inflow_ratio;
  if (ratio !== null && ratio !== undefined && !(isNum(ratio) && ratio >= 0 && ratio <= 1)) {
    throw new Error(`t=${t}: inflow_ratio 는 0~1 또는 null 입니다.`);
  }
  const cells = fr.cells as unknown[];
  if (cells.length !== meta.cells.length) throw new Error(`t=${t}: cells 개수가 meta.cells 와 다릅니다.`);
  const predMinT = meta.prediction.history_s - 1;

  cells.forEach((c, i) => {
    const id = meta.cells[i].cell_id;
    if (!isObj(c) || c.cell_id !== id) throw new Error(`t=${t}: cells 는 meta.cells 와 같은 순서여야 합니다 (${id}).`);
    if (!isNum(c.density)) throw new Error(`t=${t} ${id}: density 는 숫자여야 합니다.`);
    for (const key of CELL_FIELDS) {
      const v = c[key];
      if (v === undefined) throw new Error(`t=${t} ${id}: ${key} 필드가 없습니다 (아직 없으면 null).`);
      if (v !== null && !isNum(v)) throw new Error(`t=${t} ${id}: ${key} 는 숫자 또는 null 입니다.`);
    }
    if (t < predMinT && c.density_pred_60s !== null) {
      throw new Error(`t=${t} ${id}: t < ${predMinT} 이면 density_pred_60s 는 null 입니다.`);
    }
  });
  return { t, inflow_ratio: (ratio as number | null | undefined) ?? null, cells: cells as Frame['cells'] };
}

export interface ValidateOptions {
  /**
   * true 면 일부 프레임만 담긴 타임라인(실시간 연결 직후의 빈 frames 등)을 허용한다:
   * duration_s = frames 개수와 t 가 0부터 빠짐없이 증가해야 한다는 조건을 검사하지 않는다 (t 는 증가해야 한다).
   */
  partial?: boolean;
}

/** 타임라인 전체를 검증한다. */
export function validateTimeline(data: unknown, opts: ValidateOptions = {}): Timeline {
  if (!isObj(data) || !isObj(data.meta) || !Array.isArray(data.frames)) {
    throw new Error('timeline 형식 오류: meta(객체)와 frames(배열)가 필요합니다.');
  }
  if (String(data.schema_version).split('.')[0] !== SCHEMA_MAJOR) {
    throw new Error(`지원하지 않는 schema_version: ${String(data.schema_version)}`);
  }
  const meta = validateMeta(data.meta);
  const frames = (data.frames as unknown[]).map((f) => validateFrame(f, meta));
  if (!opts.partial) {
    if (meta.duration_s !== frames.length) {
      throw new Error(`meta.duration_s(${meta.duration_s}) 와 frames 개수(${frames.length}) 가 다릅니다.`);
    }
    frames.forEach((f, i) => {
      if (f.t !== i) throw new Error(`frames[${i}].t 는 ${i} 이어야 합니다 (0부터 빠짐없이 증가).`);
    });
  } else {
    frames.forEach((f, i) => {
      if (i > 0 && f.t <= frames[i - 1].t) throw new Error('frames 의 t 는 증가해야 합니다.');
    });
  }
  return { schema_version: String(data.schema_version), meta, frames };
}
