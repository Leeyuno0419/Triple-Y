/**
 * 서버 등급(Grade) ↔ 화면 단계(DensityLevel) 변환.
 *
 * 규칙: 서버가 판정한 등급이 있으면 **그대로** 쓰고 화면에서 다시 계산하지 않는다 (docs/api-spec.md 1절).
 * 서버 없이 timeline 파일만 열었거나(등급 키가 없음) 서버 등급이 null 인데 밀도는 있는 셀만 밀도 경계값으로 해석한다.
 */
import { DENSITY_LEVELS, type DensityLevel } from '../config/density';
import { GRADES, type Grade } from '../types/grade';
import type { Thresholds } from '../types/live';
import type { CellState } from '../types/timeline';
import { levelOf } from './density';
import type { ViewMode } from './model';

/** 서버 등급 코드 → 화면 단계. DENSITY_LEVELS 와 순서가 같다 (정상·주의·경계·심각). */
export function gradeLevel(grade: Grade | null | undefined): DensityLevel | null {
  if (!grade) return null;
  return DENSITY_LEVELS[GRADES.indexOf(grade)] ?? null;
}

/** 등급이 높을수록 큰 수. null 은 -1 (판정 없음). */
export const gradeRank = (grade: Grade | null | undefined): number => (grade ? GRADES.indexOf(grade) : -1);

/** 알 수 없는 값은 null 로 둔다 (서버가 새 등급을 추가해도 화면이 깨지지 않게). */
export function parseGrade(value: unknown): Grade | null {
  return typeof value === 'string' && (GRADES as readonly string[]).includes(value) ? (value as Grade) : null;
}

/**
 * 셀의 화면 단계. value 는 cellValue(state, mode) 로 얻은 밀도(없으면 null).
 * - 서버 등급이 있으면 그 값을 그대로 쓴다.
 * - 등급이 없거나(timeline 파일) null 인데 밀도는 있으면, bounds(서버 hello.thresholds 경계값, 없으면 기본 설정)로 해석한다.
 *   liveFeed 는 등급 키를 항상 채우므로(모르면 null), null 을 '값 없음'으로 보면 밀도가 있는 예측 셀이 회색으로 빠진다.
 */
export function cellLevel(
  state: CellState, mode: ViewMode, value: number | null, bounds?: number[],
): DensityLevel | null {
  if (value === null) return null;
  const grade = mode === 'pred' ? state.grade_pred_60s : state.grade;
  return gradeLevel(grade) ?? levelOf(value, bounds);
}

/** hello.thresholds → 범례·그래프 기준선용 경계값 [주의, 경계, 심각]. 없으면 undefined(기본 설정을 쓴다). */
export function thresholdBounds(thresholds: Thresholds | null | undefined): number[] | undefined {
  if (!thresholds) return undefined;
  const { caution, alert, critical } = thresholds.density;
  return [caution, alert, critical];
}
