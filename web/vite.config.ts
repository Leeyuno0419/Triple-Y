import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { VitePWA } from 'vite-plugin-pwa';

// TODO: 프로젝트 확정 후 name / short_name 변경 (src/config/app.ts 와 맞출 것)
export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      registerType: 'autoUpdate',
      includeAssets: ['icons/*.png'],
      manifest: {
        name: '인파 밀집 모니터',
        short_name: '인파모니터',
        description: '셀 단위 인파 밀도 지도 시각화',
        lang: 'ko',
        display: 'standalone',
        orientation: 'portrait',
        start_url: '/',
        background_color: '#f8f9fa',
        theme_color: '#f8f9fa',
        icons: [
          { src: 'icons/icon-192.png', sizes: '192x192', type: 'image/png' },
          { src: 'icons/icon-512.png', sizes: '512x512', type: 'image/png' },
          { src: 'icons/icon-512.png', sizes: '512x512', type: 'image/png', purpose: 'maskable' },
        ],
      },
      workbox: {
        // 앱 셸은 캐시, 실시간성 데이터(timeline)는 네트워크 우선.
        // 카카오 SDK/타일은 외부 도메인이라 캐시하지 않는다.
        runtimeCaching: [
          {
            urlPattern: ({ url }: { url: URL }) =>
              url.pathname.endsWith('timeline.json') || url.pathname.startsWith('/api/'),
            handler: 'NetworkFirst',
            options: { cacheName: 'timeline-data', networkTimeoutSeconds: 5 },
          },
          {
            // 폰트 서브셋은 사용한 것만 한 번 받아 오래 캐시 (precache 에는 넣지 않는다)
            urlPattern: ({ request }: { request: Request }) => request.destination === 'font',
            handler: 'CacheFirst',
            options: {
              cacheName: 'fonts',
              expiration: { maxEntries: 120, maxAgeSeconds: 60 * 60 * 24 * 365 },
            },
          },
        ],
      },
    }),
  ],
});
