import type { CSSProperties, ReactNode } from 'react';

export type KpiTone = 'coral' | 'sage' | 'sand' | 'gray' | 'grade' | 'sky' | 'teal';

interface Props {
  icon: ReactNode;
  label: string;
  value: string;
  unit?: string;
  sub?: ReactNode;
  tone: KpiTone;
  /** tone="grade" 일 때 단계 파스텔 색을 직접 지정 */
  chipStyle?: CSSProperties;
  /** 핵심 강조 수치: 큰 숫자를 코랄로 */
  accent?: boolean;
}

/** 통계 요약 카드: 아이콘 칩 + 라벨 + 큰 숫자 + 보조 설명 */
export function KpiCard({ icon, label, value, unit, sub, tone, chipStyle, accent }: Props) {
  return (
    <article className={`kpi${accent ? ' accent' : ''}`}>
      <div className="kpi-top">
        <span className={`kpi-chip ${tone}`} style={chipStyle}>{icon}</span>
        <span className="kpi-label">{label}</span>
      </div>
      <div className="kpi-value">
        {value}
        {unit && <small>{unit}</small>}
      </div>
      {sub && <div className="kpi-sub">{sub}</div>}
    </article>
  );
}
