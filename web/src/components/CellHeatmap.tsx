import { useEffect, useRef, useState, type CSSProperties } from 'react';
import { DEBUG_GRID } from '../config/app';
import { CELL_STYLE, HEATMAP_OVERLAY, SEVERE_BLINK } from '../config/density';
import { DebugGrid } from './DebugGrid';
import { cellStyle } from '../lib/density';
import { cellValue, pairCells, type ViewMode } from '../lib/model';
import { decideVideoSync } from '../lib/video';
import type { Frame, Meta } from '../types/timeline';

/** 영상 상태: none = 영상 주소 없음, loading = 불러오는 중, ready = 재생 가능, error = 못 찾았거나 재생 실패 */
export type VideoStatus = 'none' | 'loading' | 'ready' | 'error';

interface Props {
  meta: Meta;
  /** 보여 줄 프레임 (없으면 값 없는 셀로 그린다) */
  frame: Frame | undefined;
  mode: ViewMode;
  /** 선택한 셀의 cell_id */
  selectedCellId: string | null;
  onCellSelect: (cellId: string) => void;
  /** 영상 주소 (meta.video_id 로 만든다). 없으면 영상 없이 셀만 그린다 */
  videoSrc?: string;
  /** 보여 주는 프레임의 t = 영상 시각(초). 정지 중에는 영상이 이 시각으로 이동한다 */
  t: number;
  /** 재생 중인가. 재생 중에는 영상이 시간의 기준이 된다 */
  playing: boolean;
  /** 재생 중 영상 시각(초)이 바뀔 때 */
  onVideoTime?: (sec: number) => void;
  onVideoStatus?: (status: VideoStatus) => void;
  onVideoEnded?: () => void;
}

/** 영상 크기를 알기 전 기본 화면 비율 (16:9) */
const DEFAULT_ASPECT = 16 / 9;

/**
 * 영상 위 셀 히트맵 (기획서 MVP 화면).
 *
 * .stage-container 안에 <video> 와 <svg> 를 같은 크기로 겹친다. SVG 는 viewBox="0 0 1 1" + preserveAspectRatio="none" 이라
 * meta.cells[].image_polygon (영상 가로·세로를 1 로 본 0~1 좌표)을 변환 없이 polygon 점으로 쓴다.
 * 화면 크기가 바뀌어도 컨테이너와 함께 늘어나므로 셀은 영상의 같은 자리에 머문다.
 * 컨테이너 비율은 영상의 실제 크기(videoWidth/videoHeight)에서 가져온다. 영상이 없으면 16:9 다.
 */
export function CellHeatmap({
  meta, frame, mode, selectedCellId, onCellSelect, videoSrc, t, playing, onVideoTime, onVideoStatus, onVideoEnded,
}: Props) {
  const predicted = mode === 'pred';
  const byId = new Map(pairCells(meta, frame).map((p) => [p.meta.cell_id, p.state]));
  // 격자선은 모든 셀의 윤곽을 path 하나로 모아 한 번에 그린다. 이웃 셀이 같은 변을 공유해도 투명 선이 겹쳐 진해지지 않는다.
  const gridPath = meta.cells
    .map((cm) => `M${cm.image_polygon.map(([x, y]) => `${x} ${y}`).join('L')}Z`)
    .join('');

  const videoRef = useRef<HTMLVideoElement>(null);
  const stageRef = useRef<HTMLDivElement>(null);
  const [status, setStatus] = useState<VideoStatus>(videoSrc ? 'loading' : 'none');
  const [aspect, setAspect] = useState(DEFAULT_ASPECT);

  // 영상 주소가 바뀌면 다시 불러온다
  useEffect(() => {
    setStatus(videoSrc ? 'loading' : 'none');
  }, [videoSrc]);

  // 부모(App)가 재생 방식(영상 기준 / 타이머)을 고를 수 있게 상태를 알려 준다. 화면을 떠나면 'none'.
  const statusCb = useRef(onVideoStatus);
  statusCb.current = onVideoStatus;
  useEffect(() => {
    statusCb.current?.(status);
  }, [status]);
  useEffect(() => () => statusCb.current?.('none'), []);

  // 프레임 t 와 영상 시각을 맞춘다 (재생/정지, 이동)
  useEffect(() => {
    const v = videoRef.current;
    if (!v || status !== 'ready') return;
    const d = decideVideoSync(playing, v.currentTime, t);
    if (d.seekTo !== null) v.currentTime = d.seekTo;
    if (d.play) {
      if (v.paused) v.play().catch(() => setStatus('error')); // 자동 재생이 막히면 타이머 재생으로 되돌린다
    } else if (!v.paused) {
      v.pause();
    }
  }, [t, playing, status]);

  const showVideo = !!videoSrc && status !== 'error';
  const overlay = status === 'ready'; // 영상이 보이는 중이면 셀을 더 투명하게 칠한다

  return (
    <div className="hm-wrap">
      <div
        ref={stageRef}
        className="stage-container"
        data-debug={DEBUG_GRID || undefined}
        style={{ '--stage-aspect': aspect } as CSSProperties}
      >
        {showVideo && (
          <video
            ref={videoRef}
            className="stage-video"
            src={videoSrc}
            muted
            playsInline
            preload="auto"
            onLoadedMetadata={(e) => {
              const { videoWidth: w, videoHeight: h } = e.currentTarget;
              if (w > 0 && h > 0) setAspect(w / h);
              setStatus('ready');
            }}
            onTimeUpdate={(e) => {
              if (playing) onVideoTime?.(e.currentTarget.currentTime);
            }}
            onEnded={onVideoEnded}
            onError={() => setStatus('error')}
          />
        )}
        {!overlay && (
          <p className="hm-note">
            {status === 'loading' && `영상 불러오는 중 · ${videoSrc}`}
            {status === 'error' && `영상을 열 수 없음 · ${videoSrc}`}
            {status === 'none' && `영상 연결 전 · ${meta.video_id}`}
          </p>
        )}
        <svg className="stage-svg" viewBox="0 0 1 1" preserveAspectRatio="none" role="group" aria-label="셀 히트맵">
          {meta.cells.map((cm) => {
            const state = byId.get(cm.cell_id);
            const value = state ? cellValue(state, mode) : null;
            const s = cellStyle(value, predicted);
            const selected = cm.cell_id === selectedCellId;
            const fillOpacity = overlay
              ? s.opacity * HEATMAP_OVERLAY.opacityScale
              : Math.min(1, s.opacity + HEATMAP_OVERLAY.placeholderBoost);
            const label = `${cm.row + 1}행 ${cm.col + 1}열 · ${value === null ? '값 없음' : `${value.toFixed(2)} 명/m²`} · ${s.label}`;
            return (
              <polygon
                key={cm.cell_id}
                className={`heatmap-cell${selected ? ' selected' : ''}${s.predicted ? ' predicted' : ''}${s.blink ? ' severe' : ''}`}
                points={cm.image_polygon.map(([x, y]) => `${x},${y}`).join(' ')}
                fill={s.color}
                fillOpacity={fillOpacity}
                // 관측 셀은 테두리 없이 채움만 (격자선은 아래 path 가 담당). 예측 셀만 등급 색 점선 테두리로 구분한다.
                stroke={s.predicted ? s.strokeColor : 'none'}
                strokeOpacity={s.strokeOpacity}
                strokeWidth={CELL_STYLE.strokeWeight}
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
          <path
            className="heatmap-grid"
            d={gridPath}
            fill="none"
            stroke={CELL_STYLE.strokeColor}
            strokeOpacity={CELL_STYLE.strokeOpacity}
            strokeWidth={CELL_STYLE.strokeWeight}
            strokeLinejoin="round"
            aria-hidden="true"
          />
        </svg>
        {DEBUG_GRID && <DebugGrid meta={meta} stageRef={stageRef} videoSrc={videoSrc} status={status} t={t} />}
      </div>
    </div>
  );
}
