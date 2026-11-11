import { useMemo } from 'react';
import { GradeBadge } from '../components/GradeBadge';
import { CHART_COLORS } from '../config/density';
import { EyeIcon, PulseIcon, UsersIcon, AlertIcon } from '../components/Icons';
import { KpiCard } from '../components/KpiCard';
import { TrendChart } from '../components/TrendChart';
import { hotCellsFor, predictedPeakSeries, zoneSeries, type Dashboard } from '../lib/dashboard';
import { fmtClock } from '../lib/format';
import { levelOf } from '../lib/density';
import type { Frame, Meta } from '../types/timeline';

interface Props {
  meta: Meta | undefined;
  frames: Frame[];
  /** 모니터 뷰에서 보고 있는 프레임 위치 */
  index: number;
  /** 모니터 뷰의 현재 프레임 기준 요약 (관측 값) */
  dash: Dashboard | null;
}

const MAX_HISTORY_ROWS = 12;
const CELL_ROWS = 10;
const fmt = (v: number | null | undefined, d = 2) => (v === null || v === undefined ? '-' : v.toFixed(d));

/** 구역 분석: 지표 카드, 밀도 추이(관측 + 예측), 프레임 기록 표, 셀 상세 표 */
export function AnalysisView({ meta, frames, index, dash }: Props) {
  const horizon = meta?.prediction.horizon_s ?? 60;
  const series = useMemo(() => (meta ? zoneSeries(meta, frames) : []), [meta, frames]);
  const predPeaks = useMemo(() => predictedPeakSeries(frames, horizon), [frames, horizon]);
  const cur = series[Math.min(index, series.length - 1)];
  const frame = frames[index];

  const cells = useMemo(() => (meta ? hotCellsFor(meta, frame, 'now', null, CELL_ROWS) : []), [meta, frame]);

  if (!meta || frames.length === 0) {
    return <div className="view-scroll"><p className="empty center">분석할 데이터가 없습니다.</p></div>;
  }

  // 시간축: 관측 프레임 + 마지막 프레임 이후 horizon 초(예측만 있는 구간)
  const n = frames.length;
  const lastT = frames[n - 1].t;
  const times = [...frames.map((f) => f.t), ...Array.from({ length: horizon }, (_, k) => lastT + 1 + k)];
  const pad = <T,>(vals: T[]): Array<T | null> => [...vals, ...Array.from({ length: horizon }, () => null)];
  const rows = series
    .map((s, i) => ({ s, i, f: frames[i], pred: predPeaks[i + horizon] }))
    .slice(-MAX_HISTORY_ROWS)
    .reverse();

  return (
    <div className="view-scroll analysis">
      <section className="hero">
        <div>
          <h2>구역 분석 데이터</h2>
          <p className="hero-note">{meta.zone_id} · {meta.camera_id} · 영상 {meta.video_id} · 프레임별 인원·밀도 변화와 {horizon}초 예측</p>
        </div>
      </section>

      <section className="kpi-row" aria-label="지표">
        <KpiCard icon={<UsersIcon />} label="추정 인원" tone="sky" value={cur?.count == null ? '-' : Math.round(cur.count).toLocaleString()} unit="명" sub="선택한 시점 기준" />
        <KpiCard icon={<PulseIcon />} label="평균 밀도" tone="sky" value={fmt(cur?.meanDensity ?? null)} unit="명/m²" sub="면적 가중 평균" />
        <KpiCard
          icon={<AlertIcon />}
          label="최대 밀도"
          tone="grade"
          accent
          chipStyle={cur?.level ? { background: cur.level.soft.bg, color: cur.level.soft.ink } : undefined}
          value={fmt(cur?.maxDensity ?? null)}
          unit="명/m²"
          sub={<GradeBadge level={cur?.level ?? null} />}
        />
        <KpiCard
          icon={<EyeIcon />}
          label="경계 유입 비율"
          tone="teal"
          value={cur?.inflowRatio == null ? '-' : String(Math.round(cur.inflowRatio * 100))}
          unit="%"
          sub={dash ? `${dash.summary.observedCells}/${dash.summary.totalCells}칸 관측` : undefined}
        />
      </section>

      <section className="card" aria-label="밀도 추이">
        <div className="card-title">
          <h3>밀도 추이</h3>
          <small>세로선 = 모니터에서 보고 있는 시점 · 점선 = {horizon}초 뒤 예측(예측 대상 시각에 표시)</small>
        </div>
        <TrendChart
          times={times}
          futureFrom={n}
          current={index}
          series={[
            { label: '최대 밀도', color: CHART_COLORS.max, values: pad(series.map((s) => s.maxDensity ?? 0)) },
            { label: '평균 밀도', color: CHART_COLORS.mean, values: pad(series.map((s) => s.meanDensity ?? 0)) },
            { label: `${horizon}초 뒤 예측 최대`, color: CHART_COLORS.max, values: predPeaks, dashed: true },
          ]}
        />
      </section>

      <div className="home-grid">
        <section className="card" aria-label="프레임 기록">
          <div className="card-title">
            <h3>프레임 기록</h3>
            <small>최근 {Math.min(MAX_HISTORY_ROWS, series.length)}개</small>
          </div>
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr><th>시각</th><th className="num">인원</th><th className="num">평균</th><th className="num">최대</th><th>단계</th><th className="num">{horizon}초 뒤</th></tr>
              </thead>
              <tbody>
                {rows.map(({ s, i, f, pred }) => (
                  <tr key={f.t} className={i === index ? 'current' : undefined}>
                    <td>{fmtClock(f.t)}</td>
                    <td className="num">{s.count == null ? '-' : Math.round(s.count).toLocaleString()}</td>
                    <td className="num">{fmt(s.meanDensity)}</td>
                    <td className="num">{fmt(s.maxDensity)}</td>
                    <td><GradeBadge level={s.level} /></td>
                    <td className="num">{fmt(pred)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        <section className="card" aria-label="셀 상세">
          <div className="card-title">
            <h3>셀 상세 TOP {cells.length || ''}</h3>
            <small>선택한 시점 · 밀도 내림차순</small>
          </div>
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr><th>셀</th><th className="num">밀도</th><th>단계</th><th className="num">속도 m/s</th><th className="num">P</th><th className="num">{horizon}초 뒤</th></tr>
              </thead>
              <tbody>
                {cells.map((c) => {
                  const st = c.state;
                  const speed = st.vx !== null && st.vy !== null ? Math.hypot(st.vx, st.vy) : null;
                  return (
                    <tr key={c.meta.cell_id}>
                      <td>{c.meta.row + 1}행 {c.meta.col + 1}열</td>
                      <td className="num">{fmt(c.value)}</td>
                      <td><GradeBadge level={levelOf(c.value)} /></td>
                      <td className="num">{fmt(speed)}</td>
                      <td className="num">{fmt(st.pressure, 4)}</td>
                      <td className="num">{fmt(st.density_pred_60s)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </section>
      </div>
    </div>
  );
}
