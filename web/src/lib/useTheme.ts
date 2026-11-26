import { useEffect, useState } from 'react';

export type Theme = 'light' | 'dark';

const KEY = 'crowdsight-theme';

/** 저장한 값이 있으면 그것, 없으면 OS 설정. 저장소를 못 쓰는 환경에서도 동작한다. */
function initialTheme(): Theme {
  try {
    const saved = localStorage.getItem(KEY);
    if (saved === 'light' || saved === 'dark') return saved;
  } catch {
    /* 저장소 접근 불가 */
  }
  return typeof window !== 'undefined' && window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}

/** 화면 테마. <html data-theme> 에 반영한다 (색은 styles.css). 버튼으로 고른 값만 저장한다. */
export function useTheme(): [Theme, () => void] {
  const [theme, setTheme] = useState<Theme>(initialTheme);
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
  }, [theme]);
  const toggle = () => {
    const next: Theme = theme === 'dark' ? 'light' : 'dark';
    setTheme(next);
    try {
      localStorage.setItem(KEY, next);
    } catch {
      /* 저장 실패는 무시 */
    }
  };
  return [theme, toggle];
}
