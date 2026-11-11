import { useEffect, useRef, useState } from 'react';
import { LIVE } from '../config/app';
import { parseLiveMessage, type LiveMessage } from './liveFeed';

export type LiveStatus = 'idle' | 'connecting' | 'open' | 'reconnecting';

/**
 * WebSocket 으로 실시간 메시지를 받는다. 끊기면 지수 백오프(최소→최대)로 자동 재연결한다.
 * url 이 비어 있으면 아무것도 하지 않는다(status 'idle').
 */
export function useLiveFeed(url: string, onMessage: (msg: LiveMessage) => void): LiveStatus {
  const [status, setStatus] = useState<LiveStatus>(url ? 'connecting' : 'idle');
  const handlerRef = useRef(onMessage);
  handlerRef.current = onMessage;

  useEffect(() => {
    if (!url) return;
    let ws: WebSocket | null = null;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let delay = LIVE.reconnectMinMs;
    let disposed = false;

    const connect = () => {
      setStatus((s) => (s === 'open' || s === 'reconnecting' ? 'reconnecting' : 'connecting'));
      ws = new WebSocket(url);

      ws.onopen = () => {
        delay = LIVE.reconnectMinMs;
        setStatus('open');
      };
      ws.onmessage = (ev) => {
        try {
          handlerRef.current(parseLiveMessage(String(ev.data)));
        } catch (err) {
          console.warn('[live] 메시지 무시:', err);
        }
      };
      ws.onclose = () => {
        if (disposed) return;
        setStatus('reconnecting');
        timer = setTimeout(connect, delay);
        delay = Math.min(delay * 2, LIVE.reconnectMaxMs);
      };
      ws.onerror = () => ws?.close(); // onclose 에서 재연결 처리
    };

    connect();
    return () => {
      disposed = true;
      clearTimeout(timer);
      ws?.close();
    };
  }, [url]);

  return status;
}
