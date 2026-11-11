import { useEffect, useRef, useState } from 'react';
import type { Favorite } from '../lib/favorites';
import { isDomestic } from '../lib/geo';
import { ChevronIcon, StarIcon } from './Icons';

interface Props {
  items: Favorite[];
  /** 지금 보고 있는 구역(또는 검색한 장소). 없으면 저장 버튼이 비활성 */
  current: Favorite | null;
  /** 이 관심 구역에 실시간 밀도 데이터가 연결되어 있는가 */
  isLinked: (f: Favorite) => boolean;
  onOpen: (f: Favorite) => void;
  onAddCurrent: () => void;
  onRemove: (id: string) => void;
}

/** 지도 오른쪽 위의 "⭐ 관심 구역" 드롭다운: 저장한 구역으로 바로 이동, 현재 구역 저장/삭제 */
export function FavoritesMenu({ items, current, isLinked, onOpen, onAddCurrent, onRemove }: Props) {
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);

  // 바깥을 누르거나 Esc 를 누르면 닫는다
  useEffect(() => {
    if (!open) return;
    const onDown = (e: PointerEvent) => {
      if (!root.current?.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && setOpen(false);
    document.addEventListener('pointerdown', onDown);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('pointerdown', onDown);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  const saved = current ? items.some((i) => i.id === current.id) : false;

  return (
    <div className="fav" ref={root}>
      <button type="button" className={`fav-btn${open ? ' open' : ''}`} aria-haspopup="menu" aria-expanded={open} onClick={() => setOpen((o) => !o)}>
        <StarIcon size={15} />
        <span>관심 구역</span>
        <ChevronIcon size={14} />
      </button>

      {open && (
        <div className="fav-menu" role="menu" aria-label="관심 구역">
          <div className="fav-head">자주 가는 구역</div>
          {items.length === 0 ? (
            <p className="fav-empty">저장한 관심 구역이 없습니다.</p>
          ) : (
            <ul className="fav-list">
              {items.map((f) => (
                <li key={f.id}>
                  <button
                    type="button"
                    role="menuitem"
                    className="fav-item"
                    onClick={() => {
                      onOpen(f);
                      setOpen(false);
                    }}
                  >
                    <span className="fav-name">{f.name}</span>
                    <span className={`fav-tag${isLinked(f) ? ' linked' : isDomestic(f.lat, f.lng) ? '' : ' sim'}`}>
                      {isLinked(f) ? '실시간 데이터' : isDomestic(f.lat, f.lng) ? '위치만' : '가상 시뮬레이션'}
                    </span>
                  </button>
                  <button type="button" className="fav-del" aria-label={`${f.name} 삭제`} onClick={() => onRemove(f.id)}>
                    ✕
                  </button>
                </li>
              ))}
            </ul>
          )}
          <div className="fav-foot">
            <button type="button" className="fav-save" disabled={!current || saved} onClick={onAddCurrent}>
              {saved ? '✓ 이미 저장됨' : '+ 현재 구역 저장'}
            </button>
            <small>
              {!current ? '구역을 선택하거나 장소를 검색하면 저장할 수 있습니다.' : saved ? current.name : `저장할 곳: ${current.name}`}
            </small>
          </div>
        </div>
      )}
    </div>
  );
}
