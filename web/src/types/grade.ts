/**
 * 서버가 판정한 등급 코드 (docs/api-spec.md 4.1절).
 * 화면은 이 값을 그대로 표시한다. 밀도 임계값으로 다시 판정하지 않는다.
 */
export type Grade = 'NORMAL' | 'CAUTION' | 'ALERT' | 'CRITICAL';

/** 낮은 단계부터. config/density.ts 의 DENSITY_LEVELS 와 같은 순서(정상·주의·경계·심각)다. */
export const GRADES: readonly Grade[] = ['NORMAL', 'CAUTION', 'ALERT', 'CRITICAL'];
