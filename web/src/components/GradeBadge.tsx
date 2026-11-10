import type { CSSProperties } from 'react';
import { SEVERE_BLINK, UNOBSERVED, type DensityLevel } from '../config/density';
import { shouldBlink } from '../lib/density';

/** 단계별 파스텔 배지. level 이 null 이면 '화각 밖'. 심각이면 깜빡인다(예측 프레임 제외). */
export function GradeBadge({ level, predicted = false }: { level: DensityLevel | null; predicted?: boolean }) {
  const soft = (level ?? UNOBSERVED).soft;
  const blink = shouldBlink(level, predicted);
  return (
    <span
      className={`gbadge${blink ? ' severe' : ''}`}
      style={
        {
          '--b-bg': soft.bg,
          '--b-ink': soft.ink,
          '--b-dot': soft.dot,
          ...(blink ? { animationDuration: `${SEVERE_BLINK.periodMs}ms` } : {}),
        } as CSSProperties
      }
    >
      {level?.label ?? UNOBSERVED.label}
    </span>
  );
}
