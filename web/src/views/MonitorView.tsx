import { useMemo, useState } from 'react';
import { AlertPanel } from '../components/AlertPanel';
import { CellHeatmap, type VideoStatus } from '../components/CellHeatmap';
import { ChevronIcon } from '../components/Icons';
import { HotCellList } from '../components/HotCellList';
import { Legend } from '../components/Legend';
import { MonitorKpis } from '../components/MonitorKpis';
import { MonitorTrend } from '../components/MonitorTrend';
import { RegionPanel, type SelectedCellInfo } from '../components/RegionPanel';
import { TimeControls } from '../components/TimeControls';
import { VideoManager } from '../components/VideoManager';
import { DENSITY_LEVELS } from '../config/density';
import type { AlertItem } from '../lib/alerts';
import { buildDashboard, hotCellsFor, type Dashboard } from '../lib/dashboard';
import type { StatusInfo } from '../lib/format';
import type { VideoEntry } from '../lib/videoLibrary';
import { cellLevel } from '../lib/grade';
import { cellValue, pairCells, type ViewMode } from '../lib/model';
import type { LiveAlert } from '../types/live';
import type { Frame, Meta } from '../types/timeline';

interface Props {
  hasData: boolean;
  error: string | null;
  meta: Meta | undefined;
  frames: Frame[];
  /** 슬라이더가 가리키는 프레임 */
  frame: Frame | undefined;
  /** 위 프레임·모드 기준 요약 */
  dash: Dashboard | null;
  mode: ViewMode;
  onModeChange: (mode: ViewMode) => void;
  /** 상단 상태 표시 */
  status: StatusInfo;
  index: number;
  playing: boolean;
  onIndexChange: (index: number) => void;
  onTogglePlay: () => void;
  /** 선택한 셀의 cell_id */
  selectedCellId: string | null;
  onCellSelect: (cellId: string | null) => void;
  /** 영상 주소 (없으면 영상 없이 셀만 표시) */
  videoSrc?: string;
  /** 영상을 재생해야 하는가 (사용자가 재생 중이거나, 실시간에서 최신 프레임을 따라가는 중) */
  videoPlaying: boolean;
  /** 재생 중 영상 시각(초)이 바뀔 때 — 영상이 시간의 기준 */
  onVideoTime: (sec: number) => void;
  onVideoStatus: (status: VideoStatus) => void;
  onVideoEnded: () => void;
  /** 범례에 표시할 단계 경계값 [주의, 경계, 심각] (서버 hello.thresholds). 없으면 기본 설정 */
  bounds?: number[];
  /** 프레임 이력에서 파생한 알림 (서버 알림이 없을 때만 쓴다) */
  alerts: AlertItem[];
  /** 서버 미확인 알림. null 이면 서버에 연결되지 않은 것이다 */
  liveAlerts: LiveAlert[] | null;
  onAck: (alertId: string) => void;
  /** 영상 관리: 표시 중인 등록 영상 id(기본 영상이면 null), 표시 중·기본 영상 이름, 실시간 여부, 영상 바꾸기 */
  selectedVideoId: string | null;
  videoName: string;
  defaultVideoName: string;
  isLive: boolean;
  onSelectVideo: (entry: VideoEntry | null) => void;
}

/**
 * 모니터 뷰: 상단 요약 카드 + 좌측 위험도 사이드바 · 중앙 영상 위 셀 히트맵과 추이/재생 바 · 우측 경보 패널.
 * 레이아웃 CSS 는 지도 뷰에서 쓰던 .map-view / .side / .map-card 를 그대로 쓴다.
 */
export function MonitorView(p: Props) {
  const [activeGrade, setActiveGrade] = useState<number | null>(null); // 단계 타일을 눌러 고밀도 셀 목록을 걸러 본다
  const [sideOpen, setSideOpen] = useState(true);
  const [panelOpen, setPanelOpen] = useState(true);
  const [showLabels, setShowLabels] = useState(true);
  const [managerOpen, setManagerOpen] = useState(false);
  const { meta, frame, mode } = p;
  const predicted = mode === 'pred';
  const summary = p.dash?.summary;
  const horizon = meta?.prediction.horizon_s ?? 60;

  // 요약 카드는 표시 값(관측/예측)과 상관없이 같은 프레임의 관측과 예측을 함께 보여 준다
  const dashNow = useMemo(() => (meta ? buildDashboard(meta, frame, 'now') : null), [meta, frame]);
  const dashPred = useMemo(() => (meta ? buildDashboard(meta, frame, 'pred') : null), [meta, frame]);

  const gradeLevel = activeGrade === null ? null : DENSITY_LEVELS[activeGrade];
  const hotCells = useMemo(
    () => (meta ? hotCellsFor(meta, frame, mode, gradeLevel) : []),
    [meta, frame, mode, gradeLevel],
  );

  // 선택한 셀의 상세: 현재 프레임에서 cell_id 로 찾는다
  const cellInfo = useMemo<SelectedCellInfo | null>(() => {
    if (!meta || !frame || !p.selectedCellId) return null;
    const pair = pairCells(meta, frame).find((c) => c.meta.cell_id === p.selectedCellId);
    if (!pair) return null;
    const value = cellValue(pair.state, mode);
    return { meta: pair.meta, state: pair.state, value, level: cellLevel(pair.state, mode, value, p.bounds) };
  }, [meta, frame, mode, p.selectedCellId, p.bounds]);

  const toggleGrade = (i: number) => setActiveGrade((prev) => (prev === i ? null : i));
  const closeCell = () => p.onCellSelect(null);

  return (
    <div className="monitor">
    <MonitorKpis now={dashNow} pred={dashPred} horizonS={horizon} liveAlerts={p.liveAlerts} derivedCount={p.alerts.length} />
    <div className={`map-view monitor-grid${sideOpen ? '' : ' side-collapsed'}${panelOpen ? '' : ' panel-collapsed'}`}>
      <aside id="monitor-side" className="side" aria-label="위험도 요약" aria-hidden={!sideOpen} inert={!sideOpen}>
        <div className="side-top">
          <div className="dash-section-title">
            <h2>위험도 요약</h2>
            <span className={`frame-chip ${p.status.kind}`}>{p.status.text}</span>
          </div>

          <section className="grade-tiles" aria-label="단계별 셀 수 (눌러서 해당 단계만 보기, 다시 누르면 전체)">
            {DENSITY_LEVELS.map((l, i) => (
              <button
                key={l.label}
                type="button"
                className={`grade-tile${activeGrade === i ? ' active' : ''}`}
                style={{ '--b-bg': l.soft.bg, '--b-ink': l.soft.ink, '--b-dot': l.soft.dot } as React.CSSProperties}
                aria-pressed={activeGrade === i}
                title={activeGrade === i ? '다시 누르면 전체 보기' : `${l.label} 단계만 보기`}
                onClick={() => toggleGrade(i)}
              >
                <b>{summary?.levelCounts[i] ?? 0}</b>
                <span>{l.label}</span>
              </button>
            ))}
          </section>

          <section className="card" aria-label="표시 값 선택">
            <div className="card-title">
              <h3>표시 값</h3>
              <small>{predicted ? `${horizon}초 뒤 예측을 표시 중` : '현재 관측을 표시 중'}</small>
            </div>
            <div className="pill-group" role="group" aria-label="표시 값">
              <button type="button" className={`pill${!predicted ? ' active' : ''}`} aria-pressed={!predicted} onClick={() => p.onModeChange('now')}>
                현재 관측
              </button>
              <button type="button" className={`pill${predicted ? ' active' : ''}`} aria-pressed={predicted} onClick={() => p.onModeChange('pred')}>
                {horizon}초 뒤 예측
              </button>
            </div>
          </section>
        </div>

        {/* 남는 높이를 차지하고, 목록은 이 카드 안에서만 스크롤 */}
        <section className="card grow" aria-label="고밀도 셀">
          <div className="card-title">
            <h3>고밀도 셀 TOP {hotCells.length || ''}</h3>
            <small>{gradeLevel ? `${gradeLevel.label} 단계` : '눌러서 상세 보기'}</small>
          </div>
          <HotCellList
            cells={hotCells}
            predicted={predicted}
            onSelect={p.onCellSelect}
            emptyText={gradeLevel ? `${gradeLevel.label} 단계인 셀이 없습니다.` : undefined}
          />
        </section>

      </aside>

      <div className="monitor-center">
      <div className="map-card">
        <div className="map-bar">
          <div className="pill-group" role="group" aria-label="표시 레이어">
            <button type="button" className={`pill${showLabels ? ' active' : ''}`} aria-pressed={showLabels} onClick={() => setShowLabels((v) => !v)}>
              셀 수치
            </button>
            <button type="button" className={`pill${panelOpen ? ' active' : ''}`} aria-pressed={panelOpen} onClick={() => setPanelOpen((v) => !v)}>
              경보 패널
            </button>
            <button type="button" className="pill" aria-haspopup="dialog" title={`표시 중: ${p.videoName}`} onClick={() => setManagerOpen(true)}>
              영상 관리
            </button>
          </div>
          <Legend bounds={p.bounds} />
        </div>
        <div className="map-body">
        <button
          type="button"
          className="side-toggle"
          aria-expanded={sideOpen}
          aria-controls="monitor-side"
          aria-label="사이드바 접기/열기"
          title={sideOpen ? '사이드바 접기' : '사이드바 열기'}
          onClick={() => setSideOpen((o) => !o)}
        >
          <ChevronIcon size={14} />
        </button>
        {p.error && <div className="map-error" role="alert">데이터를 불러오지 못했습니다: {p.error}</div>}
        {p.hasData && meta && (
          <CellHeatmap
            key={p.videoSrc}
            meta={meta}
            frame={frame}
            mode={mode}
            selectedCellId={p.selectedCellId}
            onCellSelect={p.onCellSelect}
            videoSrc={p.videoSrc}
            t={frame?.t ?? 0}
            playing={p.videoPlaying}
            onVideoTime={p.onVideoTime}
            onVideoStatus={p.onVideoStatus}
            onVideoEnded={p.onVideoEnded}
            bounds={p.bounds}
            showLabels={showLabels}
          />
        )}
        {summary && <RegionPanel summary={summary} cell={cellInfo} mode={mode} onClose={closeCell} />}
        </div>
      </div>

      {p.frames.length > 0 && (
        <section className="monitor-bottom" aria-label="추이와 재생">
          <MonitorTrend frames={p.frames} index={p.index} horizonS={horizon} bounds={p.bounds} />
          <TimeControls
            frames={p.frames}
            index={p.index}
            playing={p.playing}
            mode={mode}
            horizonS={horizon}
            onIndexChange={p.onIndexChange}
            onTogglePlay={p.onTogglePlay}
          />
        </section>
      )}
      </div>

      {/* 접으면 아예 그리지 않는다: 보이지 않는 알림이 '화면에 표시됨'으로 G2 지연에 기록되지 않게 */}
      {managerOpen && (
        <VideoManager
          onClose={() => setManagerOpen(false)}
          selectedId={p.selectedVideoId}
          defaultName={p.defaultVideoName}
          live={p.isLive}
          onSelect={p.onSelectVideo}
        />
      )}
      {panelOpen && <AlertPanel alerts={p.alerts} liveAlerts={p.liveAlerts} onAck={p.onAck} level={dashNow?.summary.level ?? null} />}
    </div>
    </div>
  );
}
