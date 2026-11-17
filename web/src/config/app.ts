import { apiBaseFromWs, resolveWsUrl } from '../lib/liveFeed';

// TODO: 프로젝트 명칭 확정 후 수정 (index.html <title>, vite.config.ts manifest 와 함께)
export const APP_NAME = '인파 밀집 모니터';
/** 상단 내비게이션 오른쪽에 표시하는 영문 서비스 제목 */
export const APP_NAME_EN = 'Crowd Density Monitoring System';

export const KAKAO_JS_KEY: string = import.meta.env.VITE_KAKAO_JS_KEY ?? '';
export const TIMELINE_URL: string = import.meta.env.VITE_TIMELINE_URL ?? '/timeline.json';
export const USE_MOCK: boolean = (import.meta.env.VITE_USE_MOCK ?? 'true') !== 'false';

/** 영상 폴더 URL. 영상 파일은 `${VIDEO_BASE_URL}/${meta.video_id}.mp4` 로 찾는다 (docs/api-spec.md 6절). 원본 영상은 git 에 올리지 않는다. */
export const VIDEO_BASE_URL: string = import.meta.env.VITE_VIDEO_BASE_URL ?? '/videos';

/**
 * 디버그 모드: 주소에 `?debug=grid` 를 붙이면(예: http://localhost:5173/?debug=grid#/monitor) 영상 위에 셀 번호·모서리 좌표·정렬 점검 표시를 얹는다.
 * 셀 격자가 영상 바닥과 맞는지, 영상과 타임라인의 짝이 맞는지 볼 때 쓴다. 화면을 불러올 때 한 번만 읽으므로 바꾸면 새로고침한다.
 */
export const DEBUG_GRID: boolean =
  typeof window !== 'undefined' && new URLSearchParams(window.location.search).get('debug') === 'grid';

/**
 * 실시간 WebSocket 주소. 서버 경로는 /ws/zones/{zone_id} 다 (docs/api-spec.md 2절).
 * VITE_WS_URL 은 'ws://localhost:8080/ws/zones/{zone_id}'(구역 ID 는 VITE_ZONE_ID),
 * 'ws://localhost:8080/ws/zones'(뒤에 VITE_ZONE_ID 를 붙임), 또는 구역 ID 까지 쓴 전체 주소를 받는다.
 * 비우면 실시간 연결을 하지 않는다.
 */
export const WS_URL: string = resolveWsUrl(import.meta.env.VITE_WS_URL ?? '', import.meta.env.VITE_ZONE_ID ?? '');

/**
 * REST(알림 확인 등) 서버 주소. 비우면 WebSocket 주소의 서버를 쓴다 (ws://localhost:8080/... → http://localhost:8080).
 * WebSocket 을 쓰지 않으면 같은 출처('')다.
 */
export const API_URL: string = (import.meta.env.VITE_API_URL ?? '').trim().replace(/\/$/, '') || apiBaseFromWs(WS_URL);

export const LIVE = {
  /** 메모리 보호: 유지할 프레임 최대 개수 (1초 1프레임이면 약 2분) */
  maxFrames: 120,
  /** 재접속 간격: 1초, 2초, 4초, 이후 5초 (docs/api-spec.md 3.5절) */
  reconnectMinMs: 1000,
  reconnectMaxMs: 5000,
};

/** 지도 초기 중심(서울시청). timeline 로드 후에는 구역 bounds 에 맞춰 재조정된다. */
export const DEFAULT_CENTER = { lat: 37.5663, lng: 126.9779 };
export const DEFAULT_MAP_LEVEL = 3;
