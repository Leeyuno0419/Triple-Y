import { useCallback, useEffect, useState } from 'react';
import type { ZoneMeta } from '../types/timeline';
import { EXAMPLE_PLACES, loadFavorites, saveFavorites, zoneFavorite, type Favorite } from './favorites';

const MAX_SEEDED_ZONES = 5;

/**
 * 관심 구역 목록을 상태로 들고 localStorage 에 저장해 새로고침 뒤에도 유지한다.
 * 처음 사용할 때(저장된 값이 없을 때) 데이터에 있는 구역과 예시 장소로 목록을 한 번 채운다.
 */
export function useFavorites(zones: ZoneMeta[]) {
  const [state, setState] = useState(loadFavorites);

  // 구역 데이터가 로드되면 처음 한 번만 기본 목록을 채운다
  useEffect(() => {
    if (state.seeded || zones.length === 0) return;
    const items = [...zones.slice(0, MAX_SEEDED_ZONES).map(zoneFavorite), ...EXAMPLE_PLACES];
    setState({ items, seeded: true });
  }, [zones, state.seeded]);

  useEffect(() => saveFavorites(state), [state]);

  const add = useCallback(
    (f: Favorite) =>
      setState((s) => (s.items.some((i) => i.id === f.id) ? s : { ...s, seeded: true, items: [...s.items, f] })),
    [],
  );
  const remove = useCallback(
    (id: string) => setState((s) => ({ ...s, seeded: true, items: s.items.filter((i) => i.id !== id) })),
    [],
  );

  return { items: state.items, add, remove };
}
