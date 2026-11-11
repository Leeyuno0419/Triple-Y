import { useEffect, useMemo, useState } from 'react';
import { CenterBadge } from '../components/CenterBadge';
import { DensityLayer, type CellRef } from '../components/DensityLayer';
import { DrawLayer, type DrawMode } from '../components/DrawLayer';
import { DrawToolbar } from '../components/DrawToolbar';
import { FavoritesMenu } from '../components/FavoritesMenu';
import { HeatmapLayer } from '../components/HeatmapLayer';
import { GradeBadge } from '../components/GradeBadge';
import { GridPreview } from '../components/GridPreview';
import { KakaoMap } from '../components/KakaoMap';
import { Legend } from '../components/Legend';
import { MapModeToggle, type MapMode } from '../components/MapModeToggle';
import { MapCenterTracker, type MapCenter } from '../components/MapCenterTracker';
import { MapFocus, type FocusTarget } from '../components/MapFocus';
import { MapPlace, type PlaceTarget } from '../components/MapPlace';
import { RegionOutline } from '../components/RegionOutline';
import { RegionPanel } from '../components/RegionPanel';
import { ZoneBounds } from '../components/ZoneBounds';
import { TimeControls } from '../components/TimeControls';
import { ZoneRankList } from '../components/ZoneRankList';
import { ChevronIcon } from '../components/Icons';
import { DENSITY_LEVELS } from '../config/density';
import { areaLabel, cellInArea, summarizeArea, type CustomArea } from '../lib/customArea';
import { buildDashboard, hotCellsFor, type Dashboard } from '../lib/dashboard';
import type { Favorite } from '../lib/favorites';
import { cellStyle } from '../lib/density';
import { isDomestic } from '../lib/geo';
import type { StatusInfo } from '../lib/format';
import { summarizeZone } from '../lib/region';
import { makeSimulation, type SimAnchor } from '../lib/simulation';
import { matchZone } from '../lib/search';
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
  /** 상단 상태 표시 */
  status: StatusInfo;
  index: number;
  playing: boolean;
  onIndexChange: (index: number) => void;
  onTogglePlay: () => void;
  selectedRegion: string | null;
  selectedCell: CellRef | null;
  focus: FocusTarget | null;
  /** 장소 검색으로 이동할 위치 */
  place: PlaceTarget | null;
  /** 검색으로 걸린 구역 필터 (빈 문자열이면 전체) */
  query: string;
  /** 지도에서 셀 클릭 */
  onCellSelect: (cell: CellRef) => void;
  /** 사이드바에서 구역/셀 선택 (지도도 이동) */
  onZoneSelect: (zoneId: string) => void;
  onListCellSelect: (cell: CellRef) => void;
  onCloseRegion: () => void;
  /** 관심 구역(즐겨찾기) */
  favorites: Favorite[];
  currentFavorite: Favorite | null;
  isFavoriteLinked: (f: Favorite) => boolean;
  onOpenFavorite: (f: Favorite) => void;
  onAddFavorite: () => void;
  onRemoveFavorite: (id: string) => void;
}

const fmt = (v: number | null, d = 2) => (v === null ? '-' : v.toFixed(d));

/** 지도 뷰: 좌측 구역 필터·위험도 요약 사이드바 + 우측 카카오맵 */
export function MapView(p: Props) {

  // 필터 상태: 선택한 위험 단계(위험도 요약 카드, 다시 누르면 전체) + 구역별 지도 표시 체크박스
  const [activeGrade, setActiveGrade] = useState<number | null>(null);
  const [hiddenZones, setHiddenZones] = useState<Set<string>>(new Set());
  // 사이드바 접기/열기: 접어도 내용은 그대로 유지되므로(필터·스크롤 위치) 다시 열면 접기 전 상태 그대로다
  const [sideOpen, setSideOpen] = useState(true);
  // 지도 중심 좌표 (사이드바의 📍 위치 뱃지가 이름으로 바꿔 보여 준다)
  const [center, setCenter] = useState<MapCenter | null>(null);
  // 지도 시각화 모드: 기본 지도 / 밀도 히트맵 / Grid 뷰(셀 격자)
  const [mapMode, setMapMode] = useState<MapMode>('grid');
  // 사용자 구역 지정: 그리는 모드와 확정된 구역
  const [drawMode, setDrawMode] = useState<DrawMode>('off');
  const [customArea, setCustomArea] = useState<CustomArea | null>(null);
  // 그리는 동안의 미리보기 구역: 확정 전에도 사이드바 지표를 실시간으로 계산해 보여 준다
  const [preview, setPreview] = useState<CustomArea | null>(null);
  const shownArea = preview ?? customArea;

  // ---- 국내/해외 자동 전환: 지도 중심(또는 검색·이동한 장소)이 해외면 가상 시뮬레이션 데이터로 바꿔 보여 준다 ----
  const [simAnchor, setSimAnchor] = useState<SimAnchor | null>(null);
  useEffect(() => {
    if (!center) return;
    if (isDomestic(center.lat, center.lng)) {
      setSimAnchor(null);
    } else {
      // 해외로 나온 순간의 지도 중심을 기준점으로 삼고, 해외 안에서 지도를 움직여도 같은 시뮬레이션을 유지한다
      setSimAnchor((prev) => prev ?? { lat: center.lat, lng: center.lng, name: p.place && !isDomestic(p.place.lat, p.place.lng) ? p.place.name : undefined });
    }
  }, [center]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    // 새 해외 장소를 검색/선택하면 그 장소로 기준점을 옮기고, 지도가 움직이기 전에 바로 시뮬레이션 모드로 들어간다
    if (p.place && !isDomestic(p.place.lat, p.place.lng)) setSimAnchor({ lat: p.place.lat, lng: p.place.lng, name: p.place.name });
  }, [p.place]);
  const sim = useMemo(() => (simAnchor ? makeSimulation(simAnchor) : null), [simAnchor]);

  // 시뮬레이션 타임라인 재생 상태 (해외 모드에서만 사용; 실제 데이터의 슬라이더 상태는 건드리지 않는다)
  const [simIndex, setSimIndex] = useState(0);
  const [simPlaying, setSimPlaying] = useState(false);
  useEffect(() => {
    setSimIndex(0);
    setSimPlaying(false);
  }, [sim]);
  useEffect(() => {
    if (!simPlaying || !sim) return;
    const id = setInterval(() => {
      setSimIndex((i) => {
        if (i >= sim.frames.length - 1) {
          setSimPlaying(false);
          return i;
        }
        return i + 1;
      });
    }, 1000);
    return () => clearInterval(id);
  }, [simPlaying, sim]);

  // 아래 화면은 모두 "지금 보여 줄 데이터"(실제 또는 시뮬레이션)를 기준으로 그린다
  const zones = sim ? [sim.zone] : p.zones;
  const frames = sim ? sim.frames : p.frames;
  const frame = sim ? sim.frames[Math.min(simIndex, sim.frames.length - 1)] : p.frame;
  const index = sim ? simIndex : p.index;
  const playing = sim ? simPlaying : p.playing;
  const simDash = useMemo(() => (sim ? buildDashboard([sim.zone], frame) : null), [sim, frame]);
  const dash = simDash ?? p.dash;
  const status: StatusInfo = sim ? { text: '🧪 해외 가상 시뮬레이션', kind: 'sim' } : p.status;
  const predicted = frame?.kind === 'predicted';

  const toggleGrade = (i: number) => setActiveGrade((prev) => (prev === i ? null : i));
  const toggleZone = (id: string) =>
    setHiddenZones((prev) => {
      const next = new Set(prev);
      if (!next.delete(id)) next.add(id);
      return next;
    });

  // 목록 필터: 선택한 단계에 해당하는 구역만 (+ 검색어)
  const gradeLevel = activeGrade === null ? null : DENSITY_LEVELS[activeGrade];
  const listed = useMemo(
    () => dash.zones.filter((s) => (gradeLevel === null || s.level === gradeLevel) && matchZone(s.zone, p.query)),
    [dash.zones, gradeLevel, p.query],
  );
  // 고밀도 셀 목록: 같은 단계의 셀만, 사용자 구역이 있으면 그 안의 셀만
  const hotCells = useMemo(
    () =>
      hotCellsFor(
        zones,
        frame,
        gradeLevel,
        undefined,
        shownArea ? (zone, row, col) => cellInArea(zone, row, col, shownArea) : undefined,
      ),
    [zones, frame, gradeLevel, shownArea],
  );
  const areaSummary = useMemo(
    () => (shownArea ? summarizeArea(zones, frame, shownArea) : null),
    [zones, frame, shownArea],
  );
  // 지도에서 숨길 구역 = 체크 해제한 구역 + 검색어와 맞지 않는 구역 (단계 필터는 목록에만 적용)
  const mapHidden = useMemo(() => {
    const out = new Set(hiddenZones);
    for (const z of zones) if (!matchZone(z, p.query)) out.add(z.zone_id);
    return out;
  }, [zones, hiddenZones, p.query]);

  // 격자 레이어는 Grid 뷰에서만 보이게: 다른 모드에서는 모든 구역의 셀을 지도에서 뗀다
  const gridHidden = useMemo(
    () => (mapMode === 'grid' ? mapHidden : new Set(zones.map((z) => z.zone_id))),
    [mapMode, mapHidden, zones],
  );

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

  const filtered = activeGrade !== null || hiddenZones.size > 0;
  const resetFilter = () => {
    setActiveGrade(null);
    setHiddenZones(new Set());
  };

  return (
    <div className={`map-view${sideOpen ? '' : ' side-collapsed'}`}>
      <aside id="map-side" className="side" aria-label="구역 필터와 위험도 요약" aria-hidden={!sideOpen} inert={!sideOpen}>
        {/* 위쪽 고정 영역: 위험도 요약 · 사용자 지정 구역 · 구역 선택 */}
        <div className="side-top">
          <div className="dash-section-title">
            <h2>위험도 요약</h2>
            <span className={`frame-chip ${status.kind}`}>{status.text}</span>
          </div>

          <section className="grade-tiles" aria-label="단계별 구역 수 (눌러서 해당 단계만 보기, 다시 누르면 전체)">
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
                <b>{dash.zonesPerLevel[i]}</b>
                <span>{l.label}</span>
              </button>
            ))}
          </section>

          {shownArea && areaSummary && (
            <section className="card" aria-label="사용자 지정 구역">
              <div className="card-title">
                <h3>사용자 지정 구역{preview ? ' · 미리보기' : ''}</h3>
                {preview ? (
                  <small>그리는 중…</small>
                ) : (
                  <button type="button" className="link-btn" onClick={() => setCustomArea(null)}>
                    해제
                  </button>
                )}
              </div>
              {areaSummary.cells === 0 ? (
                <p className="empty">지정한 범위 안에 분석 셀이 없습니다. 구역(격자) 위를 지정해 보세요.</p>
              ) : (
                <>
                  <div className="area-head">
                    <GradeBadge level={areaSummary.level} predicted={predicted} />
                    <small>
                      {areaLabel(shownArea)} · {Math.round(areaSummary.areaM2).toLocaleString()}㎡
                    </small>
                  </div>
                  <dl className="rp-stats">
                    <div>
                      <dt>추정 인원</dt>
                      <dd>{Math.round(areaSummary.people).toLocaleString()}<small> 명</small></dd>
                    </div>
                    <div>
                      <dt>평균 밀도</dt>
                      <dd>{fmt(areaSummary.meanDensity)}<small> 명/m²</small></dd>
                    </div>
                    <div>
                      <dt>최대 밀도</dt>
                      <dd>{fmt(areaSummary.maxDensity)}<small> 명/m²</small></dd>
                    </div>
                    <div>
                      <dt>관측 셀</dt>
                      <dd>{areaSummary.observedCells}<small> / {areaSummary.cells}칸</small></dd>
                    </div>
                  </dl>
                </>
              )}
            </section>
          )}

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
              emptyText={gradeLevel ? `${gradeLevel.label} 단계인 구역이 없습니다.` : undefined}
            />
          </section>
        </div>

        {/* 지도 도구: 중심지 뱃지 · 지도 뷰 모드 · 구역 지정 (지도 위에 흩어져 있던 버튼을 사이드바로 모음) */}
        <section className="map-tools" aria-label="지도 도구">
          <CenterBadge center={center} />
          <MapModeToggle mode={mapMode} onChange={setMapMode} />
          <DrawToolbar mode={drawMode} hasArea={customArea !== null} onMode={setDrawMode} onClear={() => setCustomArea(null)} />
        </section>

        {/* 남는 높이를 차지하고, 목록은 이 카드 안에서만 스크롤 */}
        <section className="card grow" aria-label="고밀도 셀">
            <div className="card-title">
              <h3>고밀도 셀 TOP {hotCells.length || ''}</h3>
              <small>
                {[shownArea ? '지정 구역 안' : null, gradeLevel ? `${gradeLevel.label} 단계` : null].filter(Boolean).join(' · ') ||
                  '눌러서 상세 보기'}
              </small>
            </div>
            {hotCells.length === 0 ? (
              <p className="empty">{gradeLevel ? `${gradeLevel.label} 단계인 셀이 없습니다.` : '조건에 맞는 셀이 없습니다.'}</p>
            ) : (
              <ol className="hot-list">
                {hotCells.map((c, i) => (
                  <li key={`${c.zone_id}:${c.row}:${c.col}`}>
                    <button type="button" onClick={() => p.onListCellSelect({ zone_id: c.zone_id, row: c.row, col: c.col })}>
                      <span className="rank">{i + 1}</span>
                      <span className="hc-main">{c.zoneName} · {c.row + 1}행 {c.col + 1}열</span>
                      <b>{c.value.toFixed(2)}</b>
                      <GradeBadge level={c.level} predicted={predicted} />
                    </button>
                  </li>
                ))}
              </ol>
            )}
          </section>

        <footer className="dash-foot">
          {frames.length > 0 && (
            <TimeControls
              frames={frames}
              index={index}
              playing={playing}
              simulated={sim !== null}
              onIndexChange={
                sim
                  ? (i) => {
                      setSimPlaying(false);
                      setSimIndex(i);
                    }
                  : p.onIndexChange
              }
              onTogglePlay={sim ? () => setSimPlaying((v) => !v) : p.onTogglePlay}
            />
          )}
          {sim && <p className="sim-note">※ 해외 지역은 가상 시뮬레이션 모드로 동작합니다</p>}
          <Legend />
        </footer>
      </aside>

      <div className="map-card">
        <button
          type="button"
          className="side-toggle"
          aria-expanded={sideOpen}
          aria-controls="map-side"
          aria-label="사이드바 접기/열기"
          title={sideOpen ? '사이드바 접기' : '사이드바 열기'}
          onClick={() => setSideOpen((o) => !o)}
        >
          <ChevronIcon size={14} />
        </button>
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
            <DensityLayer zones={zones} frame={frame} hiddenZones={gridHidden} onCellSelect={p.onCellSelect} />
            <HeatmapLayer zones={zones} frame={frame} active={mapMode === 'heat'} hiddenZones={mapHidden} onCellSelect={p.onCellSelect} />
            <ZoneBounds zones={zones} active={mapMode === 'base'} hiddenZones={mapHidden} />
            <RegionOutline zone={regionZone} />
            <MapFocus target={p.focus} />
            <MapPlace target={p.place} />
            <DrawLayer
              mode={drawMode}
              area={customArea}
              onPreview={setPreview}
              onComplete={(area) => {
                setCustomArea(area);
                setDrawMode('off');
              }}
              onCancel={() => setDrawMode('off')}
            />
            <MapCenterTracker onCenter={setCenter} />
            {/* 지도 위에는 관심 구역 버튼만 남긴다 */}
            <div className="map-toolbar">
              <FavoritesMenu
                items={p.favorites}
                current={p.currentFavorite}
                isLinked={p.isFavoriteLinked}
                onOpen={p.onOpenFavorite}
                onAddCurrent={p.onAddFavorite}
                onRemove={p.onRemoveFavorite}
              />
            </div>
          </KakaoMap>
        )}
        <RegionPanel region={region} frame={frame} cell={cellInfo} onClose={p.onCloseRegion} simulated={sim !== null} />
      </div>
    </div>
  );
}
