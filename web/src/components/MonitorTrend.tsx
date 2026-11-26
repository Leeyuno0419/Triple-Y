import { useMemo } from 'react';
import { CHART_COLORS } from '../config/density';
import { peakSeries, predictedPeakSeries } from '../lib/dashboard';
import type { Frame } from '../types/timeline';
import { TrendChart } from './TrendChart';

interface Props {
  frames: Frame[];
  index: number;
  horizonS: number;
  bounds?: number[];
}

/** 재생 바 위 추이 그래프: 관측 최대 밀도와 60초 예측(예측 대상 시각에 표시) */
export function MonitorTrend({ frames, index, horizonS, bounds }: Props) {
  const data = useMemo(() => {
    const lastT = frames[frames.length - 1]?.t ?? 0;
    const future = Array.from({ length: horizonS }, (_, k) => k);
    return {
      times: [...frames.map((f) => f.t), ...future.map((k) => lastT + 1 + k)],
      observed: [...peakSeries(frames, 'now'), ...future.map(() => null)],
      predicted: predictedPeakSeries(frames, horizonS),
    };
  }, [frames, horizonS]);

  return (
    <div className="monitor-trend">
      <div className="card-title">
        <h3>최대 밀도 추이</h3>
        <small>명/m² · 점선 = {horizonS}초 예측</small>
      </div>
      <TrendChart
        compact
        times={data.times}
        futureFrom={frames.length}
        current={index}
        bounds={bounds}
        series={[
          { label: '관측', color: CHART_COLORS.max, values: data.observed },
          { label: `${horizonS}초 예측`, color: CHART_COLORS.mean, values: data.predicted, dashed: true },
        ]}
      />
    </div>
  );
}
