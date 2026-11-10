import type { Frame } from '../types/timeline';

interface Props {
  frames: Frame[];
  index: number;
  playing: boolean;
  onIndexChange: (index: number) => void;
  onTogglePlay: () => void;
}

const fmtTime = (iso: string) =>
  new Date(iso).toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false });

export function TimeControls({ frames, index, playing, onIndexChange, onTogglePlay }: Props) {
  const frame = frames[index];
  if (!frame) return null;
  const predicted = frame.kind === 'predicted';

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
        <span>{fmtTime(frame.t)}</span>
        <span className={`badge ${predicted ? 'pred' : 'obs'}`}>
          {predicted ? `예측 +${frame.horizon_s ?? '?'}s` : '관측'}
        </span>
      </div>
    </div>
  );
}
