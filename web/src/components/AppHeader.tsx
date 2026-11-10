import { useRef, type KeyboardEvent, type ReactNode } from 'react';
import { ChartIcon, HomeIcon, MapIcon } from './Icons';

export type ViewId = 'home' | 'map' | 'analysis';

const TABS: { id: ViewId; label: string; icon: ReactNode }[] = [
  { id: 'home', label: '메인 대시보드', icon: <HomeIcon size={16} /> },
  { id: 'map', label: '실시간 지도', icon: <MapIcon size={16} /> },
  { id: 'analysis', label: '구역별 분석 데이터', icon: <ChartIcon size={16} /> },
];

interface Props {
  title: string;
  view: ViewId;
  onChange: (view: ViewId) => void;
  /** 오른쪽 상태 배지(mock/실시간) */
  badges?: ReactNode;
}

/** 상단 헤더: 브랜드 + 탭 메뉴(슬라이딩 인디케이터) + 상태 배지 */
export function AppHeader({ title, view, onChange, badges }: Props) {
  const refs = useRef<Record<string, HTMLButtonElement | null>>({});
  const index = TABS.findIndex((t) => t.id === view);

  // 탭 키보드 조작: ← → Home End
  const onKeyDown = (e: KeyboardEvent) => {
    const move = { ArrowRight: 1, ArrowLeft: -1 }[e.key as 'ArrowRight' | 'ArrowLeft'];
    let next = -1;
    if (move) next = (index + move + TABS.length) % TABS.length;
    else if (e.key === 'Home') next = 0;
    else if (e.key === 'End') next = TABS.length - 1;
    if (next < 0) return;
    e.preventDefault();
    onChange(TABS[next].id);
    refs.current[TABS[next].id]?.focus();
  };

  return (
    <header className="app-header">
      <h1 className="brand">
        <span className="brand-mark" aria-hidden="true" />
        {title}
      </h1>

      <div className="tabs" role="tablist" aria-label="화면 전환" onKeyDown={onKeyDown} style={{ '--i': index } as React.CSSProperties}>
        <span className="tab-indicator" aria-hidden="true" />
        {TABS.map((t) => (
          <button
            key={t.id}
            ref={(el) => {
              refs.current[t.id] = el;
            }}
            type="button"
            role="tab"
            id={`tab-${t.id}`}
            aria-selected={view === t.id}
            aria-controls={`view-${t.id}`}
            tabIndex={view === t.id ? 0 : -1}
            className={`tab${view === t.id ? ' active' : ''}`}
            onClick={() => onChange(t.id)}
          >
            {t.icon}
            <span>{t.label}</span>
          </button>
        ))}
      </div>

      <div className="header-badges">{badges}</div>
    </header>
  );
}
