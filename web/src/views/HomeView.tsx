import { AlertFeed } from '../components/AlertFeed';
import { GradeDistribution } from '../components/GradeDistribution';
import { GradeBadge } from '../components/GradeBadge';
import { AlertIcon, ArrowRightIcon, BellIcon, EyeIcon, LayersIcon, PulseIcon, UsersIcon } from '../components/Icons';
import { KpiCard } from '../components/KpiCard';
import { Sparkline } from '../components/Sparkline';
import { ZoneRankList } from '../components/ZoneRankList';
import type { AlertItem } from '../lib/alerts';
import type { Dashboard } from '../lib/dashboard';
import { frameLabel } from '../lib/format';
import type { Frame } from '../types/timeline';

interface Props {
  /** 가장 최근 관측 프레임 */
  frame: Frame | undefined;
  dash: Dashboard;
  alerts: AlertItem[];
  peakValues: number[];
  lastObservedIndex: number;
  predictedFrom: number;
  hasData: boolean;
  onOpenMap: () => void;
  /** 구역을 골라 지도 뷰로 이동 */
  onOpenZone: (zoneId: string) => void;
}

/** 시작 화면: 전체 현황 요약 → 순위/알림 → 추이/분포, 그리고 지도 바로가기 */
export function HomeView(p: Props) {
  const { dash, frame } = p;
  const total = dash.zones.length;
  const peakSoft = dash.peak?.level.soft;

  return (
    <div className="view-scroll home">
      <section className="hero">
        <div>
          <h2>전체 현황</h2>
          <p>
            <span className="frame-chip">{frameLabel(frame) || '데이터 대기 중'}</span>
            <span className="hero-note">가장 최근 관측 기준</span>
          </p>
        </div>
        <button type="button" className="cta" onClick={p.onOpenMap}>
          <span>실시간 인파 지도 보기</span>
          <ArrowRightIcon size={18} />
        </button>
      </section>

      <section className="kpi-row" aria-label="주요 통계">
        <KpiCard
          icon={<LayersIcon />}
          label="총 감지 구역"
          tone="teal"
          value={String(total)}
          unit="구역"
          sub={`관측 중 ${total - dash.unobservedZones}곳`}
        />
        <KpiCard
          icon={<AlertIcon />}
          label="위험·경고 구역"
          tone={dash.riskZones > 0 ? 'coral' : 'sage'}
          accent={dash.riskZones > 0}
          value={String(dash.riskZones)}
          unit={`/ ${total}구역`}
          sub={dash.severeZones > 0 ? `심각 ${dash.severeZones}곳 포함` : '경고 이상 구역'}
        />
        <KpiCard
          icon={<PulseIcon />}
          label="최고 밀도 지역"
          tone="grade"
          accent
          chipStyle={peakSoft ? { background: peakSoft.bg, color: peakSoft.ink } : undefined}
          value={dash.peak ? dash.peak.density.toFixed(2) : '-'}
          unit="명/m²"
          sub={
            dash.peak ? (
              <>
                <GradeBadge level={dash.peak.level} /> <span className="ellipsis">{dash.peak.zone.name}</span>
              </>
            ) : (
              '관측 없음'
            )
          }
        />
        <KpiCard
          icon={<UsersIcon />}
          label="총 인원"
          tone="sky"
          value={dash.totalCount === null ? '-' : Math.round(dash.totalCount).toLocaleString()}
          unit="명"
          sub={`관측 범위 ${dash.totalCells ? Math.round((dash.observedCells / dash.totalCells) * 100) : 0}%`}
        />
      </section>

      <div className="home-grid">
        <section className="card" aria-label="구역별 위험도 순위">
          <div className="card-title">
            <h3>구역별 위험도 순위</h3>
            <small>최대 밀도 기준 · 눌러서 지도로 이동</small>
          </div>
          <ZoneRankList zones={dash.zones} onSelect={p.onOpenZone} />
        </section>

        <section className="card" aria-label="최근 알림">
          <div className="card-title">
            <h3>
              <BellIcon size={14} /> 최근 알림
            </h3>
            <small>단계 변화 기준</small>
          </div>
          <AlertFeed alerts={p.alerts} onSelect={p.onOpenZone} />
        </section>
      </div>

      <div className="home-grid even">
        <section className="card" aria-label="최고 밀도 추이">
          <div className="card-title">
            <h3>최고 밀도 추이</h3>
            <small>점선 = 예측</small>
          </div>
          <Sparkline values={p.peakValues} current={p.lastObservedIndex} predictedFrom={p.predictedFrom} label="프레임별 최고 밀도" />
        </section>
        <section className="card" aria-label="구역 등급 분포">
          <div className="card-title">
            <h3>구역 등급 분포</h3>
            <small>
              <EyeIcon size={12} /> {total}구역
            </small>
          </div>
          <GradeDistribution dash={dash} />
        </section>
      </div>

      {!p.hasData && <p className="empty center">데이터를 불러오는 중입니다…</p>}
    </div>
  );
}
