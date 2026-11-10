import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { APP_NAME, LIVE, WS_URL } from './config/app';
import { AppHeader, type ViewId } from './components/AppHeader';
import type { CellRef } from './components/DensityLayer';
import type { FocusTarget } from './components/MapFocus';
import { deriveAlerts } from './lib/alerts';
import { buildDashboard, peakSeries } from './lib/dashboard';
import { applyLiveMessage, type LiveMessage } from './lib/liveFeed';
import { loadTimeline, type LoadResult } from './lib/timeline';
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

  // ---- 지표: 홈은 "가장 최근 관측", 지도는 슬라이더가 가리키는 프레임 기준 ----
  const latestFrame = lastObserved >= 0 ? frames[lastObserved] : undefined;
  const dashLatest = useMemo(() => buildDashboard(zones, latestFrame), [zones, latestFrame]);
  const dashShown = useMemo(() => buildDashboard(zones, frame), [zones, frame]);
  const alerts = useMemo(() => deriveAlerts(zones, frames), [zones, frames]);
  const peakValues = useMemo(() => peakSeries(frames), [frames]);
  const predictedFrom = useMemo(() => frames.findIndex((f) => f.kind === 'predicted'), [frames]);

  const badges = (
    <>
      {data?.source === 'mock' && <span className="badge mock">mock 데이터</span>}
      {LIVE_BADGE[liveStatus] && <span className={`badge live ${liveStatus}`}>{LIVE_BADGE[liveStatus]}</span>}
    </>
  );

  return (
    <div className="app">
      <AppHeader title={APP_NAME} view={view} onChange={go} badges={badges} />

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
              onOpenMap={() => go('map')}
              onOpenZone={openZoneOnMap}
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
              onCellSelect={handleCellSelect}
              onZoneSelect={handleZoneSelect}
              onListCellSelect={handleListCellSelect}
              onCloseRegion={closeRegion}
            />
          </section>
        )}

        {view === 'analysis' && (
          <section key="analysis" id="view-analysis" role="tabpanel" aria-labelledby="tab-analysis" className="view">
            <AnalysisView zones={zones} frames={frames} index={index} dash={dashShown} initialZoneId={selectedRegion} />
          </section>
        )}
      </main>
    </div>
  );
}
