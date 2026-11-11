import { SEVERE_BLINK } from '../config/density';
import { cellStyle } from '../lib/density';
import type { Frame, ZoneMeta } from '../types/timeline';
import { cellKey, type CellRef } from './DensityLayer';

interface Props {
  zones: ZoneMeta[];
  frame: Frame | undefined;
  selected?: CellRef | null;
  /** 상세 패널에서 선택된 구역 (테두리 강조) */
  selectedRegion?: string | null;
  onCellSelect?: (cell: CellRef) => void;
}

/**
 * 카카오 지도 없이 같은 색상 규칙으로 셀 격자를 보여주는 폴백.
 * (JS 키 미설정/도메인 미등록 상태에서도 레이어 로직을 확인할 수 있다.)
 */
export function GridPreview({ zones, frame, selected, selectedRegion, onCellSelect }: Props) {
  return (
    <div className="grid-preview">
      {zones.map((zone) => {
        const zf = frame?.zones.find((z) => z.zone_id === zone.zone_id);
        return (
          <section key={zone.zone_id} className={selectedRegion === zone.zone_id ? 'region-selected' : undefined}>
            <h3>{zone.name}</h3>
            <div className="grid" style={{ gridTemplateColumns: `repeat(${zone.cols}, 1fr)` }}>
              {Array.from({ length: zone.rows }, (_, row) =>
                Array.from({ length: zone.cols }, (_, col) => {
                  const value = zf?.density[row]?.[col] ?? null;
                  const s = cellStyle(value, frame?.kind === 'predicted');
                  const isSel =
                    selected?.zone_id === zone.zone_id && selected.row === row && selected.col === col;
                  return (
                    <button
                      key={cellKey(zone.zone_id, row, col)}
                      className={`cell${isSel ? ' selected' : ''}${s.predicted ? ' predicted' : ''}${s.blink ? ' severe' : ''}`}
                      style={{
                        background: s.color,
                        ...(s.blink ? { animationDuration: `${SEVERE_BLINK.periodMs}ms` } : {}),
                        opacity: Math.max(s.opacity + 0.3, 0.35),
                        ...(s.predicted ? { borderColor: s.color } : {}),
                      }}
                      aria-label={`${row + 1}행 ${col + 1}열 ${s.label}`}
                      onClick={() => onCellSelect?.({ zone_id: zone.zone_id, row, col })}
                    />
                  );
                }),
              )}
            </div>
          </section>
        );
      })}
    </div>
  );
}
