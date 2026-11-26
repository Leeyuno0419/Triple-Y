/**
 * 관리자가 등록한 영상 목록. 서버에 영상 관리 API 가 없어 이 브라우저의 IndexedDB 에만 저장한다
 * (다른 PC·브라우저와 공유되지 않는다).
 *
 * 화면은 영상을 분석하지 않는다. 모니터에 띄우려면 그 영상의 timeline.json(분석 결과)을 함께 등록해야 한다.
 */
import type { Timeline } from '../types/timeline';

export interface VideoEntry {
  id: string;
  name: string;
  createdAt: number;
  /** 로컬 파일로 등록한 영상. 주소로 등록했으면 없다 */
  file?: Blob;
  /** 주소로 등록한 영상 (http(s) 또는 / 로 시작하는 경로) */
  url?: string;
  /** 분석 결과. 없으면 모니터에 띄울 수 없다 */
  timeline?: Timeline;
}

const DB_NAME = 'crowdsight';
const STORE = 'videos';

function openDb(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, 1);
    req.onupgradeneeded = () => req.result.createObjectStore(STORE, { keyPath: 'id' });
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

/** 저장소 작업 하나를 실행하고, 트랜잭션이 끝난 뒤 결과를 돌려준다 (저장 공간 부족은 이때 실패한다). */
async function run<T>(mode: IDBTransactionMode, op: (store: IDBObjectStore) => IDBRequest<T>): Promise<T> {
  const db = await openDb();
  try {
    return await new Promise<T>((resolve, reject) => {
      const tx = db.transaction(STORE, mode);
      const req = op(tx.objectStore(STORE));
      tx.oncomplete = () => resolve(req.result);
      tx.onabort = () => reject(tx.error);
    });
  } finally {
    db.close();
  }
}

export async function listVideos(): Promise<VideoEntry[]> {
  const all = await run<VideoEntry[]>('readonly', (s) => s.getAll());
  return all.sort((a, b) => a.createdAt - b.createdAt);
}

export async function addVideo(input: Omit<VideoEntry, 'id' | 'createdAt'>): Promise<void> {
  const entry: VideoEntry = { ...input, id: `v-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`, createdAt: Date.now() };
  await run('readwrite', (s) => s.add(entry));
}

export async function deleteVideo(id: string): Promise<void> {
  await run('readwrite', (s) => s.delete(id));
}

/** 입력한 영상·타임라인 주소가 쓸 수 있는 형식인가. http(s) 주소 또는 / 로 시작하는 같은 서버의 경로만 받는다. */
export function isUsableUrl(value: string): boolean {
  return /^https?:\/\/\S+$/i.test(value) || /^\/(?!\/)\S*$/.test(value);
}
