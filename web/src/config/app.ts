// TODO: 프로젝트 명칭 확정 후 수정 (index.html <title>, vite.config.ts manifest 와 함께)
export const APP_NAME = '인파 밀집 모니터';
/** 상단 내비게이션 오른쪽에 표시하는 영문 서비스 제목 */
export const APP_NAME_EN = 'Crowd Density Monitoring System';

export const KAKAO_JS_KEY: string = import.meta.env.VITE_KAKAO_JS_KEY ?? '';
export const TIMELINE_URL: string = import.meta.env.VITE_TIMELINE_URL ?? '/timeline.json';
export const USE_MOCK: boolean = (import.meta.env.VITE_USE_MOCK ?? 'true') !== 'false';

/** 실시간 WebSocket 주소 (예: ws://localhost:8080/ws/zones). 비우면 실시간 연결을 하지 않는다. */
export const WS_URL: string = import.meta.env.VITE_WS_URL ?? '';

export const LIVE = {
  /** 메모리 보호: 유지할 프레임 최대 개수 (1초 1프레임이면 약 2분) */
  maxFrames: 120,
  reconnectMinMs: 1000,
  reconnectMaxMs: 15000,
};

/** 지도 초기 중심(서울시청). timeline 로드 후에는 구역 bounds 에 맞춰 재조정된다. */
export const DEFAULT_CENTER = { lat: 37.5663, lng: 126.9779 };
export const DEFAULT_MAP_LEVEL = 3;
