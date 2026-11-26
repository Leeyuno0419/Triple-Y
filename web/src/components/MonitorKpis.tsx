import type { Dashboard } from '../lib/dashboard';
import type { LiveAlert } from '../types/live';
import { GradeBadge } from './GradeBadge';
import { AlertIcon, BellIcon, PulseIcon, UsersIcon } from './Icons';
import { KpiCard } from './KpiCard';

interface Props {
  /** 슬라이더가 가리키는 프레임의 관측 요약 */
  now: Dashboard | null;
  /** 같은 프레임의 60초 뒤 예측 요약 */
  pred: Dashboard | null;
  horizonS: number;
  /** 서버 미확인 알림. null 이면 서버에 연결되지 않은 것이다 */
  liveAlerts: LiveAlert[] | null;
  /** 서버 없이 볼 때의 파생 알림 수 */
  derivedCount: number;
}

const fmt = (v: number | null | undefined) => (v === null || v === undefined ? '-' : v.toFixed(2));

/** 모니터 상단 요약 카드: 총 추정 인원, 최고 밀도 셀, 예측 피크, 활성 경보 */
export function MonitorKpis({ now, pred, horizonS, liveAlerts, derivedCount }: Props) {
  const s = now?.summary;
  const p = pred?.summary;
  const soft = s?.level?.soft;
  return (
    <section className="kpi-row monitor-kpis" aria-label="요약">
      <KpiCard
        icon={<UsersIcon />}
        label="총 추정 인원"
        tone="sky"
        value={s?.count == null ? '-' : Math.round(s.count).toLocaleString()}
        unit="명"
        sub={s ? `관측 셀 ${s.observedCells}/${s.totalCells}칸` : '데이터 대기 중'}
      />
      <KpiCard
        icon={<AlertIcon />}
        label="최고 밀도 셀 (Hotspot)"
        tone="grade"
        chipStyle={soft ? { background: soft.bg, color: soft.ink } : undefined}
        value={fmt(s?.maxDensity)}
        unit="명/m²"
        sub={
          s?.maxCell ? (
            <>
              <GradeBadge level={s.level} />
              <span className="ellipsis">{s.maxCell.cell_id} · {s.maxCell.row + 1}행 {s.maxCell.col + 1}열</span>
            </>
          ) : (
            '관측 없음'
          )
        }
      />
      <KpiCard
        icon={<PulseIcon />}
        label={`${horizonS}초 뒤 예상 피크`}
        tone="teal"
        value={fmt(p?.maxDensity)}
        unit="명/m²"
        sub={
          p?.level ? (
            <>
              <GradeBadge level={p.level} predicted />
              <span className="ellipsis">{p.maxCell?.cell_id}</span>
            </>
          ) : (
            '예측 없음'
          )
        }
      />
      <KpiCard
        icon={<BellIcon />}
        label="활성 경보"
        tone="coral"
        accent={!!liveAlerts?.length}
        value={liveAlerts ? String(liveAlerts.length) : '-'}
        unit="건"
        sub={liveAlerts ? '서버 미확인 알림' : `서버 미연결 · 파생 알림 ${derivedCount}건`}
      />
    </section>
  );
}
