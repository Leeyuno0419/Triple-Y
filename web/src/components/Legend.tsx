import { DENSITY_LEVELS, SEVERE_BLINK, UNOBSERVED } from '../config/density';
import { isSevereLevel } from '../lib/density';

export function Legend() {
  return (
    <ul className="legend" aria-label="밀도 범례">
      {DENSITY_LEVELS.map((level, i) => {
        const min = i === 0 ? 0 : DENSITY_LEVELS[i - 1].max;
        const range = Number.isFinite(level.max) ? `${min}–${level.max}` : `${min}+`;
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
      <li title="예측 프레임은 같은 색을 반투명·점선으로 표시합니다">
        <span className="swatch predicted" />
        예측
      </li>
    </ul>
  );
}
