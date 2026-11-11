import { DENSITY_LEVELS, UNOBSERVED } from '../config/density';
import type { Dashboard } from '../lib/dashboard';

/** 단계별 구역 수 누적 막대 + 범례 */
export function GradeDistribution({ dash }: { dash: Dashboard }) {
  const total = Math.max(1, dash.zones.length);
  return (
    <>
      <div
        className="dist-bar"
        role="img"
        aria-label={DENSITY_LEVELS.map((l, i) => `${l.label} ${dash.zonesPerLevel[i]}곳`).join(', ')}
      >
        {DENSITY_LEVELS.map((l, i) =>
          dash.zonesPerLevel[i] > 0 ? (
            <span key={l.label} style={{ width: `${(dash.zonesPerLevel[i] / total) * 100}%`, background: l.soft.dot }} />
          ) : null,
        )}
        {dash.unobservedZones > 0 && (
          <span style={{ width: `${(dash.unobservedZones / total) * 100}%`, background: UNOBSERVED.soft.dot }} />
        )}
      </div>
      <ul className="dist-legend">
        {DENSITY_LEVELS.map((l, i) => (
          <li key={l.label}>
            <span className="swatch" style={{ background: l.soft.dot }} />
            {l.label}
            <b>{dash.zonesPerLevel[i]}</b>
          </li>
        ))}
      </ul>
    </>
  );
}
