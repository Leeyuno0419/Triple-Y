import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { APP_NAME_EN, KAKAO_JS_KEY, LIVE, WS_URL } from './config/app';
import { AppHeader, type ViewId } from './components/AppHeader';
import type { CellRef } from './components/DensityLayer';
import type { FocusTarget } from './components/MapFocus';
import type { PlaceTarget } from './components/MapPlace';
import { SearchBox, type SearchNote } from './components/SearchBox';
import { deriveAlerts } from './lib/alerts';
import { buildDashboard, peakSeries } from './lib/dashboard';
import { placeFavorite, zoneFavorite, type Favorite } from './lib/favorites';
import type { StatusInfo } from './lib/format';
import { applyLiveMessage, type LiveMessage } from './lib/liveFeed';
import { findOverseasSample, isDomestic } from './lib/geo';
import { searchPlace } from './lib/place';
import { matchZone } from './lib/search';
import { loadTimeline, type LoadResult } from './lib/timeline';
import { useFavorites } from './lib/useFavorites';
import { useLiveFeed, type LiveStatus } from './lib/useLiveFeed';
import { AnalysisView } from './views/AnalysisView';
import { HomeView } from './views/HomeView';
import { MapView } from './views/MapView';

const PLAY_INTERVAL_MS = 1000;

const VIEWS: ViewId[] = ['home', 'map', 'analysis'];
function parseHash(): ViewId {
  const h = window.location.hash.replace(/^#\/?/, '') as ViewId;
  return VIEWS.includes(h) ? h : 'home';
}

const LIVE_BADGE: Record<LiveStatus, string | null> = {
  idle: null,
  connecting: '● 연결 중',
  open: '● 실시간',
  reconnecting: '● 재연결 중',
};

export default function App() {
  const [data, setData] = useState<LoadResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [index, setIndex] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [selected, setSelected] = useState<CellRef | null>(null);
  // 상세 패널에 표시할 구역(zone_id). null 이면 패널이 닫혀 있다.
  const [selectedRegion, setSelectedRegion] = useState<string | null>(null);
  const [view, setView] = useState<ViewId>(parseHash);
  const [mapVisited, setMapVisited] = useState(false); // 지도는 처음 열 때 만들고, 이후엔 숨기기만 한다
  // 대시보드 목록에서 고른 구역으로 지도를 옮기기 위한 요청 (지도에서 직접 클릭할 때는 쓰지 않는다)
  const [focus, setFocus] = useState<FocusTarget | null>(null);
  const focusSeq = useRef(0);
  // 검색: query = 목록·지도에 적용 중인 구역 필터, place = 장소 검색으로 이동할 위치, searchNote = 결과 안내
  const [query, setQuery] = useState('');
  const [place, setPlace] = useState<PlaceTarget | null>(null);
  const [searchNote, setSearchNote] = useState<SearchNote | null>(null);
  const searchToken = useRef(0); // 늦게 도착한 이전 검색 결과를 무시하기 위한 번호
  const placeSeq = useRef(0);
  const liveReceived = useRef(false); // 실시간 데이터가 한 번이라도 왔는가
  const following = useRef(true); // 슬라이더가 "현재(마지막 관측)"에 있어 새 프레임을 따라가는가

  useEffect(() => {
    const ctrl = new AbortController();
    loadTimeline(ctrl.signal)
      .then((res) => {
        if (liveReceived.current) return; // 실시간 데이터가 먼저 왔으면 덮어쓰지 않는다
        setData(res);
        // 처음에는 "현재"(마지막 관측 프레임)를 보여준다.
        const lastObserved = res.timeline.frames.map((f) => f.kind).lastIndexOf('observed');
        setIndex(Math.max(lastObserved, 0));
      })
      .catch((e: Error) => !ctrl.signal.aborted && setError(e.message));
    return () => ctrl.abort();
  }, []);

  // 실시간(WebSocket) 수신: timeline 이 오면 교체, frames 가 오면 이어 붙인다.
  const onLive = useCallback((msg: LiveMessage) => {
    liveReceived.current = true;
    setError(null);
    setData((prev) => {
      try {
        const next = applyLiveMessage(prev?.timeline ?? null, msg, LIVE.maxObservedFrames);
        return next ? { timeline: next, source: 'live' } : prev;
      } catch (err) {
        console.warn('[live] 프레임 무시:', err);
        return prev;
      }
    });
  }, []);
  const liveStatus = useLiveFeed(WS_URL, onLive);

  const frames = data?.timeline.frames ?? [];
  const zones = useMemo(() => data?.timeline.zones ?? [], [data]);
  const frame = frames[index];

  // 새 프레임이 오면 "현재"를 보고 있던 경우에만 따라간다 (과거를 보는 중이면 그대로 둔다).
  const lastObserved = useMemo(() => frames.map((f) => f.kind).lastIndexOf('observed'), [frames]);
  useEffect(() => {
    if (data?.source === 'live' && following.current) setIndex(Math.max(lastObserved, 0));
  }, [data?.source, lastObserved, frames.length]);

  // 재생: 끝에 닿으면 정지
  useEffect(() => {
    if (!playing) return;
    const id = setInterval(() => {
      setIndex((i) => {
        if (i >= frames.length - 1) {
          setPlaying(false);
          return i;
        }
        return i + 1;
      });
    }, PLAY_INTERVAL_MS);
    return () => clearInterval(id);
  }, [playing, frames.length]);

  // ---- 화면 전환: state 로 분기하고, URL 해시(#/map 등)와 동기화해 뒤로가기·새로고침을 지원한다 ----
  const go = useCallback((next: ViewId) => {
    setView(next);
    if (window.location.hash !== `#/${next}`) window.location.hash = `#/${next}`;
  }, []);
  useEffect(() => {
    const onHash = () => setView(parseHash());
    window.addEventListener('hashchange', onHash);
    return () => window.removeEventListener('hashchange', onHash);
  }, []);
  useEffect(() => {
    if (view === 'map') setMapVisited(true);
  }, [view]);

  // ---- 선택 상태 (지도 뷰와 다른 뷰가 공유) ----
  const handleCellSelect = useCallback((cell: CellRef) => {
    setSelected(cell);
    setSelectedRegion(cell.zone_id);
  }, []);
  const closeRegion = useCallback(() => {
    setSelectedRegion(null);
    setSelected(null);
  }, []);
  const focusZone = useCallback(
    (zoneId: string) => {
      const zone = zones.find((z) => z.zone_id === zoneId);
      if (zone) setFocus({ zone, seq: ++focusSeq.current });
    },
    [zones],
  );
  const handleZoneSelect = useCallback(
    (zoneId: string) => {
      setSelected(null);
      setSelectedRegion(zoneId);
      focusZone(zoneId);
    },
    [focusZone],
  );
  const handleListCellSelect = useCallback(
    (cell: CellRef) => {
      handleCellSelect(cell);
      focusZone(cell.zone_id);
    },
    [handleCellSelect, focusZone],
  );
  /** 홈/알림에서 구역을 누르면: 구역 선택 + 지도 뷰로 이동 */
  const openZoneOnMap = useCallback(
    (zoneId: string) => {
      handleZoneSelect(zoneId);
      go('map');
    },
    [handleZoneSelect, go],
  );

  /**
   * 검색 실행 (Enter 또는 돋보기 클릭).
   * 1) 구역 이름·ID 가 일치하면 → 그 구역 목록으로 필터링하고 첫 구역을 선택해 지도를 이동한다.
   * 2) 일치하는 구역이 없으면 → 카카오 장소 검색으로 위치를 찾아 지도를 그 위치로 이동한다(마커 표시).
   * 빈 검색어는 필터를 해제한다.
   */
  const runSearch = useCallback(
    (raw: string) => {
      const q = raw.trim();
      const token = ++searchToken.current;
      setPlace(null);
      if (!q) {
        setQuery('');
        setSearchNote(null);
        return;
      }

      const hits = zones.filter((z) => matchZone(z, q));
      if (hits.length > 0) {
        setQuery(q);
        setSearchNote({ tone: 'info', text: `구역 ${hits.length}곳 일치 · ${hits[0].name}` });
        handleZoneSelect(hits[0].zone_id);
        if (view === 'home') go('map');
        return;
      }

      // 해외 샘플 장소(도쿄·뉴욕 등)면 그 위치로 이동 — 지도 뷰가 가상 시뮬레이션 모드로 자동 전환된다
      const sample = findOverseasSample(q);
      if (sample) {
        setQuery('');
        setPlace({ name: sample.name, lat: sample.lat, lng: sample.lng, seq: ++placeSeq.current });
        setSearchNote({ tone: 'info', text: `"${sample.name}" 위치로 이동했습니다. 해외 지역은 가상 시뮬레이션으로 표시됩니다.` });
        go('map');
        return;
      }

      setQuery(''); // 구역 필터는 일치가 있을 때만 건다 (없으면 목록이 텅 비므로)
      setSearchNote({ tone: 'info', text: '장소를 찾는 중…' });
      searchPlace(q, KAKAO_JS_KEY)
        .then((hit) => {
          if (token !== searchToken.current) return;
          if (!hit) {
            setSearchNote({ tone: 'warn', text: `"${q}"와 일치하는 구역이나 장소가 없습니다.` });
            return;
          }
          setPlace({ name: hit.name, lat: hit.lat, lng: hit.lng, seq: ++placeSeq.current });
          setSearchNote({ tone: 'info', text: `"${hit.name}" 위치로 이동했습니다.` });
          go('map');
        })
        .catch((err: Error) => {
          if (token !== searchToken.current) return;
          setSearchNote({ tone: 'warn', text: `구역 일치 없음 · 장소 검색 불가: ${err.message}` });
        });
    },
    [zones, view, go, handleZoneSelect],
  );

  // ---- 관심 구역(즐겨찾기): localStorage 에 저장 ----
  const favorites = useFavorites(zones);
  /** "+ 현재 구역 저장"으로 저장할 후보: 선택한 구역, 없으면 마지막으로 검색한 장소 */
  const currentFavorite = useMemo<Favorite | null>(() => {
    const zone = zones.find((z) => z.zone_id === selectedRegion);
    if (zone) return zoneFavorite(zone);
    if (place) return placeFavorite(place.name, place.lat, place.lng);
    return null;
  }, [zones, selectedRegion, place]);
  const isFavoriteLinked = useCallback((f: Favorite) => !!f.zoneId && zones.some((z) => z.zone_id === f.zoneId), [zones]);
  /** 관심 구역 열기: 데이터가 연결된 구역이면 그 구역의 실시간 데이터(지도 뷰 + 구역 상세)로, 아니면 지도를 그 위치로 */
  const openFavorite = useCallback(
    (f: Favorite) => {
      if (f.zoneId && zones.some((z) => z.zone_id === f.zoneId)) {
        setPlace(null);
        setSearchNote(null);
        openZoneOnMap(f.zoneId);
        return;
      }
      setPlace({ name: f.name, lat: f.lat, lng: f.lng, seq: ++placeSeq.current });
      setSearchNote({
        tone: 'info',
        text: `"${f.name}" 위치로 이동했습니다. ${
          isDomestic(f.lat, f.lng) ? '연결된 밀도 데이터는 없습니다.' : '해외 지역은 가상 시뮬레이션으로 표시됩니다.'
        }`,
      });
      go('map');
    },
    [zones, openZoneOnMap, go],
  );

  // ---- 지표: 홈은 "가장 최근 관측", 지도는 슬라이더가 가리키는 프레임 기준 ----
  const latestFrame = lastObserved >= 0 ? frames[lastObserved] : undefined;
  const dashLatest = useMemo(() => buildDashboard(zones, latestFrame), [zones, latestFrame]);
  const dashShown = useMemo(() => buildDashboard(zones, frame), [zones, frame]);
  const alerts = useMemo(() => deriveAlerts(zones, frames), [zones, frames]);
  const peakValues = useMemo(() => peakSeries(frames), [frames]);
  const predictedFrom = useMemo(() => frames.findIndex((f) => f.kind === 'predicted'), [frames]);

  // 사이드바 맨 위 상태 표시: 시각은 하단 타임라인에 있으므로 간결하게
  const status: StatusInfo = useMemo(() => {
    if (frame?.kind === 'predicted') return { text: '● 예측', kind: 'pred' };
    if (liveStatus === 'open') return index >= lastObserved ? { text: '● 실시간 관측', kind: 'live' } : { text: '● 지난 시점', kind: 'past' };
    return { text: '● 관측', kind: 'obs' };
  }, [frame, liveStatus, index, lastObserved]);

  const homeStatus: StatusInfo =
    liveStatus === 'open' ? { text: '● 실시간 관측', kind: 'live' } : { text: '● 관측', kind: 'obs' };

  const badges = (
    <>
      {data?.source === 'mock' && <span className="badge mock">데모 데이터</span>}
      {LIVE_BADGE[liveStatus] && <span className={`badge live ${liveStatus}`}>{LIVE_BADGE[liveStatus]}</span>}
    </>
  );

  return (
    <div className="app">
      <AppHeader
        title={APP_NAME_EN}
        view={view}
        onChange={go}
        search={<SearchBox onSubmit={runSearch} note={searchNote} />}
        badges={badges}
      />

      <main className="view-area">
        {view === 'home' && (
          <section key="home" id="view-home" role="tabpanel" aria-labelledby="tab-home" className="view">
            <HomeView
              frame={latestFrame}
              dash={dashLatest}
              alerts={alerts}
              peakValues={peakValues}
              lastObservedIndex={Math.max(lastObserved, 0)}
              predictedFrom={predictedFrom}
              hasData={!!data}
              status={homeStatus}
              onOpenMap={() => go('map')}
              onOpenZone={openZoneOnMap}
              query={query}
            />
          </section>
        )}

        {(mapVisited || view === 'map') && (
          <section id="view-map" role="tabpanel" aria-labelledby="tab-map" className="view" hidden={view !== 'map'}>
            <MapView
              active={view === 'map'}
              hasData={!!data}
              error={error}
              zones={zones}
              frames={frames}
              frame={frame}
              dash={dashShown}
              status={status}
              index={index}
              playing={playing}
              onIndexChange={(i) => {
                setPlaying(false);
                following.current = i === lastObserved;
                setIndex(i);
              }}
              onTogglePlay={() => setPlaying((p) => !p)}
              selectedRegion={selectedRegion}
              selectedCell={selected}
              focus={focus}
              place={place}
              query={query}
              onCellSelect={handleCellSelect}
              onZoneSelect={handleZoneSelect}
              onListCellSelect={handleListCellSelect}
              onCloseRegion={closeRegion}
              favorites={favorites.items}
              currentFavorite={currentFavorite}
              isFavoriteLinked={isFavoriteLinked}
              onOpenFavorite={openFavorite}
              onAddFavorite={() => currentFavorite && favorites.add(currentFavorite)}
              onRemoveFavorite={favorites.remove}
            />
          </section>
        )}

        {view === 'analysis' && (
          <section key="analysis" id="view-analysis" role="tabpanel" aria-labelledby="tab-analysis" className="view">
            <AnalysisView
              zones={zones}
              frames={frames}
              index={index}
              dash={dashShown}
              selectedZoneId={selectedRegion}
              query={query}
            />
          </section>
        )}
      </main>
    </div>
  );
}
