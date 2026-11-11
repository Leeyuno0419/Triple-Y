import { useEffect, useRef, type CSSProperties } from 'react';
import { DENSITY_LEVELS, SEVERE_BLINK, UNOBSERVED, type DensityLevel } from '../config/density';
import { shouldBlink } from '../lib/density';
import { modeLabel } from '../lib/format';
import type { ViewMode } from '../lib/model';
import type { ZoneSummary } from '../lib/region';
import type { CellMeta, CellState } from '../types/timeline';

export interface SelectedCellInfo {
  meta: CellMeta;
  state: CellState;
  /** 현재 모드의 밀도(명/m²), 없으면 null */
  value: number | null;
  level: DensityLevel | null;
}

interface Props {
  /** 구역 요약 (현재 프레임·모드 기준) */
  summary: ZoneSummary;
  /** null 이면 패널이 닫힌다 */
  cell: SelectedCellInfo | null;
  mode: ViewMode;
  onClose: () => void;
}

const fmt = (v: number | null | undefined, digits = 2) => (v === null || v === undefined ? '-' : v.toFixed(digits));

/**
 * 선택한 셀의 상세 패널. cell 이 있으면 열리고(슬라이드 인), null 이면 닫힌다.
 * - 데스크톱: 히트맵 오른쪽 위 플로팅 카드 / 모바일: 아래에서 올라오는 시트 (CSS 미디어쿼리)
 * - 닫기: X 버튼 또는 Esc
 */
export function RegionPanel({ summary, cell, mode, onClose }: Props) {
  // 닫히는 애니메이션 동안 내용이 사라지지 않도록 마지막 내용을 유지한다.
  const last = useRef<SelectedCellInfo | null>(null);
  if (cell) last.current = cell;
  const shown = cell ?? last.current;
  const open = cell !== null;

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose();
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  const level = shown?.level ?? null;
  const soft = (level ?? UNOBSERVED).soft;
  const predicted = mode === 'pred';
  const blink = shouldBlink(level, predicted);
  const meta = summary.meta;

  const st = shown?.state;
  const speed = st && st.vx !== null && st.vy !== null ? Math.hypot(st.vx, st.vy) : null;
  const people = shown && shown.value !== null ? shown.value * shown.meta.walkable_area_m2 : null;

  return (
    <aside
      className={`region-panel${open ? ' open' : ''}`}
      style={{ '--grade-bg': soft.bg, '--grade-ink': soft.ink, '--grade-dot': soft.dot } as CSSProperties}
      role="complementary"
      aria-label="셀 상세"
      aria-hidden={!open}
    >
      {shown && st && (
        <>
          <header className="rp-header">
            <div>
              <h2>{shown.meta.row + 1}행 {shown.meta.col + 1}열</h2>
              <small>{shown.meta.cell_id} · {meta.zone_id}</small>
            </div>
            <button type="button" className="rp-close" onClick={onClose} aria-label="상세 패널 닫기" tabIndex={open ? 0 : -1}>
              ✕
            </button>
          </header>

          <div className="rp-body">
            <div className="rp-grade">
              <span className="rp-grade-label">셀 위험 단계</span>
              <strong
                className={`rp-badge${blink ? ' severe' : ''}`}
                style={blink ? { animationDuration: `${SEVERE_BLINK.periodMs}ms` } : undefined}
              >
                {level?.label ?? UNOBSERVED.label}
              </strong>
              <span className={`rp-frame${predicted ? ' predicted' : ''}`}>{modeLabel(mode, meta.prediction.horizon_s)}</span>
            </div>

            <dl className="rp-stats">
              <div>
                <dt>밀도 ρ</dt>
                <dd>{fmt(shown.value)}<small> 명/m²</small></dd>
              </div>
              <div>
                <dt>{meta.prediction.horizon_s}초 뒤 예측</dt>
                <dd>{fmt(st.density_pred_60s)}<small> 명/m²</small></dd>
              </div>
              <div>
                <dt>속도 V</dt>
                <dd>{fmt(speed)}<small> m/s</small></dd>
                <dd className="rp-sub">vx {fmt(st.vx)} · vy {fmt(st.vy)}</dd>
              </div>
              <div>
                <dt>속도 분산 Var(v)</dt>
                <dd>{fmt(st.speed_var, 4)}<small> m²/s²</small></dd>
              </div>
              <div>
                <dt>불안정 지표 P</dt>
                <dd>{fmt(st.pressure, 4)}<small> 1/s²</small></dd>
              </div>
              <div>
                <dt>보행 가능 면적</dt>
                <dd>{fmt(shown.meta.walkable_area_m2, 1)}<small> ㎡</small></dd>
                <dd className="rp-sub">셀 추정 {people === null ? '-' : `${people.toFixed(1)}명`}</dd>
              </div>
            </dl>

            <section aria-label="구역 요약">
              <h3>구역 요약 · {meta.camera_id}</h3>
              <dl className="rp-stats">
                <div>
                  <dt>추정 인원</dt>
                  <dd>{summary.count === null ? '-' : `${Math.round(summary.count).toLocaleString()}명`}</dd>
                </div>
                <div>
                  <dt>경계 유입 비율</dt>
                  <dd>{summary.inflowRatio === null ? '-' : Math.round(summary.inflowRatio * 100)}<small> %</small></dd>
                </div>
                <div>
                  <dt>평균 밀도</dt>
                  <dd>{fmt(summary.meanDensity)}<small> 명/m²</small></dd>
                </div>
                <div>
                  <dt>최대 밀도</dt>
                  <dd>{fmt(summary.maxDensity)}<small> 명/m²</small></dd>
                  {summary.maxCell && <dd className="rp-sub">{summary.maxCell.row + 1}행 {summary.maxCell.col + 1}열</dd>}
                </div>
              </dl>
            </section>

            <section aria-label="단계별 셀 분포">
              <h3>단계별 셀 분포</h3>
              <div className="rp-dist" role="img" aria-label={DENSITY_LEVELS.map((l, i) => `${l.label} ${summary.levelCounts[i]}칸`).join(', ')}>
                {DENSITY_LEVELS.map((l, i) =>
                  summary.levelCounts[i] > 0 ? (
                    <span key={l.label} style={{ flexGrow: summary.levelCounts[i], background: l.soft.dot }} />
                  ) : null,
                )}
              </div>
              <ul className="rp-dist-list">
                {DENSITY_LEVELS.map((l, i) => (
                  <li key={l.label}>
                    <span className="swatch" style={{ background: l.soft.dot }} />
                    {l.label}
                    <b>{summary.levelCounts[i]}칸</b>
                  </li>
                ))}
              </ul>
            </section>
          </div>
        </>
      )}
    </aside>
  );
}
