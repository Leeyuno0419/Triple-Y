import { useState, type FormEvent } from 'react';
import { SearchIcon } from './Icons';

export interface SearchNote {
  tone: 'info' | 'warn';
  text: string;
}

interface Props {
  /** Enter 또는 돋보기 클릭 시 호출. 빈 문자열이면 검색 해제 */
  onSubmit: (query: string) => void;
  /** 마지막 검색의 결과 안내 */
  note: SearchNote | null;
}

/** 내비게이션 바의 지역/장소 검색창. 결과 안내는 입력을 다시 수정하기 전까지 아래에 표시된다. */
export function SearchBox({ onSubmit, note }: Props) {
  const [text, setText] = useState('');
  const [dirty, setDirty] = useState(false); // 검색 후 입력을 고치면 이전 안내를 숨긴다

  const submit = (e: FormEvent) => {
    e.preventDefault();
    setDirty(false);
    onSubmit(text);
  };
  const clear = () => {
    setText('');
    setDirty(false);
    onSubmit('');
  };

  return (
    <form className="search" role="search" onSubmit={submit}>
      <button type="submit" className="search-btn" aria-label="검색">
        <SearchIcon size={16} />
      </button>
      <input
        type="search"
        value={text}
        onChange={(e) => {
          setText(e.target.value);
          setDirty(true);
        }}
        placeholder="지역 또는 장소 검색..."
        aria-label="지역 또는 장소 검색"
        autoComplete="off"
        spellCheck={false}
      />
      {text && (
        <button type="button" className="search-clear" aria-label="검색어 지우기" onClick={clear}>
          ✕
        </button>
      )}
      {note && !dirty && (
        <div className={`search-note ${note.tone}`} role="status">
          {note.text}
        </div>
      )}
    </form>
  );
}
