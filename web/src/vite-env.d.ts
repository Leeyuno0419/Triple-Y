/// <reference types="vite/client" />
/// <reference types="vite-plugin-pwa/client" />

interface ImportMetaEnv {
  readonly VITE_KAKAO_JS_KEY?: string;
  readonly VITE_TIMELINE_URL?: string;
  readonly VITE_USE_MOCK?: string;
  readonly VITE_WS_URL?: string;
}
