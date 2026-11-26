import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { API_URL, APP_NAME_EN, LIVE, WS_URL } from './config/app';
import { AppHeader, type ViewId } from './components/AppHeader';
import type { VideoStatus } from './components/CellHeatmap';
import { ackAlert } from './lib/alertApi';
import { deriveAlerts } from './lib/alerts';
import { buildDashboard, futurePeaks, peakSeries } from './lib/dashboard';
import type { StatusInfo } from './lib/format';
import { thresholdBounds } from './lib/grade';
import { applyLiveMessage, INITIAL_LIVE_STATE, markAck, removeAlert, type LiveState } from './lib/liveFeed';
import type { ViewMode } from './lib/model';
import type { LiveMessage } from './types/live';
import type { VideoEntry } from './lib/videoLibrary';
import { loadTimeline, type LoadResult } from './lib/timeline';
import { useLiveFeed, type LiveStatus } from './lib/useLiveFeed';
import { frameIndexAtTime, videoUrl } from './lib/video';
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
  // 정적 timeline 파일(서버 없이 볼 때)과 서버 실시간 상태를 따로 둔다. 실시간 hello 가 오면 실시간이 우선한다.
  const [staticData, setStaticData] = useState<LoadResult | null>(null);
  const [live, setLive] = useState<LiveState>(INITIAL_LIVE_STATE);
  // 영상 관리에서 고른 등록 영상. null 이면 기본(설정 파일) 영상. 실시간 데이터가 있으면 실시간이 우선한다.
  const [picked, setPicked] = useState<{ entry: VideoEntry; src: string } | null>(null);
  const data = useMemo<LoadResult | null>(() => {
    if (live.timeline) return { timeline: live.timeline, source: 'live' };
    if (picked?.entry.timeline) return { timeline: picked.entry.timeline, source: 'library' };
    return staticData;
  }, [live.timeline, picked, staticData]);
  // 로컬 파일로 만든 주소는 다른 영상으로 바꾸면 해제한다
  useEffect(() => {
    const src = picked?.src;
    return () => {
      if (src?.startsWith('blob:')) URL.revokeObjectURL(src);
    };
  }, [picked]);
  const [error, setError] = useState<string | null>(null);
  const [index, setIndex] = useState(0); // frames 배열 위치 (영상 시간 t 와 같지 않을 수 있다: 실시간은 최근 프레임만 유지)
  const [playing, setPlaying] = useState(false);
  const [mode, setMode] = useState<ViewMode>('now'); // 히트맵에 보여 줄 값: 현재 관측 / 60초 뒤 예측
  const [selectedCellId, setSelectedCellId] = useState<string | null>(null);
  const [view, setView] = useState<ViewId>(parseHash);
  // 영상 상태: 'ready' 이면 재생 중 영상이 시간의 기준이고, 아니면(영상 없음·실패) 1초 타이머로 재생한다
  const [videoState, setVideoState] = useState<VideoStatus>('none');
  const liveReceived = useRef(false); // 실시간 데이터가 한 번이라도 왔는가
  const following = useRef(true); // 슬라이더가 "현재(마지막 프레임)"에 있어 새 프레임을 따라가는가

  useEffect(() => {
    const ctrl = new AbortController();
    loadTimeline(ctrl.signal)
      .then((res) => {
        if (liveReceived.current) return; // 실시간 데이터가 먼저 왔으면 덮어쓰지 않는다
        setStaticData(res);
        setIndex(Math.max(res.timeline.frames.length - 1, 0)); // 처음에는 "현재"(마지막 프레임)를 보여준다.
      })
      .catch((e: Error) => !ctrl.signal.aborted && setError(e.message));
    return () => ctrl.abort();
  }, []);

  // 실시간(WebSocket) 수신 (docs/api-spec.md 3절): hello·zone_state·alert·playback 4종을 liveFeed.ts 가 상태에 반영한다.
  const onLive = useCallback((msg: LiveMessage) => {
    liveReceived.current = true;
    setError(null);
    // 반복 재생으로 처음(t=0)으로 돌아왔다: 쌓아 둔 프레임은 liveFeed 가 비우고, 화면은 0초(최신)로 따라간다
    if (msg.type === 'playback' && msg.playback.state === 'playing' && msg.playback.t === 0) {
      following.current = true;
      setPlaying(false);
      setIndex(0);
    }
    setLive((prev) => {
      try {
        return applyLiveMessage(prev, msg, LIVE.maxFrames);
      } catch (err) {
        console.warn('[live] 메시지 무시:', err);
        return prev;
      }
    });
  }, []);
  const liveStatus = useLiveFeed(WS_URL, onLive);

  // 알림 '확인': POST /api/alerts/{alert_id}/ack 가 성공하면 목록에서 지운다. 실패하면 남기고 '다시 시도'를 보여 준다.
  const onAck = useCallback(async (alertId: string) => {
    setLive((prev) => markAck(prev, alertId, 'pending'));
    try {
      await ackAlert(API_URL, alertId);
      setLive((prev) => removeAlert(prev, alertId));
    } catch (err) {
      console.warn('[live] 알림 확인 실패:', err);
      setLive((prev) => markAck(prev, alertId, 'error'));
    }
  }, []);

  const meta = data?.timeline.meta;
  const frames = useMemo(() => data?.timeline.frames ?? [], [data]);
  const lastIndex = frames.length - 1;
  const frame = frames[Math.min(index, Math.max(lastIndex, 0))];
  const horizon = meta?.prediction.horizon_s ?? 60;

  // 새 프레임이 오면 "현재"를 보고 있던 경우에만 따라간다 (과거를 보는 중이면 그대로 둔다).
  useEffect(() => {
    if (data?.source === 'live' && following.current) setIndex(Math.max(lastIndex, 0));
  }, [data?.source, lastIndex, frames.length]);

  // 재생(타이머): 영상이 없거나 열 수 없을 때만 쓴다. 끝에 닿으면 정지
  useEffect(() => {
    if (!playing || videoState === 'ready') return;
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
  }, [playing, videoState, frames.length]);

  // 재생(영상 기준): 영상 시각에 해당하는 프레임을 보여 준다
  const videoId = meta?.video_id;
  const videoSrc = data?.source === 'library' ? picked?.src : videoId ? videoUrl(videoId) : undefined;
  const onVideoTime = useCallback(
    (sec: number) => {
      // 실시간에서 최신 프레임을 따라가는 중에는 서버 프레임이 시간의 기준이다. 영상은 그 t 에 맞춰 따라올 뿐이라
      // 영상 시각으로 프레임을 고르지 않는다. 고르면 영상이 조금만 늦어도 '지난 시점'으로 빠져 영상이 멈춘다.
      if (data?.source === 'live' && !playing && following.current) return;
      const i = frameIndexAtTime(frames, sec);
      following.current = i >= frames.length - 1;
      setIndex(i);
    },
    [frames, data?.source, playing],
  );
  const onVideoEnded = useCallback(() => setPlaying(false), []);
  // 영상은 사용자가 재생 중이거나, 실시간에서 최신 프레임을 따라가는 중일 때 재생한다
  // 새 프레임이 막 도착한 렌더에서는 index 가 아직 lastIndex 를 따라가기 전이다. 그때 index 만 보면 한 번 '정지'로 판단해
  // 영상을 이전 t 로 되감았다가 다시 재생한다(1초마다 끊김). 따라가는 중인지는 following 으로 본다.
  const videoPlaying = playing || (data?.source === 'live' && (following.current || index >= lastIndex));

  /** 영상 관리에서 고른 영상으로 바꾼다 (null = 기본 영상). 등록 영상은 처음부터, 기본 영상은 마지막 프레임부터 보여 준다 */
  const onSelectVideo = useCallback(
    (entry: VideoEntry | null) => {
      const src = entry ? (entry.file ? URL.createObjectURL(entry.file) : entry.url) : undefined;
      setPicked(entry && src ? { entry, src } : null);
      setPlaying(false);
      setSelectedCellId(null);
      setIndex(entry ? 0 : Math.max((staticData?.timeline.frames.length ?? 0) - 1, 0));
    },
    [staticData],
  );

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

  const bounds = useMemo(() => thresholdBounds(live.thresholds), [live.thresholds]); // 범례·그래프 기준선 (서버 hello.thresholds)
  // 서버에 연결된 뒤(hello 를 받은 뒤)에는 서버 알림만 보여 준다. 그 전에는 프레임 이력에서 파생한 알림을 쓴다.
  const liveAlerts = live.timeline ? live.alerts : null;

  const badges = (
    <>
      {data?.source === 'mock' && <span className="badge mock">데모 데이터</span>}
      {LIVE_BADGE[liveStatus] && <span className={`badge live ${liveStatus}`}>{LIVE_BADGE[liveStatus]}</span>}
      {live.playback?.state === 'ended' && <span className="badge live ended">피드 종료</span>}
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
              liveAlerts={liveAlerts}
              onAck={onAck}
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
              error={data?.source === 'library' ? null : error}
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
              videoSrc={videoSrc}
              videoPlaying={videoPlaying}
              onVideoTime={onVideoTime}
              onVideoStatus={setVideoState}
              onVideoEnded={onVideoEnded}
              bounds={bounds}
              alerts={alerts}
              liveAlerts={liveAlerts}
              onAck={onAck}
              selectedVideoId={data?.source === 'library' ? (picked?.entry.id ?? null) : null}
              videoName={data?.source === 'library' ? (picked?.entry.name ?? '') : (meta?.video_id ?? '')}
              defaultVideoName={staticData?.timeline.meta.video_id ?? '기본 영상'}
              isLive={data?.source === 'live'}
              onSelectVideo={onSelectVideo}
            />
          </section>
        )}

        {view === 'analysis' && (
          <section key="analysis" id="view-analysis" role="tabpanel" aria-labelledby="tab-analysis" className="view">
            <AnalysisView meta={meta} frames={frames} index={index} dash={dashShownNow} bounds={bounds} />
          </section>
        )}
      </main>
    </div>
  );
}
