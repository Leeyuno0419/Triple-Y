import { useEffect, useRef, useState } from 'react';
import { DENSITY_BAR_MAX, DENSITY_LEVELS } from '../config/density';

export interface TrendSeries {
  label: string;
  color: string;
  values: number[];
}

interface Props {
  series: TrendSeries[];
  /** 프레임 시각(ISO). series.values 와 같은 길이 */
  times: string[];
  /** 예측 프레임이 시작되는 인덱스 (없으면 -1) */
  predictedFrom: number;
  /** 지금 보고 있는 프레임 */
  current: number;
}

const MIN_W = 280;
const MIN_H = 140;
const PAD = { l: 40, r: 14, t: 14, b: 28 };
const hhmmss = (iso: string) => new Date(iso).toLocaleTimeString('ko-KR', { hour12: false });

/** 밀도 추이 꺾은선 그래프. 단계 임계값 가로선, 예측 구간 음영·점선, 현재 위치 세로선. */
export function TrendChart({ series, times, predictedFrom, current }: Props) {
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

  const top = Math.max(DENSITY_BAR_MAX, Math.ceil(Math.max(0, ...series.flatMap((s) => s.values)) + 0.3));
  const x = (i: number) => PAD.l + (i / (n - 1)) * (W - PAD.l - PAD.r);
  const y = (v: number) => PAD.t + (1 - v / top) * (H - PAD.t - PAD.b);
  const pts = (vals: number[], from: number, to: number) =>
    vals.slice(from, to + 1).map((v, k) => `${x(from + k).toFixed(1)},${y(v).toFixed(1)}`).join(' ');

  const obsEnd = predictedFrom > 0 ? predictedFrom - 1 : n - 1;
  const ticks = Array.from({ length: top + 1 }, (_, i) => i);
  const thresholds = DENSITY_LEVELS.slice(0, -1).map((l, i) => ({ value: l.max, label: DENSITY_LEVELS[i + 1].label }));
  const labelIdx = Array.from(new Set([0, Math.floor((n - 1) / 2), n - 1]));

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
        {predictedFrom > 0 && (
          <rect x={x(predictedFrom - 1)} y={PAD.t} width={x(n - 1) - x(predictedFrom - 1)} height={H - PAD.t - PAD.b} className="tc-pred" />
        )}
        {thresholds.map((t) => (
          <g key={t.label}>
            <line x1={PAD.l} x2={W - PAD.r} y1={y(t.value)} y2={y(t.value)} className="tc-threshold" />
            <text x={W - PAD.r - 2} y={y(t.value) - 4} textAnchor="end" className="tc-text strong">{t.label}↑</text>
          </g>
        ))}
        {series.map((s) => (
          <g key={s.label}>
            <polyline points={pts(s.values, 0, obsEnd)} className="tc-line" style={{ stroke: s.color }} />
            {predictedFrom > 0 && (
              <polyline points={pts(s.values, predictedFrom - 1, n - 1)} className="tc-line pred" style={{ stroke: s.color }} />
            )}
          </g>
        ))}
        <line x1={x(current)} x2={x(current)} y1={PAD.t} y2={H - PAD.b} className="tc-now" />
        {labelIdx.map((i) => (
          <text key={i} x={x(i)} y={H - 8} textAnchor={i === 0 ? 'start' : i === n - 1 ? 'end' : 'middle'} className="tc-text">
            {hhmmss(times[i])}
          </text>
        ))}
      </svg>
      </div>
      <ul className="trend-legend">
        {series.map((s) => (
          <li key={s.label}><i style={{ background: s.color }} />{s.label}</li>
        ))}
        {predictedFrom > 0 && <li><i className="pred" />예측 구간</li>}
      </ul>
    </div>
  );
}
