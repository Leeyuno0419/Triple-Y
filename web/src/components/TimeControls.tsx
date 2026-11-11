import { fmtClock } from '../lib/format';
import type { ViewMode } from '../lib/model';
import type { Frame } from '../types/timeline';

interface Props {
  frames: Frame[];
  index: number;
  playing: boolean;
  /** 지금 보여 주는 값: 관측 / 60초 뒤 예측 */
  mode: ViewMode;
  /** 예측 시점(초). 배지에 표시 */
  horizonS: number;
  onIndexChange: (index: number) => void;
  onTogglePlay: () => void;
}

export function TimeControls({ frames, index, playing, mode, horizonS, onIndexChange, onTogglePlay }: Props) {
  const frame = frames[index];
  if (!frame) return null;
  const predicted = mode === 'pred';

  return (
    <div className="time-controls">
      <button className="play" onClick={onTogglePlay} aria-label={playing ? '일시정지' : '재생'}>
        <svg viewBox="0 0 24 24" width="14" height="14" fill="currentColor" aria-hidden="true">
          {playing ? <path d="M7 5h3.5v14H7zM13.5 5H17v14h-3.5z" /> : <path d="M8 5.5v13l11-6.5z" />}
        </svg>
      </button>
      <input
        type="range"
        min={0}
        max={frames.length - 1}
        value={index}
        onChange={(e) => onIndexChange(Number(e.target.value))}
        aria-label="시간 이동"
      />
      <div className="time-label">
        <span>{fmtClock(frame.t)}</span>
        <span className={`badge ${predicted ? 'pred' : 'obs'}`}>{predicted ? `예측 +${horizonS}s` : '관측'}</span>
      </div>
    </div>
  );
}
