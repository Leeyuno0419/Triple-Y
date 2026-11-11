import { useEffect, useRef, useState } from 'react';
import { DENSITY_BAR_MAX, DENSITY_LEVELS } from '../config/density';
import { fmtClock } from '../lib/format';

export interface TrendSeries {
  label: string;
  color: string;
  /** times 와 같은 길이. null 은 값 없음(선을 끊는다) */
  values: Array<number | null>;
  /** 예측 선(점선)인가 */
  dashed?: boolean;
}

interface Props {
  series: TrendSeries[];
  /** 각 지점의 시각(영상 시작 뒤 경과 초). series.values 와 같은 길이 */
  times: number[];
  /** 예측만 있는 미래 구간이 시작되는 인덱스 (없으면 -1) */
  futureFrom: number;
  /** 지금 보고 있는 프레임 */
  current: number;
}

const MIN_W = 280;
const MIN_H = 140;
const PAD = { l: 40, r: 14, t: 14, b: 28 };

/** 값이 이어지는 구간(null 로 끊긴 덩어리)마다 하나씩 점 목록을 만든다. */
function runs(values: Array<number | null>, x: (i: number) => number, y: (v: number) => number): string[] {
  const out: string[] = [];
  let cur: string[] = [];
  values.forEach((v, i) => {
    if (v === null) {
      if (cur.length) out.push(cur.join(' '));
      cur = [];
    } else {
      cur.push(`${x(i).toFixed(1)},${y(v).toFixed(1)}`);
    }
  });
  if (cur.length) out.push(cur.join(' '));
  return out;
}

/** 밀도 추이 꺾은선 그래프. 단계 임계값 가로선, 예측 구간 음영·점선, 현재 위치 세로선. */
export function TrendChart({ series, times, futureFrom, current }: Props) {
  // 부모 크기에 맞춰 SVG 를 다시 그린다 (글자가 늘어나지 않도록 viewBox 를 실제 픽셀 크기로 맞춘다)
  const plotRef = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState({ w: 640, h: 240 });
  useEffect(() => {
    const el = plotRef.current;
    if (!el || typeof ResizeObserver === 'undefined') return;
    const ro = new ResizeObserver(([entry]) => {
      const { width, height } = entry.contentRect;
      setSize({ w: Math.max(MIN_W, Math.round(width)), h: Math.max(MIN_H, Math.round(height)) });
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, [times.length < 2]); // 그래프가 처음 그려질 때(프레임 2개 이상) 관찰 시작
  const { w: W, h: H } = size;

  const n = times.length;
  if (n < 2) return <p className="empty">추이를 그리려면 프레임이 2개 이상 필요합니다.</p>;

  const all = series.flatMap((s) => s.values).filter((v): v is number => v !== null);
  const top = Math.max(DENSITY_BAR_MAX, Math.ceil(Math.max(0, ...all) + 0.3));
  const x = (i: number) => PAD.l + (i / (n - 1)) * (W - PAD.l - PAD.r);
  const y = (v: number) => PAD.t + (1 - v / top) * (H - PAD.t - PAD.b);

  const ticks = Array.from({ length: top + 1 }, (_, i) => i);
  const thresholds = DENSITY_LEVELS.slice(0, -1).map((l, i) => ({ value: l.max, label: DENSITY_LEVELS[i + 1].label }));
  const labelIdx = Array.from(new Set([0, Math.floor((n - 1) / 2), n - 1]));
  const hasFuture = futureFrom > 0 && futureFrom < n;

  return (
    <div className="trend">
      <div className="trend-plot" ref={plotRef}>
      <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`밀도 추이: ${series.map((s) => s.label).join(', ')}`}>
        {ticks.map((t) => (
          <g key={t}>
            <line x1={PAD.l} x2={W - PAD.r} y1={y(t)} y2={y(t)} className="tc-grid" />
            <text x={PAD.l - 8} y={y(t) + 3} textAnchor="end" className="tc-text">{t}</text>
          </g>
        ))}
        {hasFuture && (
          <rect x={x(futureFrom - 1)} y={PAD.t} width={x(n - 1) - x(futureFrom - 1)} height={H - PAD.t - PAD.b} className="tc-pred" />
        )}
        {thresholds.map((t) => (
          <g key={t.label}>
            <line x1={PAD.l} x2={W - PAD.r} y1={y(t.value)} y2={y(t.value)} className="tc-threshold" />
            <text x={W - PAD.r - 2} y={y(t.value) - 4} textAnchor="end" className="tc-text strong">{t.label}↑</text>
          </g>
        ))}
        {series.map((s) => (
          <g key={s.label}>
            {runs(s.values, x, y).map((points, k) => (
              <polyline key={k} points={points} className={`tc-line${s.dashed ? ' pred' : ''}`} style={{ stroke: s.color }} />
            ))}
          </g>
        ))}
        <line x1={x(current)} x2={x(current)} y1={PAD.t} y2={H - PAD.b} className="tc-now" />
        {labelIdx.map((i) => (
          <text key={i} x={x(i)} y={H - 8} textAnchor={i === 0 ? 'start' : i === n - 1 ? 'end' : 'middle'} className="tc-text">
            {fmtClock(times[i])}
          </text>
        ))}
      </svg>
      </div>
      <ul className="trend-legend">
        {series.map((s) => (
          <li key={s.label}><i style={{ background: s.color }} />{s.label}</li>
        ))}
        {hasFuture && <li><i className="pred" />예측 구간</li>}
      </ul>
    </div>
  );
}
