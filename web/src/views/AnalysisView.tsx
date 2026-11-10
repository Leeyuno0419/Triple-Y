import { useMemo, useState } from 'react';
import { GradeBadge } from '../components/GradeBadge';
import { CHART_COLORS } from '../config/density';
import { EyeIcon, PulseIcon, UsersIcon, AlertIcon } from '../components/Icons';
import { KpiCard } from '../components/KpiCard';
import { TrendChart } from '../components/TrendChart';
import { zoneSeries, type Dashboard } from '../lib/dashboard';
import type { Frame, ZoneMeta } from '../types/timeline';

interface Props {
  zones: ZoneMeta[];
  frames: Frame[];
  /** 지도 뷰에서 보고 있는 프레임 위치 */
  index: number;
  /** 지도 뷰의 현재 프레임 기준 요약 (구역 비교 표용) */
  dash: Dashboard;
  initialZoneId: string | null;
}

const MAX_HISTORY_ROWS = 12;
const fmt = (v: number | null, d = 2) => (v === null ? '-' : v.toFixed(d));
const hhmmss = (iso: string) => new Date(iso).toLocaleTimeString('ko-KR', { hour12: false });

/** 구역별 분석: 구역 선택 → 지표 카드, 밀도 추이, 프레임 기록 표, 구역 비교 표 */
export function AnalysisView({ zones, frames, index, dash, initialZoneId }: Props) {
  const [pickedId, setPickedId] = useState<string | null>(initialZoneId);
  const zone = zones.find((z) => z.zone_id === pickedId) ?? zones[0];

  const series = useMemo(() => (zone ? zoneSeries(zone, frames) : []), [zone, frames]);
  const predictedFrom = useMemo(() => frames.findIndex((f) => f.kind === 'predicted'), [frames]);
  const cur = series[Math.min(index, series.length - 1)];

  if (!zone) return <div className="view-scroll"><p className="empty center">분석할 구역 데이터가 없습니다.</p></div>;

  const rows = series
    .map((s, i) => ({ s, i, f: frames[i] }))
    .slice(-MAX_HISTORY_ROWS)
    .reverse();

  return (
    <div className="view-scroll analysis">
      <section className="hero">
        <div>
          <h2>구역별 분석 데이터</h2>
          <p className="hero-note">구역을 고르면 프레임별 인원·밀도 변화를 볼 수 있습니다.</p>
        </div>
        <div className="pill-group" role="group" aria-label="분석할 구역">
          {zones.map((z) => (
            <button
              key={z.zone_id}
              type="button"
              className={`pill${z.zone_id === zone.zone_id ? ' active' : ''}`}
              aria-pressed={z.zone_id === zone.zone_id}
              onClick={() => setPickedId(z.zone_id)}
            >
              {z.name}
            </button>
          ))}
        </div>
      </section>

      <section className="kpi-row" aria-label={`${zone.name} 지표`}>
        <KpiCard icon={<UsersIcon />} label="인원" tone="sky" value={cur?.count == null ? '-' : Math.round(cur.count).toLocaleString()} unit="명" sub="선택한 시점 기준" />
        <KpiCard icon={<PulseIcon />} label="평균 밀도" tone="sky" value={fmt(cur?.meanDensity ?? null)} unit="명/m²" sub="관측된 칸의 평균" />
        <KpiCard
          icon={<AlertIcon />}
          label="최대 밀도"
          tone="grade"
          accent
          chipStyle={cur?.level ? { background: cur.level.soft.bg, color: cur.level.soft.ink } : undefined}
          value={fmt(cur?.maxDensity ?? null)}
          unit="명/m²"
          sub={<GradeBadge level={cur?.level ?? null} predicted={frames[index]?.kind === 'predicted'} />}
        />
        <KpiCard
          icon={<EyeIcon />}
          label="관측 범위"
          tone="teal"
          value={cur && cur.totalCells ? String(Math.round((cur.observedCells / cur.totalCells) * 100)) : '-'}
          unit="%"
          sub={cur ? `${cur.observedCells}/${cur.totalCells}칸` : undefined}
        />
      </section>

      <section className="card" aria-label="밀도 추이">
        <div className="card-title">
          <h3>밀도 추이 · {zone.name}</h3>
          <small>세로선 = 지도에서 보고 있는 시점</small>
        </div>
        <TrendChart
          times={frames.map((f) => f.t)}
          predictedFrom={predictedFrom}
          current={index}
          series={[
            { label: '최대 밀도', color: CHART_COLORS.max, values: series.map((s) => s.maxDensity ?? 0) },
            { label: '평균 밀도', color: CHART_COLORS.mean, values: series.map((s) => s.meanDensity ?? 0) },
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
                <tr><th>시각</th><th>구분</th><th className="num">인원</th><th className="num">평균</th><th className="num">최대</th><th>단계</th></tr>
              </thead>
              <tbody>
                {rows.map(({ s, i, f }) => (
                  <tr key={f.t + f.kind + i} className={i === index ? 'current' : undefined}>
                    <td>{hhmmss(f.t)}</td>
                    <td>{f.kind === 'predicted' ? <span className="badge pred">예측 +{f.horizon_s ?? '?'}s</span> : <span className="badge obs">관측</span>}</td>
                    <td className="num">{s.count == null ? '-' : Math.round(s.count).toLocaleString()}</td>
                    <td className="num">{fmt(s.meanDensity)}</td>
                    <td className="num">{fmt(s.maxDensity)}</td>
                    <td><GradeBadge level={s.level} predicted={f.kind === 'predicted'} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        <section className="card" aria-label="구역 비교">
          <div className="card-title">
            <h3>구역 비교</h3>
            <small>선택한 시점 기준</small>
          </div>
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr><th>구역</th><th className="num">인원</th><th className="num">평균</th><th className="num">최대</th><th>단계</th></tr>
              </thead>
              <tbody>
                {dash.zones.map((s) => (
                  <tr key={s.zone.zone_id} className={s.zone.zone_id === zone.zone_id ? 'current' : undefined}>
                    <td>{s.zone.name}</td>
                    <td className="num">{s.count == null ? '-' : Math.round(s.count).toLocaleString()}</td>
                    <td className="num">{fmt(s.meanDensity)}</td>
                    <td className="num">{fmt(s.maxDensity)}</td>
                    <td><GradeBadge level={s.level} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      </div>
    </div>
  );
}
