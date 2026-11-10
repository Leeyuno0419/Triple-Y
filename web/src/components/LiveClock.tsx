import { useEffect, useState } from 'react';

const pad = (n: number) => String(n).padStart(2, '0');

/** 초 단위로 갱신되는 실시간 시계 (예: 2026-11-10 11:58:42). 다음 정각 초에 맞춰 갱신해 건너뜀이 없다. */
export function LiveClock() {
  const [now, setNow] = useState(() => new Date());

  useEffect(() => {
    let timer: ReturnType<typeof setTimeout>;
    const tick = () => {
      setNow(new Date());
      timer = setTimeout(tick, 1000 - (Date.now() % 1000) + 5);
    };
    timer = setTimeout(tick, 1000 - (Date.now() % 1000) + 5);
    return () => clearTimeout(timer);
  }, []);

  const date = `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
  const time = `${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())}`;
  return (
    <time className="live-clock" dateTime={now.toISOString()}>
      {date} <b>{time}</b>
    </time>
  );
}
