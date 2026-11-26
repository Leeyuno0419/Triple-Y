import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react';
import { validateTimeline } from '../lib/timeline';
import { addVideo, deleteVideo, isUsableUrl, listVideos, type VideoEntry } from '../lib/videoLibrary';
import type { Timeline } from '../types/timeline';

interface Props {
  onClose: () => void;
  /** 모니터에 띄운 등록 영상의 id. 기본 영상이면 null */
  selectedId: string | null;
  /** 기본(설정 파일) 영상 이름 */
  defaultName: string;
  /** 서버 실시간 수신 중이면 영상을 바꿀 수 없다 */
  live: boolean;
  /** null 이면 기본 영상으로 되돌린다 */
  onSelect: (entry: VideoEntry | null) => void;
}

const message = (e: unknown) => (e instanceof Error ? e.message : String(e));

/** 타임라인 입력(파일 우선, 없으면 주소)을 읽어 검증한다. 둘 다 비면 undefined. */
async function readTimeline(file: File | undefined, url: string): Promise<Timeline | undefined> {
  if (file) return validateTimeline(JSON.parse(await file.text()));
  if (!url) return undefined;
  if (!isUsableUrl(url)) throw new Error('타임라인 주소는 http(s):// 또는 / 로 시작해야 합니다.');
  const res = await fetch(url);
  if (!res.ok) throw new Error(`타임라인을 불러오지 못했습니다 (HTTP ${res.status}).`);
  return validateTimeline(await res.json());
}

/** 영상 관리 모달: 목록 확인 · 추가(파일 또는 주소) · 삭제 · 모니터에 띄우기 */
export function VideoManager({ onClose, selectedId, defaultName, live, onSelect }: Props) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const [videos, setVideos] = useState<VideoEntry[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [confirmId, setConfirmId] = useState<string | null>(null); // 삭제를 한 번 더 확인받는 항목
  const [source, setSource] = useState<'file' | 'url'>('file');

  useEffect(() => {
    const d = dialogRef.current;
    if (d && !d.open) d.showModal();
  }, []);

  const reload = useCallback(
    () => listVideos().then(setVideos).catch((e) => setError(`목록을 읽지 못했습니다: ${message(e)}`)),
    [],
  );
  useEffect(() => {
    reload();
  }, [reload]);

  const onAdd = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const form = e.currentTarget;
    const data = new FormData(form);
    const text = (key: string) => String(data.get(key) ?? '').trim();
    const fileOf = (key: string) => {
      const f = data.get(key);
      return f instanceof File && f.size > 0 ? f : undefined;
    };
    setError(null);
    setBusy(true);
    try {
      const file = source === 'file' ? fileOf('videoFile') : undefined;
      const url = source === 'url' ? text('videoUrl') : '';
      if (source === 'file' && !file) throw new Error('영상 파일을 선택해 주세요.');
      if (source === 'url' && !isUsableUrl(url)) {
        throw new Error('영상 주소는 http(s):// 또는 / 로 시작해야 합니다. PC 의 파일은 "로컬 파일"로 추가해 주세요.');
      }
      const timeline = await readTimeline(fileOf('timelineFile'), text('timelineUrl'));
      const name = text('name') || file?.name || url.split('/').pop() || url;
      await addVideo({ name, file, url: url || undefined, timeline });
      form.reset();
      await reload();
    } catch (err) {
      setError(`추가하지 못했습니다: ${message(err)}`);
    } finally {
      setBusy(false);
    }
  };

  const onDelete = async (id: string) => {
    setError(null);
    try {
      await deleteVideo(id);
      if (id === selectedId) onSelect(null);
      setConfirmId(null);
      await reload();
    } catch (err) {
      setError(`삭제하지 못했습니다: ${message(err)}`);
    }
  };

  const row = (key: string, name: string, info: string, entry: VideoEntry | null) => {
    const current = (entry?.id ?? null) === selectedId && !live;
    const playable = !entry || !!entry.timeline;
    return (
      <li key={key} className={current ? 'current' : undefined}>
        <div className="vm-name">
          <strong title={name}>{name}</strong>
          <small>{info}</small>
        </div>
        <button
          type="button"
          className="pill"
          disabled={current || live || !playable}
          title={live ? '실시간 수신 중에는 바꿀 수 없습니다' : playable ? undefined : '분석 타임라인이 없습니다'}
          onClick={() => {
            onSelect(entry);
            onClose();
          }}
        >
          {current ? '표시 중' : '모니터에 띄우기'}
        </button>
        {entry &&
          (confirmId === entry.id ? (
            <>
              <button type="button" className="pill active" onClick={() => onDelete(entry.id)}>삭제 확인</button>
              <button type="button" className="pill" onClick={() => setConfirmId(null)}>취소</button>
            </>
          ) : (
            <button type="button" className="pill" aria-label={`${name} 삭제`} onClick={() => setConfirmId(entry.id)}>삭제</button>
          ))}
      </li>
    );
  };

  return (
    <dialog ref={dialogRef} className="video-manager" aria-labelledby="vm-title" onClose={onClose}>
      <header>
        <h2 id="vm-title">영상 관리</h2>
        <button type="button" className="rp-close" aria-label="닫기" onClick={onClose}>✕</button>
      </header>

      <p className="vm-note">
        등록한 영상은 이 브라우저에만 저장됩니다. 화면은 영상을 분석하지 않으므로, 모니터에 띄우려면 분석 타임라인(JSON)을 함께 등록하세요.
        {live && ' 지금은 서버 실시간 수신 중이라 영상을 바꿀 수 없습니다.'}
      </p>
      {error && <p className="map-error vm-error" role="alert">{error}</p>}

      <ul className="vm-list" aria-label="등록된 영상">
        {row('default', defaultName, '기본 영상 · 설정 파일 (삭제 불가)', null)}
        {videos?.map((v) =>
          row(v.id, v.name, `${v.file ? '로컬 파일' : v.url} · ${v.timeline ? `타임라인 ${v.timeline.frames.length}초` : '분석 데이터 없음'}`, v),
        )}
      </ul>

      <form className="vm-form" onSubmit={onAdd}>
        <h3>새 영상 추가</h3>
        <label>
          이름 <input type="text" name="name" placeholder="비우면 파일 이름" maxLength={60} />
        </label>
        <div className="pill-group" role="group" aria-label="영상 가져오는 방법">
          <button type="button" className={`pill${source === 'file' ? ' active' : ''}`} aria-pressed={source === 'file'} onClick={() => setSource('file')}>로컬 파일</button>
          <button type="button" className={`pill${source === 'url' ? ' active' : ''}`} aria-pressed={source === 'url'} onClick={() => setSource('url')}>경로 / URL</button>
        </div>
        {source === 'file' ? (
          <label>
            영상 파일 <input type="file" name="videoFile" accept="video/mp4,video/webm" />
          </label>
        ) : (
          <label>
            영상 주소 <input type="text" name="videoUrl" placeholder="/videos/E04_039.mp4 또는 https://..." />
          </label>
        )}
        <label>
          타임라인 파일 <input type="file" name="timelineFile" accept=".json,application/json" />
        </label>
        <label>
          또는 타임라인 주소 <input type="text" name="timelineUrl" placeholder="/data/E04_039.pred.json" />
        </label>
        <button type="submit" className="cta" disabled={busy}>{busy ? '추가 중…' : '추가'}</button>
      </form>
    </dialog>
  );
}
