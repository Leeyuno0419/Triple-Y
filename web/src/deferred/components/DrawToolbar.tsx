import { CircleIcon, PolygonIcon, RectIcon } from './Icons';
import type { DrawMode } from './DrawLayer';

interface Props {
  mode: DrawMode;
  /** 이미 지정한 구역이 있는가 (있으면 "구역 해제" 버튼 표시) */
  hasArea: boolean;
  onMode: (mode: DrawMode) => void;
  onClear: () => void;
}

/** 지도 왼쪽 위의 "사용자 구역 지정" 도구: 사각형 / 다각형 그리기, 지정 해제 */
export function DrawToolbar({ mode, hasArea, onMode, onClear }: Props) {
  const toggle = (m: Exclude<DrawMode, 'off'>) => onMode(mode === m ? 'off' : m);
  return (
    <div className="draw-toolbar" role="toolbar" aria-label="사용자 구역 지정">
      <span className="draw-title">구역 지정</span>
      <button type="button" className={`draw-tool${mode === 'rect' ? ' active' : ''}`} aria-pressed={mode === 'rect'} onClick={() => toggle('rect')}>
        <RectIcon size={15} />
        사각형
      </button>
      <button type="button" className={`draw-tool${mode === 'polygon' ? ' active' : ''}`} aria-pressed={mode === 'polygon'} onClick={() => toggle('polygon')}>
        <PolygonIcon size={15} />
        다각형
      </button>
      <button type="button" className={`draw-tool${mode === 'circle' ? ' active' : ''}`} aria-pressed={mode === 'circle'} onClick={() => toggle('circle')}>
        <CircleIcon size={15} />
        원형
      </button>
      {hasArea && (
        <button type="button" className="draw-tool clear" onClick={onClear}>
          해제
        </button>
      )}
    </div>
  );
}
