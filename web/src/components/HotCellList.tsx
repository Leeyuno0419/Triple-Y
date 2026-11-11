import type { HotCell } from '../lib/dashboard';
import { GradeBadge } from './GradeBadge';

interface Props {
  cells: HotCell[];
  predicted?: boolean;
  onSelect: (cellId: string) => void;
  emptyText?: string;
}

/** 고밀도 셀 목록 (밀도 내림차순으로 넘긴다). 홈과 모니터 사이드바에서 함께 쓴다. */
export function HotCellList({ cells, predicted = false, onSelect, emptyText }: Props) {
  if (cells.length === 0) return <p className="empty">{emptyText ?? '조건에 맞는 셀이 없습니다.'}</p>;
  return (
    <ol className="hot-list">
      {cells.map((c, i) => (
        <li key={c.meta.cell_id}>
          <button type="button" onClick={() => onSelect(c.meta.cell_id)}>
            <span className="rank">{i + 1}</span>
            <span className="hc-main">{c.meta.row + 1}행 {c.meta.col + 1}열 <small>{c.meta.cell_id}</small></span>
            <b>{c.value.toFixed(2)}</b>
            <GradeBadge level={c.level} predicted={predicted} />
          </button>
        </li>
      ))}
    </ol>
  );
}
