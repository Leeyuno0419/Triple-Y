import { SCHEMA_MAJOR, type Frame, type Timeline, type ZoneMeta } from '../types/timeline';

/** 프레임 하나를 구역 메타에 대조해 검증한다. (환경변수/브라우저 API 의존 없는 순수 함수) */
export function validateFrame(fr: Frame, zones: ZoneMeta[]): Frame {
  if (!fr || typeof fr.t !== 'string' || !Array.isArray(fr.zones)) {
    throw new Error('프레임 형식 오류: t(문자열)와 zones 배열이 필요합니다.');
  }
  if (fr.kind !== 'observed' && fr.kind !== 'predicted') {
    throw new Error(`알 수 없는 frame.kind: ${String(fr.kind)}`);
  }
  const byId = new Map(zones.map((z) => [z.zone_id, z]));
  for (const zf of fr.zones) {
    const z = byId.get(zf.zone_id);
    if (!z) throw new Error(`알 수 없는 zone_id: ${zf.zone_id}`);
    if (!Array.isArray(zf.density) || zf.density.length !== z.rows || zf.density.some((row) => row.length !== z.cols)) {
      throw new Error(`density 격자 크기 불일치 (zone ${zf.zone_id}, 기대 ${z.rows}x${z.cols})`);
    }
  }
  return fr;
}

/** 최소 검증: 규격 불일치 데이터가 지도에서 조용히 깨지는 것을 막는다. */
export function validateTimeline(data: unknown): Timeline {
  const tl = data as Timeline;
  if (!tl || !Array.isArray(tl.zones) || !Array.isArray(tl.frames)) {
    throw new Error('timeline 형식 오류: zones/frames 배열이 필요합니다.');
  }
  if (String(tl.schema_version).split('.')[0] !== SCHEMA_MAJOR) {
    throw new Error(`지원하지 않는 schema_version: ${tl.schema_version}`);
  }
  for (const fr of tl.frames) validateFrame(fr, tl.zones);
  return tl;
}
