import { useEffect, useRef, type CSSProperties } from 'react';
import { DENSITY_LEVELS, SEVERE_BLINK, UNOBSERVED } from '../config/density';
import { shouldBlink } from '../lib/density';
import { frameLabel } from '../lib/format';
import type { RegionSummary } from '../lib/region';
import type { Frame } from '../types/timeline';

export interface SelectedCellInfo {
  row: number;
  col: number;
  /** 명/m², null = 화각 밖 */
  value: number | null;
  label: string;
}

interface Props {
  /** null 이면 패널이 닫힌다 */
  region: RegionSummary | null;
  frame: Frame | undefined;
  /** 지도에서 클릭한 셀(같은 구역일 때만 표시) */
  cell?: SelectedCellInfo | null;
  onClose: () => void;
}

const fmt = (v: number | null, digits = 2) => (v === null ? '-' : v.toFixed(digits));

/**
 * 구역 상세 패널. region 이 있으면 열리고(슬라이드 인), null 이면 닫힌다.
 * - 데스크톱: 지도 오른쪽 사이드 패널 / 모바일: 아래에서 올라오는 시트 (CSS 미디어쿼리)
 * - 닫기: X 버튼 또는 Esc
 */
export function RegionPanel({ region, frame, cell, onClose }: Props) {
  // 닫히는 애니메이션 동안 내용이 사라지지 않도록 마지막 내용을 유지한다.
  const last = useRef<RegionSummary | null>(null);
  if (region) last.current = region;
  const shown = region ?? last.current;
  const open = region !== null;

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose();
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  const level = shown?.level ?? null;
  const soft = (level ?? UNOBSERVED).soft;
  const predicted = frame?.kind === 'predicted';
  const blink = shouldBlink(level, predicted);
  const observedRatio = shown && shown.totalCells > 0 ? shown.observedCells / shown.totalCells : 0;

  return (
    <aside
      className={`region-panel${open ? ' open' : ''}`}
      style={{ '--grade-bg': soft.bg, '--grade-ink': soft.ink, '--grade-dot': soft.dot } as CSSProperties}
      role="complementary"
      aria-label="구역 상세"
      aria-hidden={!open}
    >
      {shown && (
        <>
          <header className="rp-header">
            <div>
              <h2>{shown.zone.name}</h2>
              <small>{shown.zone.zone_id}</small>
            </div>
            <button type="button" className="rp-close" onClick={onClose} aria-label="상세 패널 닫기" tabIndex={open ? 0 : -1}>
              ✕
            </button>
          </header>

          <div className="rp-body">
            <div className="rp-grade">
              <span className="rp-grade-label">위험 단계</span>
              <strong
                className={`rp-badge${blink ? ' severe' : ''}`}
                style={blink ? { animationDuration: `${SEVERE_BLINK.periodMs}ms` } : undefined}
              >
                {level?.label ?? UNOBSERVED.label}
              </strong>
              <span className={`rp-frame${predicted ? ' predicted' : ''}`}>
                {frameLabel(frame)}
                {predicted && ' · 추정'}
              </span>
            </div>

            <dl className="rp-stats">
              <div>
                <dt>인원</dt>
                <dd>{shown.count === null ? '-' : `${Math.round(shown.count).toLocaleString()}명`}</dd>
              </div>
              <div>
                <dt>평균 밀도</dt>
                <dd>{fmt(shown.meanDensity)}<small> 명/m²</small></dd>
              </div>
              <div>
                <dt>최대 밀도</dt>
                <dd>
                  {fmt(shown.maxDensity)}<small> 명/m²</small>
                </dd>
                {shown.maxCell && (
                  <dd className="rp-sub">{shown.maxCell.row + 1}행 {shown.maxCell.col + 1}열</dd>
                )}
              </div>
              <div>
                <dt>관측 범위</dt>
                <dd>{Math.round(observedRatio * 100)}<small> %</small></dd>
                <dd className="rp-sub">{shown.observedCells}/{shown.totalCells}칸</dd>
              </div>
            </dl>

            <section aria-label="단계별 셀 분포">
              <h3>단계별 셀 분포</h3>
              <div className="rp-dist" role="img" aria-label={DENSITY_LEVELS.map((l, i) => `${l.label} ${shown.levelCounts[i]}칸`).join(', ')}>
                {DENSITY_LEVELS.map((l, i) =>
                  shown.levelCounts[i] > 0 ? (
                    <span key={l.label} style={{ flexGrow: shown.levelCounts[i], background: l.soft.dot }} />
                  ) : null,
                )}
              </div>
              <ul className="rp-dist-list">
                {DENSITY_LEVELS.map((l, i) => (
                  <li key={l.label}>
                    <span className="swatch" style={{ background: l.soft.dot }} />
                    {l.label}
                    <b>{shown.levelCounts[i]}칸</b>
                  </li>
                ))}
              </ul>
            </section>

            {cell && (
              <section className="rp-cell" aria-label="선택한 셀">
                <h3>선택한 셀</h3>
                <p>
                  <b>{cell.row + 1}행 {cell.col + 1}열</b>
                  <span>
                    {cell.value === null ? '화각 밖(미관측)' : `${cell.value.toFixed(2)} 명/m²`} · {cell.label}
                  </span>
                </p>
              </section>
            )}
          </div>
        </>
      )}
    </aside>
  );
}
