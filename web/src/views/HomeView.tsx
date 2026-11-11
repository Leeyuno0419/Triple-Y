import { AlertFeed } from '../components/AlertFeed';
import { GradeBadge } from '../components/GradeBadge';
import { GradeDistribution } from '../components/GradeDistribution';
import { HotCellList } from '../components/HotCellList';
import { AlertIcon, ArrowRightIcon, BellIcon, EyeIcon, PulseIcon, UsersIcon } from '../components/Icons';
import { KpiCard } from '../components/KpiCard';
import { Sparkline } from '../components/Sparkline';
import type { AlertItem } from '../lib/alerts';
import type { Dashboard } from '../lib/dashboard';
import { fmtClock, type StatusInfo } from '../lib/format';
import type { Frame, Meta } from '../types/timeline';

interface Props {
  meta: Meta | undefined;
  /** 가장 최근 프레임 */
  frame: Frame | undefined;
  /** 가장 최근 프레임의 관측 기준 요약 */
  dash: Dashboard | null;
  /** 가장 최근 프레임의 60초 뒤 예측 기준 요약 */
  dashPred: Dashboard | null;
  alerts: AlertItem[];
  /** 프레임별 최대 밀도 + 미래 예측(있으면 뒤에 붙음) */
  peakValues: number[];
  lastIndex: number;
  /** peakValues 에서 예측만 있는 구간이 시작되는 인덱스 (없으면 -1) */
  futureFrom: number;
  hasData: boolean;
  /** 맨 위 간결한 상태 표시 */
  status: StatusInfo;
  onOpenMonitor: () => void;
  /** 셀을 골라 모니터 뷰로 이동 */
  onOpenCell: (cellId: string) => void;
}

const fmt = (v: number | null, d = 2) => (v === null ? '-' : v.toFixed(d));

/** 시작 화면: 현재 상태 요약 → 고밀도 셀/알림 → 추이/분포, 그리고 모니터 바로가기 */
export function HomeView(p: Props) {
  const { dash, dashPred, frame, meta } = p;
  const s = dash?.summary;
  const sp = dashPred?.summary;
  const peakSoft = s?.level?.soft;

  return (
    <div className="view-scroll home">
      <section className="hero">
        <div>
          <h2>현재 상황</h2>
          <p>
            <span className={`frame-chip ${p.status.kind}`}>{frame ? p.status.text : '데이터 대기 중'}</span>
            <span className="hero-note">
              {frame && meta ? `${meta.zone_id} · ${meta.camera_id} · ${fmtClock(frame.t)} 기준` : '가장 최근 프레임 기준'}
            </span>
          </p>
        </div>
        <button type="button" className="cta" onClick={p.onOpenMonitor}>
          <span>실시간 모니터 보기</span>
          <ArrowRightIcon size={18} />
        </button>
      </section>

      <section className="kpi-row" aria-label="주요 통계">
        <KpiCard
          icon={<AlertIcon />}
          label="현재 최대 밀도"
          tone="grade"
          accent
          chipStyle={peakSoft ? { background: peakSoft.bg, color: peakSoft.ink } : undefined}
          value={fmt(s?.maxDensity ?? null)}
          unit="명/m²"
          sub={
            s?.maxCell ? (
              <>
                <GradeBadge level={s.level} /> <span className="ellipsis">{s.maxCell.row + 1}행 {s.maxCell.col + 1}열</span>
              </>
            ) : (
              '관측 없음'
            )
          }
        />
        <KpiCard
          icon={<UsersIcon />}
          label="추정 인원"
          tone="sky"
          value={s?.count == null ? '-' : Math.round(s.count).toLocaleString()}
          unit="명"
          sub={s ? `값이 있는 셀 ${s.observedCells}/${s.totalCells}칸` : undefined}
        />
        <KpiCard
          icon={<PulseIcon />}
          label={`${meta?.prediction.horizon_s ?? 60}초 뒤 예측`}
          tone="teal"
          value={fmt(sp?.maxDensity ?? null)}
          unit="명/m²"
          sub={sp?.level ? <><GradeBadge level={sp.level} predicted /> <span className="ellipsis">최대 밀도 기준</span></> : '예측 입력 부족 (최근 30초 필요)'}
        />
        <KpiCard
          icon={<EyeIcon />}
          label="경계 유입 비율"
          tone="sage"
          value={s?.inflowRatio == null ? '-' : String(Math.round(s.inflowRatio * 100))}
          unit="%"
          sub="화각 경계에서 안쪽으로 향하는 흐름"
        />
      </section>

      <div className="home-grid">
        <section className="card" aria-label="고밀도 셀">
          <div className="card-title">
            <h3>고밀도 셀 TOP {dash?.hotCells.length || ''}</h3>
            <small>눌러서 모니터에서 보기</small>
          </div>
          <HotCellList cells={dash?.hotCells ?? []} onSelect={p.onOpenCell} />
        </section>

        <section className="card" aria-label="최근 알림">
          <div className="card-title">
            <h3>
              <BellIcon size={14} /> 최근 알림
            </h3>
            <small>단계 변화 기준</small>
          </div>
          <AlertFeed alerts={p.alerts} onSelect={p.onOpenMonitor} />
        </section>
      </div>

      <div className="home-grid even">
        <section className="card" aria-label="최대 밀도 추이">
          <div className="card-title">
            <h3>최대 밀도 추이</h3>
            <small>점선 = 예측</small>
          </div>
          <Sparkline values={p.peakValues} current={p.lastIndex} predictedFrom={p.futureFrom} label="프레임별 최대 밀도" />
        </section>
        <section className="card" aria-label="셀 등급 분포">
          <div className="card-title">
            <h3>셀 등급 분포</h3>
            <small>
              <EyeIcon size={12} /> {s?.totalCells ?? 0}칸 · 경고 이상 {dash?.riskCells ?? 0}칸
            </small>
          </div>
          {s && <GradeDistribution summary={s} />}
        </section>
      </div>

      {!p.hasData && <p className="empty center">데이터를 불러오는 중입니다…</p>}
    </div>
  );
}
