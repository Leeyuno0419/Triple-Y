import { DENSITY_LEVELS } from '../config/density';
import type { AlertItem, AlertKind } from '../lib/alerts';
import { fmtClock } from '../lib/format';
import { gradeLevel } from '../lib/grade';
import type { LiveAlert } from '../types/live';
import { AlertIcon, BellIcon, PulseIcon } from './Icons';

const KIND: Record<AlertKind, { tag: string; cls: string }> = {
  raise: { tag: '상승', cls: 'raise' },
  clear: { tag: '해소', cls: 'clear' },
  forecast: { tag: '예측', cls: 'forecast' },
};

function message(a: AlertItem): string {
  const d = `${a.density.toFixed(2)} 명/m²`;
  if (a.kind === 'forecast') return `${a.horizon_s ?? '?'}초 뒤 ${a.level.label} 단계 예상 · ${d}`;
  if (a.kind === 'clear') return `${a.level.label}(으)로 내려와 위험이 해소됨 · ${d}`;
  return `${a.level.label} 단계로 상승 · ${d}`;
}

/** 서버 알림의 reason → 표시 태그 (docs/api-spec.md 3.3절). 모르는 reason 은 코드를 그대로 보여 준다. */
const REASON: Record<string, { tag: string; cls: string }> = {
  GRADE_UP: { tag: '등급 상승', cls: 'raise' },
  INFLOW: { tag: '유입', cls: 'inflow' },
  INSTABILITY: { tag: '불안정', cls: 'unstable' },
};

/** value 의 뜻은 reason 마다 다르다: GRADE_UP=최대 밀도, INFLOW=유입 비율(5초 평균), INSTABILITY=최대 pressure */
function valueText(a: LiveAlert): string | null {
  if (a.value === null) return null;
  if (a.reason === 'GRADE_UP') return `${a.value.toFixed(2)} 명/m²`;
  if (a.reason === 'INFLOW') return `유입 ${Math.round(a.value * 100)}%`;
  if (a.reason === 'INSTABILITY') return `P ${a.value.toFixed(4)}`;
  return String(a.value);
}

const ACK_LABEL = { idle: '확인', pending: '확인 중…', error: '다시 시도' } as const;

interface Props {
  /** 화면이 프레임 이력에서 파생한 알림. 서버 알림이 없을 때(timeline 파일만 열었을 때)만 쓴다 */
  alerts: AlertItem[];
  /** 서버가 보낸 미확인 알림 (오래된 것부터). 주면(null 이 아니면) 이것만 보여 주고 확인 버튼을 붙인다 */
  liveAlerts?: LiveAlert[] | null;
  /** '확인' 버튼: POST /api/alerts/{alert_id}/ack 를 보내고 성공하면 목록에서 지우는 것은 부모가 한다 */
  onAck?: (alertId: string) => void;
  onSelect?: () => void;
}

/** 최근 알림 피드. 서버에 연결돼 있으면 서버 알림(확인 버튼 포함), 아니면 프레임 이력에서 파생한 알림(lib/alerts.ts)을 보여 준다. */
export function AlertFeed({ alerts, liveAlerts = null, onAck, onSelect }: Props) {
  if (liveAlerts) return <LiveAlertList alerts={liveAlerts} onAck={onAck} onSelect={onSelect} />;

  if (alerts.length === 0) {
    return (
      <div className="alert-empty">
        <BellIcon size={22} />
        <p>최근 위험 알림이 없습니다.</p>
      </div>
    );
  }
  return (
    <ol className="alert-feed">
      {alerts.map((a) => {
        const k = KIND[a.kind];
        return (
          <li key={a.id}>
            <button type="button" className="alert-item" onClick={onSelect}>
              <span className={`alert-ico ${k.cls}`} style={{ background: a.level.soft.bg, color: a.level.soft.ink }}>
                {a.kind === 'forecast' ? <PulseIcon size={16} /> : <AlertIcon size={16} />}
              </span>
              <span className="alert-main">
                <strong>
                  {a.level.label} 단계 <em className={`alert-tag ${k.cls}`}>{k.tag}</em>
                </strong>
                <small>{message(a)}</small>
              </span>
              <time>{fmtClock(a.t)}</time>
            </button>
          </li>
        );
      })}
    </ol>
  );
}

/** 서버 알림 목록: 최신 알림이 위, 알림마다 '확인' 버튼. */
function LiveAlertList({ alerts, onAck, onSelect }: { alerts: LiveAlert[]; onAck?: (alertId: string) => void; onSelect?: () => void }) {
  if (alerts.length === 0) {
    return (
      <div className="alert-empty">
        <BellIcon size={22} />
        <p>확인하지 않은 알림이 없습니다.</p>
      </div>
    );
  }
  return (
    <ol className="alert-feed">
      {[...alerts].reverse().map((a) => {
        const level = gradeLevel(a.level) ?? DENSITY_LEVELS[0];
        const reason = REASON[a.reason] ?? { tag: a.reason || '알림', cls: 'raise' };
        const value = valueText(a);
        return (
          <li key={a.alert_id} className="alert-row">
            <button type="button" className="alert-item" onClick={onSelect} title={a.alert_id}>
              <span className="alert-ico raise" style={{ background: level.soft.bg, color: level.soft.ink }}>
                <AlertIcon size={16} />
              </span>
              <span className="alert-main">
                <strong>
                  {level.label} 단계 <em className={`alert-tag ${reason.cls}`}>{reason.tag}</em>
                </strong>
                <small>
                  {a.message}
                  {value ? ` · ${value}` : ''}
                  {a.ack === 'error' && <span className="alert-error"> · 확인하지 못했습니다</span>}
                </small>
              </span>
              <time>{fmtClock(a.t)}</time>
            </button>
            <button
              type="button"
              className={`alert-ack${a.ack === 'error' ? ' error' : ''}`}
              disabled={a.ack === 'pending'}
              aria-label={`알림 ${a.alert_id} 확인`}
              onClick={() => onAck?.(a.alert_id)}
            >
              {ACK_LABEL[a.ack]}
            </button>
          </li>
        );
      })}
    </ol>
  );
}
