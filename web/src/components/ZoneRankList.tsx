import { DENSITY_BAR_MAX, UNOBSERVED } from '../config/density';
import type { RegionSummary } from '../lib/region';
import { GradeBadge } from './GradeBadge';
import { ChevronIcon, PinIcon } from './Icons';

interface Props {
  zones: RegionSummary[];
  predicted?: boolean;
  selectedId?: string | null;
  onSelect: (zoneId: string) => void;
  /** 주어지면 각 행에 "지도에 표시" 체크박스가 붙는다 (지도 뷰의 구역 필터) */
  hidden?: Set<string>;
  onToggle?: (zoneId: string) => void;
  emptyText?: string;
}

const fmt = (v: number | null) => (v === null ? '-' : v.toFixed(2));

/** 구역 목록(최대 밀도 순으로 정렬해서 넘긴다). 홈의 순위, 지도 사이드바의 필터에서 함께 쓴다. */
export function ZoneRankList({ zones, predicted = false, selectedId, onSelect, hidden, onToggle, emptyText }: Props) {
  if (zones.length === 0) return <p className="empty">{emptyText ?? '구역 데이터가 없습니다.'}</p>;
  return (
    <ul className="zone-list">
      {zones.map((s, i) => {
        const id = s.zone.zone_id;
        const soft = (s.level ?? UNOBSERVED).soft;
        const ratio = Math.min((s.maxDensity ?? 0) / DENSITY_BAR_MAX, 1);
        return (
          <li key={id} className={`zone-row${selectedId === id ? ' selected' : ''}`}>
            {onToggle && hidden && (
              <label className="zr-check" title="지도에 표시">
                <input type="checkbox" checked={!hidden.has(id)} onChange={() => onToggle(id)} aria-label={`${s.zone.name} 지도에 표시`} />
              </label>
            )}
            <button type="button" className="zr-open" onClick={() => onSelect(id)}>
              {!onToggle && <span className="zr-rank">{i + 1}</span>}
              <span className="zr-icon" style={{ background: soft.bg, color: soft.ink }}>
                <PinIcon size={16} />
              </span>
              <span className="zr-main">
                <strong>{s.zone.name}</strong>
                <small>
                  {s.count === null ? '-' : `${Math.round(s.count).toLocaleString()}명`} · 평균 {fmt(s.meanDensity)}
                </small>
                <span className="zr-bar"><i style={{ width: `${ratio * 100}%`, background: soft.dot }} /></span>
              </span>
              <span className="zr-end">
                <b>{fmt(s.maxDensity)}</b>
                <GradeBadge level={s.level} predicted={predicted} />
              </span>
              <ChevronIcon size={16} />
            </button>
          </li>
        );
      })}
    </ul>
  );
}
