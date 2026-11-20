import { DENSITY_LEVELS, SEVERE_BLINK, UNOBSERVED } from '../config/density';
import { isSevereLevel } from '../lib/density';

/**
 * 밀도 범례. bounds 는 서버가 hello 로 알려 준 단계 경계값 [주의, 경계, 심각]이며 표시에만 쓴다 (판정은 서버가 한다).
 * 없으면 config/density.ts 의 기본값을 쓴다.
 */
export function Legend({ bounds }: { bounds?: number[] }) {
  const upper = (i: number) => (i < DENSITY_LEVELS.length - 1 ? (bounds?.[i] ?? DENSITY_LEVELS[i].max) : Infinity);
  return (
    <ul className="legend" aria-label="밀도 범례">
      {DENSITY_LEVELS.map((level, i) => {
        const min = i === 0 ? 0 : upper(i - 1);
        const max = upper(i);
        const range = Number.isFinite(max) ? `${min}–${max}` : `${min}+`;
        return (
          <li key={level.label}>
            <span
              className={`swatch${SEVERE_BLINK.enabled && isSevereLevel(level) ? ' blink' : ''}`}
              style={{ background: level.color, animationDuration: `${SEVERE_BLINK.periodMs}ms` }}
            />
            {level.label}
            <small>{range}</small>
          </li>
        );
      })}
      <li>
        <span className="swatch" style={{ background: UNOBSERVED.color, opacity: 0.5 }} />
        {UNOBSERVED.label}
      </li>
    </ul>
  );
}
