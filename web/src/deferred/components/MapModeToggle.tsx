import type { ReactNode } from 'react';
import { FlameIcon, GridIcon, MapIcon } from './Icons';

/** 지도 시각화 모드: base = 기본 지도(밀도 레이어 없음), heat = 밀도 히트맵, grid = 셀 격자 */
export type MapMode = 'base' | 'heat' | 'grid';

const MODES: { id: MapMode; label: string; icon: ReactNode }[] = [
  { id: 'base', label: '기본 지도', icon: <MapIcon size={15} /> },
  { id: 'heat', label: '밀도 히트맵', icon: <FlameIcon size={15} /> },
  { id: 'grid', label: 'Grid 뷰', icon: <GridIcon size={15} /> },
];

interface Props {
  mode: MapMode;
  onChange: (mode: MapMode) => void;
}

/** 지도 왼쪽 위의 시각화 모드 전환 (슬림한 세그먼트 버튼 그룹) */
export function MapModeToggle({ mode, onChange }: Props) {
  return (
    <div className="mode-toggle" role="radiogroup" aria-label="지도 시각화 모드">
      {MODES.map((m) => (
        <button
          key={m.id}
          type="button"
          role="radio"
          aria-checked={mode === m.id}
          className={`mode-btn${mode === m.id ? ' active' : ''}`}
          onClick={() => onChange(m.id)}
        >
          {m.icon}
          <span>{m.label}</span>
        </button>
      ))}
    </div>
  );
}
