let sdkPromise: Promise<void> | null = null;

/**
 * 카카오 지도 SDK 를 한 번만 동적 로드한다 (autoload=false → kakao.maps.load 로 초기화).
 * appKey 는 JavaScript 키이며, 카카오 콘솔에 접속 도메인이 등록되어 있어야 한다.
 */
export function loadKakaoSdk(appKey: string): Promise<void> {
  if (sdkPromise) return sdkPromise;
  if (!appKey) {
    return Promise.reject(new Error('VITE_KAKAO_JS_KEY 가 설정되지 않았습니다 (web/.env.local 확인).'));
  }

  sdkPromise = new Promise<void>((resolve, reject) => {
    const done = () => {
      if (!window.kakao?.maps) return reject(new Error('카카오 SDK 로드 후 kakao.maps 를 찾지 못했습니다.'));
      window.kakao.maps.load(() => resolve());
    };

    const existing = document.querySelector<HTMLScriptElement>('script[data-kakao-sdk]');
    if (existing) {
      existing.addEventListener('load', done);
      existing.addEventListener('error', () => reject(new Error('카카오 SDK 로드 실패')));
      return;
    }

    const script = document.createElement('script');
    script.dataset.kakaoSdk = 'true';
    script.async = true;
    script.src = `https://dapi.kakao.com/v2/maps/sdk.js?appkey=${encodeURIComponent(appKey)}&autoload=false`;
    script.onload = done;
    script.onerror = () => reject(new Error('카카오 SDK 로드 실패 (키/도메인 등록/네트워크 확인)'));
    document.head.appendChild(script);
  }).catch((err) => {
    sdkPromise = null; // 실패 시 재시도 허용
    throw err;
  });

  return sdkPromise;
}
