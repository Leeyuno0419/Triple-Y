import { useMemo, useState } from 'react';
import { CellHeatmap } from '../components/CellHeatmap';
import { ChevronIcon } from '../components/Icons';
import { HotCellList } from '../components/HotCellList';
import { Legend } from '../components/Legend';
import { RegionPanel, type SelectedCellInfo } from '../components/RegionPanel';
import { TimeControls } from '../components/TimeControls';
import { DENSITY_LEVELS } from '../config/density';
import { hotCellsFor, type Dashboard } from '../lib/dashboard';
import { levelOf } from '../lib/density';
import type { StatusInfo } from '../lib/format';
import { cellValue, pairCells, type ViewMode } from '../lib/model';
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
}

/**
 * 모니터 뷰: 좌측 위험도 요약 사이드바 + 우측 영상 위 셀 히트맵 (기획서 MVP 화면).
 * 레이아웃 CSS 는 지도 뷰에서 쓰던 .map-view / .side / .map-card 를 그대로 쓴다.
 */
export function MonitorView(p: Props) {
  const [activeGrade, setActiveGrade] = useState<number | null>(null); // 단계 타일을 눌러 고밀도 셀 목록을 걸러 본다
  const [sideOpen, setSideOpen] = useState(true);
  const { meta, frame, mode } = p;
  const predicted = mode === 'pred';
  const summary = p.dash?.summary;
  const horizon = meta?.prediction.horizon_s ?? 60;

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
    return { meta: pair.meta, state: pair.state, value, level: value === null ? null : levelOf(value) };
  }, [meta, frame, mode, p.selectedCellId]);

  const toggleGrade = (i: number) => setActiveGrade((prev) => (prev === i ? null : i));
  const closeCell = () => p.onCellSelect(null);

  return (
    <div className={`map-view${sideOpen ? '' : ' side-collapsed'}`}>
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

        <footer className="dash-foot">
          {p.frames.length > 0 && (
            <TimeControls
              frames={p.frames}
              index={p.index}
              playing={p.playing}
              mode={mode}
              horizonS={horizon}
              onIndexChange={p.onIndexChange}
              onTogglePlay={p.onTogglePlay}
            />
          )}
          <Legend />
        </footer>
      </aside>

      <div className="map-card">
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
          <CellHeatmap meta={meta} frame={frame} mode={mode} selectedCellId={p.selectedCellId} onCellSelect={p.onCellSelect} />
        )}
        {summary && <RegionPanel summary={summary} cell={cellInfo} mode={mode} onClose={closeCell} />}
      </div>
    </div>
  );
}
