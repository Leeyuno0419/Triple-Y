import type { AlertItem, AlertKind } from '../lib/alerts';
import { AlertIcon, BellIcon, PulseIcon } from './Icons';

const time = (iso: string) => new Date(iso).toLocaleTimeString('ko-KR', { hour12: false });

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

/** 최근 알림 피드. 프레임 이력에서 파생한 알림이다(lib/alerts.ts 주석 참고). */
export function AlertFeed({ alerts, onSelect }: { alerts: AlertItem[]; onSelect: (zoneId: string) => void }) {
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
            <button type="button" className="alert-item" onClick={() => onSelect(a.zoneId)}>
              <span className={`alert-ico ${k.cls}`} style={{ background: a.level.soft.bg, color: a.level.soft.ink }}>
                {a.kind === 'forecast' ? <PulseIcon size={16} /> : <AlertIcon size={16} />}
              </span>
              <span className="alert-main">
                <strong>
                  {a.zoneName} <em className={`alert-tag ${k.cls}`}>{k.tag}</em>
                </strong>
                <small>{message(a)}</small>
              </span>
              <time dateTime={a.t}>{time(a.t)}</time>
            </button>
          </li>
        );
      })}
    </ol>
  );
}
