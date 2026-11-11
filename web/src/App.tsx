import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { APP_NAME_EN, LIVE, WS_URL } from './config/app';
import { AppHeader, type ViewId } from './components/AppHeader';
import { deriveAlerts } from './lib/alerts';
import { buildDashboard, futurePeaks, peakSeries } from './lib/dashboard';
import type { StatusInfo } from './lib/format';
import { applyLiveMessage, type LiveMessage } from './lib/liveFeed';
import type { ViewMode } from './lib/model';
import { loadTimeline, type LoadResult } from './lib/timeline';
import { useLiveFeed, type LiveStatus } from './lib/useLiveFeed';
import { AnalysisView } from './views/AnalysisView';
import { HomeView } from './views/HomeView';
import { MonitorView } from './views/MonitorView';

const PLAY_INTERVAL_MS = 1000;

const VIEWS: ViewId[] = ['home', 'monitor', 'analysis'];
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
  const [index, setIndex] = useState(0); // frames 배열 위치 (영상 시간 t 와 같지 않을 수 있다: 실시간은 최근 프레임만 유지)
  const [playing, setPlaying] = useState(false);
  const [mode, setMode] = useState<ViewMode>('now'); // 히트맵에 보여 줄 값: 현재 관측 / 60초 뒤 예측
  const [selectedCellId, setSelectedCellId] = useState<string | null>(null);
  const [view, setView] = useState<ViewId>(parseHash);
  const liveReceived = useRef(false); // 실시간 데이터가 한 번이라도 왔는가
  const following = useRef(true); // 슬라이더가 "현재(마지막 프레임)"에 있어 새 프레임을 따라가는가

  useEffect(() => {
    const ctrl = new AbortController();
    loadTimeline(ctrl.signal)
      .then((res) => {
        if (liveReceived.current) return; // 실시간 데이터가 먼저 왔으면 덮어쓰지 않는다
        setData(res);
        setIndex(Math.max(res.timeline.frames.length - 1, 0)); // 처음에는 "현재"(마지막 프레임)를 보여준다.
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
        const next = applyLiveMessage(prev?.timeline ?? null, msg, LIVE.maxFrames);
        return next ? { timeline: next, source: 'live' } : prev;
      } catch (err) {
        console.warn('[live] 프레임 무시:', err);
        return prev;
      }
    });
  }, []);
  const liveStatus = useLiveFeed(WS_URL, onLive);

  const meta = data?.timeline.meta;
  const frames = useMemo(() => data?.timeline.frames ?? [], [data]);
  const lastIndex = frames.length - 1;
  const frame = frames[Math.min(index, Math.max(lastIndex, 0))];
  const horizon = meta?.prediction.horizon_s ?? 60;

  // 새 프레임이 오면 "현재"를 보고 있던 경우에만 따라간다 (과거를 보는 중이면 그대로 둔다).
  useEffect(() => {
    if (data?.source === 'live' && following.current) setIndex(Math.max(lastIndex, 0));
  }, [data?.source, lastIndex, frames.length]);

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

  // ---- 화면 전환: state 로 분기하고, URL 해시(#/monitor 등)와 동기화해 뒤로가기·새로고침을 지원한다 ----
  const go = useCallback((next: ViewId) => {
    setView(next);
    if (window.location.hash !== `#/${next}`) window.location.hash = `#/${next}`;
  }, []);
  useEffect(() => {
    const onHash = () => setView(parseHash());
    window.addEventListener('hashchange', onHash);
    return () => window.removeEventListener('hashchange', onHash);
  }, []);

  /** 홈에서 셀을 누르면: 셀 선택 + 모니터 뷰로 이동 */
  const openCell = useCallback(
    (cellId: string) => {
      setSelectedCellId(cellId);
      go('monitor');
    },
    [go],
  );

  // ---- 지표: 홈은 "가장 최근 프레임", 모니터는 슬라이더가 가리키는 프레임 기준 ----
  const latestFrame = lastIndex >= 0 ? frames[lastIndex] : undefined;
  const dashLatest = useMemo(() => (meta ? buildDashboard(meta, latestFrame, 'now') : null), [meta, latestFrame]);
  const dashLatestPred = useMemo(() => (meta ? buildDashboard(meta, latestFrame, 'pred') : null), [meta, latestFrame]);
  const dashShown = useMemo(() => (meta ? buildDashboard(meta, frame, mode) : null), [meta, frame, mode]);
  const dashShownNow = useMemo(() => (meta ? buildDashboard(meta, frame, 'now') : null), [meta, frame]);
  const alerts = useMemo(() => (meta ? deriveAlerts(meta, frames) : []), [meta, frames]);
  const homePeaks = useMemo(() => {
    const observed = peakSeries(frames, 'now');
    const future = futurePeaks(frames, horizon);
    return { values: [...observed, ...future], futureFrom: future.length > 0 ? observed.length : -1 };
  }, [frames, horizon]);

  // 모니터 사이드바 맨 위 상태 표시: 시각은 하단 타임라인에 있으므로 간결하게
  const status: StatusInfo = useMemo(() => {
    if (mode === 'pred') return { text: '● 예측', kind: 'pred' };
    if (liveStatus === 'open') return index >= lastIndex ? { text: '● 실시간 관측', kind: 'live' } : { text: '● 지난 시점', kind: 'past' };
    return { text: '● 관측', kind: 'obs' };
  }, [mode, liveStatus, index, lastIndex]);

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
      <AppHeader title={APP_NAME_EN} view={view} onChange={go} badges={badges} />

      <main className="view-area">
        {view === 'home' && (
          <section key="home" id="view-home" role="tabpanel" aria-labelledby="tab-home" className="view">
            <HomeView
              meta={meta}
              frame={latestFrame}
              dash={dashLatest}
              dashPred={dashLatestPred}
              alerts={alerts}
              peakValues={homePeaks.values}
              lastIndex={Math.max(lastIndex, 0)}
              futureFrom={homePeaks.futureFrom}
              hasData={!!data}
              status={homeStatus}
              onOpenMonitor={() => go('monitor')}
              onOpenCell={openCell}
            />
          </section>
        )}

        {view === 'monitor' && (
          <section id="view-monitor" role="tabpanel" aria-labelledby="tab-monitor" className="view">
            <MonitorView
              hasData={!!data}
              error={error}
              meta={meta}
              frames={frames}
              frame={frame}
              dash={dashShown}
              mode={mode}
              onModeChange={setMode}
              status={status}
              index={index}
              playing={playing}
              onIndexChange={(i) => {
                setPlaying(false);
                following.current = i === lastIndex;
                setIndex(i);
              }}
              onTogglePlay={() => setPlaying((p) => !p)}
              selectedCellId={selectedCellId}
              onCellSelect={setSelectedCellId}
            />
          </section>
        )}

        {view === 'analysis' && (
          <section key="analysis" id="view-analysis" role="tabpanel" aria-labelledby="tab-analysis" className="view">
            <AnalysisView meta={meta} frames={frames} index={index} dash={dashShownNow} />
          </section>
        )}
      </main>
    </div>
  );
}
