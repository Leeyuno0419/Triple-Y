import { DENSITY_LEVELS, UNOBSERVED } from '../config/density';
import type { ZoneSummary } from '../lib/region';

/** 단계별 셀 수 누적 막대 + 범례 */
export function GradeDistribution({ summary }: { summary: ZoneSummary }) {
  const total = Math.max(1, summary.totalCells);
  const none = Math.max(0, summary.totalCells - summary.observedCells);
  return (
    <>
      <div
        className="dist-bar"
        role="img"
        aria-label={DENSITY_LEVELS.map((l, i) => `${l.label} ${summary.levelCounts[i]}칸`).join(', ')}
      >
        {DENSITY_LEVELS.map((l, i) =>
          summary.levelCounts[i] > 0 ? (
            <span key={l.label} style={{ width: `${(summary.levelCounts[i] / total) * 100}%`, background: l.soft.dot }} />
          ) : null,
        )}
        {none > 0 && <span style={{ width: `${(none / total) * 100}%`, background: UNOBSERVED.soft.dot }} />}
      </div>
      <ul className="dist-legend">
        {DENSITY_LEVELS.map((l, i) => (
          <li key={l.label}>
            <span className="swatch" style={{ background: l.soft.dot }} />
            {l.label}
            <b>{summary.levelCounts[i]}</b>
          </li>
        ))}
      </ul>
    </>
  );
}
