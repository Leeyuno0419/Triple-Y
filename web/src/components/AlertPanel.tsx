import type { CSSProperties } from 'react';
import { DENSITY_LEVELS, type DensityLevel } from '../config/density';
import { RESPONSE_GUIDE } from '../config/response';
import type { AlertItem } from '../lib/alerts';
import type { LiveAlert } from '../types/live';
import { AlertFeed } from './AlertFeed';

interface Props {
  alerts: AlertItem[];
  liveAlerts: LiveAlert[] | null;
  onAck: (alertId: string) => void;
  /** 지금 보고 있는 프레임의 구역 단계 (가이드에서 강조) */
  level: DensityLevel | null;
}

/** 모니터 우측 패널: 등급 변화 알림 로그 + 단계별 권장 대응 */
export function AlertPanel({ alerts, liveAlerts, onAck, level }: Props) {
  return (
    <aside className="alert-panel" aria-label="경보와 대응">
      <section className="card alert-log" aria-label="알림 로그">
        <div className="card-title">
          <h3>알림 로그</h3>
          <small>{liveAlerts ? `서버 알림 · 미확인 ${liveAlerts.length}건` : '단계 변화 기준'}</small>
        </div>
        {/* G2 지연 측정(lib/renderLatency.ts)은 AlertFeed 가 알림 행을 그릴 때 남긴다 */}
        <AlertFeed alerts={alerts} liveAlerts={liveAlerts} onAck={onAck} />
      </section>

      <section className="card guide" aria-label="단계별 권장 대응">
        <div className="card-title">
          <h3>단계별 권장 대응</h3>
          <small>기획서 기준</small>
        </div>
        <ol className="guide-list">
          {DENSITY_LEVELS.map((l, i) => (
            <li
              key={l.label}
              className={l === level ? 'current' : undefined}
              aria-current={l === level || undefined}
              style={{ '--b-bg': l.soft.bg, '--b-ink': l.soft.ink, '--b-dot': l.soft.dot } as CSSProperties}
            >
              <p>
                <span className="gbadge">{l.label}</span>
                <b>{RESPONSE_GUIDE[i].action}</b>
                {l === level && <em>현재</em>}
              </p>
              <ul>
                {RESPONSE_GUIDE[i].steps.map((step) => <li key={step}>{step}</li>)}
              </ul>
            </li>
          ))}
        </ol>
      </section>
    </aside>
  );
}
