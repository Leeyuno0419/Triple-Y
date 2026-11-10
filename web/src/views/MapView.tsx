import { useMemo, useState } from 'react';
import { DensityLayer, type CellRef } from '../components/DensityLayer';
import { GradeBadge } from '../components/GradeBadge';
import { GridPreview } from '../components/GridPreview';
import { KakaoMap } from '../components/KakaoMap';
import { Legend } from '../components/Legend';
import { MapFocus, type FocusTarget } from '../components/MapFocus';
import { RegionOutline } from '../components/RegionOutline';
import { RegionPanel } from '../components/RegionPanel';
import { TimeControls } from '../components/TimeControls';
import { ZoneRankList } from '../components/ZoneRankList';
import { DENSITY_LEVELS } from '../config/density';
import type { Dashboard } from '../lib/dashboard';
import { cellStyle } from '../lib/density';
import { frameLabel } from '../lib/format';
import { summarizeZone } from '../lib/region';
import type { Frame, ZoneMeta } from '../types/timeline';

interface Props {
  /** 화면에 보이는 중인가 (한 번 열린 뒤에는 숨겨도 지도를 유지한다) */
  active: boolean;
  hasData: boolean;
  error: string | null;
  zones: ZoneMeta[];
  frames: Frame[];
  /** 슬라이더가 가리키는 프레임 */
  frame: Frame | undefined;
  /** 위 프레임 기준 요약 */
  dash: Dashboard;
  index: number;
  playing: boolean;
  onIndexChange: (index: number) => void;
  onTogglePlay: () => void;
  selectedRegion: string | null;
  selectedCell: CellRef | null;
  focus: FocusTarget | null;
  /** 지도에서 셀 클릭 */
  onCellSelect: (cell: CellRef) => void;
  /** 사이드바에서 구역/셀 선택 (지도도 이동) */
  onZoneSelect: (zoneId: string) => void;
  onListCellSelect: (cell: CellRef) => void;
  onCloseRegion: () => void;
}

const ALL_GRADES = () => new Set(DENSITY_LEVELS.map((_, i) => i));

/** 지도 뷰: 좌측 구역 필터·위험도 요약 사이드바 + 우측 카카오맵 */
export function MapView(p: Props) {
  const { dash, frame, zones } = p;
  const predicted = frame?.kind === 'predicted';

  // 필터 상태: 단계 토글(위험도 요약 타일) + 구역별 지도 표시 체크박스
  const [activeGrades, setActiveGrades] = useState<Set<number>>(ALL_GRADES);
  const [hiddenZones, setHiddenZones] = useState<Set<string>>(new Set());

  const toggleGrade = (i: number) =>
    setActiveGrades((prev) => {
      const next = new Set(prev);
      if (!next.delete(i)) next.add(i);
      return next;
    });
  const toggleZone = (id: string) =>
    setHiddenZones((prev) => {
      const next = new Set(prev);
      if (!next.delete(id)) next.add(id);
      return next;
    });

  const gradeOf = (levelIdx: number | null) => levelIdx === null || activeGrades.has(levelIdx);
  const listed = useMemo(
    () => dash.zones.filter((s) => gradeOf(s.level ? DENSITY_LEVELS.indexOf(s.level) : null)),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [dash.zones, activeGrades],
  );
  // 지도에서 숨길 구역 = 체크 해제한 구역 + 단계 필터에 안 맞는 구역
  const mapHidden = useMemo(() => {
    const out = new Set(hiddenZones);
    for (const s of dash.zones) if (!gradeOf(s.level ? DENSITY_LEVELS.indexOf(s.level) : null)) out.add(s.zone.zone_id);
    return out;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dash.zones, hiddenZones, activeGrades]);

  // 선택한 구역/셀 상세
  const regionZone = useMemo(() => zones.find((z) => z.zone_id === p.selectedRegion) ?? null, [zones, p.selectedRegion]);
  const region = useMemo(
    () => (regionZone ? summarizeZone(regionZone, frame?.zones.find((z) => z.zone_id === regionZone.zone_id)) : null),
    [regionZone, frame],
  );
  const cellInfo = useMemo(() => {
    const c = p.selectedCell;
    if (!c || !frame || c.zone_id !== p.selectedRegion) return null;
    const value = frame.zones.find((z) => z.zone_id === c.zone_id)?.density[c.row]?.[c.col] ?? null;
    return { row: c.row, col: c.col, value, label: cellStyle(value).label };
  }, [p.selectedCell, p.selectedRegion, frame]);

  const filtered = activeGrades.size !== DENSITY_LEVELS.length || hiddenZones.size > 0;
  const resetFilter = () => {
    setActiveGrades(ALL_GRADES());
    setHiddenZones(new Set());
  };

  return (
    <div className="map-view">
      <aside className="side" aria-label="구역 필터와 위험도 요약">
        <div className="dash-scroll">
          <div className="dash-section-title">
            <h2>위험도 요약</h2>
            <span className={`frame-chip${predicted ? ' pred' : ''}`}>{frameLabel(frame)}</span>
          </div>

          <section className="grade-tiles" aria-label="단계별 구역 수 (눌러서 필터)">
            {DENSITY_LEVELS.map((l, i) => (
              <button
                key={l.label}
                type="button"
                className={`grade-tile${activeGrades.has(i) ? ' on' : ''}`}
                style={{ '--b-bg': l.soft.bg, '--b-ink': l.soft.ink, '--b-dot': l.soft.dot } as React.CSSProperties}
                aria-pressed={activeGrades.has(i)}
                onClick={() => toggleGrade(i)}
              >
                <b>{dash.zonesPerLevel[i]}</b>
                <span>{l.label}</span>
              </button>
            ))}
          </section>

          <section className="card" aria-label="구역 선택">
            <div className="card-title">
              <h3>구역 선택</h3>
              {filtered ? (
                <button type="button" className="link-btn" onClick={resetFilter}>필터 초기화</button>
              ) : (
                <small>체크 = 지도에 표시</small>
              )}
            </div>
            <ZoneRankList
              zones={listed}
              predicted={predicted}
              selectedId={p.selectedRegion}
              onSelect={p.onZoneSelect}
              hidden={hiddenZones}
              onToggle={toggleZone}
              emptyText="선택한 단계에 해당하는 구역이 없습니다."
            />
          </section>

          <section className="card" aria-label="고밀도 셀">
            <div className="card-title">
              <h3>고밀도 셀 TOP {dash.hotCells.length || ''}</h3>
              <small>눌러서 상세 보기</small>
            </div>
            {dash.hotCells.length === 0 ? (
              <p className="empty">관측된 셀이 없습니다.</p>
            ) : (
              <ol className="hot-list">
                {dash.hotCells.map((c, i) => (
                  <li key={`${c.zone_id}:${c.row}:${c.col}`}>
                    <button type="button" onClick={() => p.onListCellSelect({ zone_id: c.zone_id, row: c.row, col: c.col })}>
                      <span className="rank">{i + 1}</span>
                      <span className="hc-main">{c.zone_id} · {c.row + 1}행 {c.col + 1}열</span>
                      <b>{c.value.toFixed(2)}</b>
                      <GradeBadge level={c.level} predicted={predicted} />
                    </button>
                  </li>
                ))}
              </ol>
            )}
          </section>
        </div>

        <footer className="dash-foot">
          {p.frames.length > 0 && (
            <TimeControls
              frames={p.frames}
              index={p.index}
              playing={p.playing}
              onIndexChange={p.onIndexChange}
              onTogglePlay={p.onTogglePlay}
            />
          )}
          <Legend />
        </footer>
      </aside>

      <div className="map-card">
        {p.error && <div className="map-error" role="alert">데이터를 불러오지 못했습니다: {p.error}</div>}
        {p.hasData && (
          <KakaoMap
            zones={zones}
            fallback={
              <GridPreview
                zones={zones.filter((z) => !mapHidden.has(z.zone_id))}
                frame={frame}
                selected={p.selectedCell}
                selectedRegion={p.selectedRegion}
                onCellSelect={p.onCellSelect}
              />
            }
          >
            <DensityLayer zones={zones} frame={frame} hiddenZones={mapHidden} onCellSelect={p.onCellSelect} />
            <RegionOutline zone={regionZone} />
            <MapFocus target={p.focus} />
          </KakaoMap>
        )}
        <RegionPanel region={region} frame={frame} cell={cellInfo} onClose={p.onCloseRegion} />
      </div>
    </div>
  );
}
