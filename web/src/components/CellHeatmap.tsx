import { SEVERE_BLINK } from '../config/density';
import { cellStyle } from '../lib/density';
import { cellValue, pairCells, type ViewMode } from '../lib/model';
import type { Frame, Meta } from '../types/timeline';

interface Props {
  meta: Meta;
  /** 보여 줄 프레임 (없으면 값 없는 셀로 그린다) */
  frame: Frame | undefined;
  mode: ViewMode;
  /** 선택한 셀의 cell_id */
  selectedCellId: string | null;
  onCellSelect: (cellId: string) => void;
}

/**
 * 영상 위 셀 히트맵 (기획서 MVP 화면). 셀 사각형은 meta.cells[].image_polygon(영상 가로·세로 0~1 좌표)으로 그린다.
 * 지금은 영상이 연결되어 있지 않아 어두운 배경 위에 셀만 그린다.
 * 영상을 붙일 때는 .hm-stage 안, 이 SVG 아래에 <video> 를 두면 같은 좌표계로 겹친다 (meta.video_id 로 영상을 찾는다).
 */
export function CellHeatmap({ meta, frame, mode, selectedCellId, onCellSelect }: Props) {
  const predicted = mode === 'pred';
  const pairs = pairCells(meta, frame);
  const byId = new Map(pairs.map((p) => [p.meta.cell_id, p.state]));

  return (
    <div className="hm-wrap">
      <div className="hm-stage">
        <p className="hm-note">영상 연결 전 · {meta.video_id}</p>
        <svg className="hm-svg" viewBox="0 0 1 1" preserveAspectRatio="none" role="group" aria-label="셀 히트맵">
          {meta.cells.map((cm) => {
            const state = byId.get(cm.cell_id);
            const value = state ? cellValue(state, mode) : null;
            const s = cellStyle(value, predicted);
            const selected = cm.cell_id === selectedCellId;
            const label = `${cm.row + 1}행 ${cm.col + 1}열 · ${value === null ? '값 없음' : `${value.toFixed(2)} 명/m²`} · ${s.label}`;
            return (
              <polygon
                key={cm.cell_id}
                className={`hm-cell${selected ? ' selected' : ''}${s.predicted ? ' predicted' : ''}${s.blink ? ' severe' : ''}`}
                points={cm.image_polygon.map(([x, y]) => `${x},${y}`).join(' ')}
                fill={s.color}
                fillOpacity={Math.min(1, s.opacity + 0.25)}
                stroke={s.strokeColor}
                strokeOpacity={s.strokeOpacity}
                strokeWidth={s.strokeWeight}
                strokeDasharray={s.predicted ? '5 3' : undefined}
                style={s.blink ? { animationDuration: `${SEVERE_BLINK.periodMs}ms` } : undefined}
                tabIndex={0}
                role="button"
                aria-label={label}
                aria-pressed={selected}
                onClick={() => onCellSelect(cm.cell_id)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    onCellSelect(cm.cell_id);
                  }
                }}
              >
                <title>{label}</title>
              </polygon>
            );
          })}
        </svg>
      </div>
    </div>
  );
}
