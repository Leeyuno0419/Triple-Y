import { useEffect, useState } from 'react';
import type { Meta } from '../types/timeline';

interface Props {
  meta: Meta;
  /** .stage-container 요소 (이 안의 .stage-video / .stage-svg 를 측정한다) */
  stageRef: { readonly current: HTMLDivElement | null };
  videoSrc?: string;
  /** CellHeatmap 의 영상 상태 */
  status: string;
  /** 보여 주는 프레임의 t */
  t: number;
}

type Box = [number, number, number, number]; // left, top, width, height (화면 px)

interface Measure {
  video: Box | null;
  svg: Box | null;
  natural: [number, number]; // 영상 원본 가로·세로 (아직 모르면 0)
  currentSrc: string;
}

const EMPTY: Measure = { video: null, svg: null, natural: [0, 0], currentSrc: '' };
const r1 = (n: number) => Math.round(n * 10) / 10;
const box = (e: Element | null): Box | null => {
  if (!e) return null;
  const b = e.getBoundingClientRect();
  return [r1(b.left), r1(b.top), r1(b.width), r1(b.height)];
};

/** 영상 파일명(확장자 제외)이 타임라인 meta.video_id 와 같은가 */
const srcMatches = (src: string, videoId: string) =>
  src.replace(/\?.*$/, '').split('/').pop()?.replace(/\.[^.]+$/, '') === videoId;

/**
 * `?debug=grid` 일 때 CellHeatmap 위에 얹는 점검 표시.
 * - 셀 번호(cell_id)를 셀 중앙에, 모서리 점을 좌표(영상 크기를 알면 원본 px, 아니면 0~1)와 함께 그린다.
 * - 좌상단 박스에 영상 원본 크기, 영상 박스와 SVG 박스가 같은지, 영상·타임라인 id 일치 여부를 보여 준다.
 * SVG 는 가로·세로가 다르게 늘어나(preserveAspectRatio="none") 글자가 찌그러지므로 라벨은 HTML 로 얹고 위치만 % 로 맞춘다.
 */
export function DebugGrid({ meta, stageRef, videoSrc, status, t }: Props) {
  const [m, setM] = useState<Measure>(EMPTY);

  useEffect(() => {
    const stage = stageRef.current;
    if (!stage) return;
    const measure = () => {
      const v = stage.querySelector<HTMLVideoElement>('.stage-video');
      setM({
        video: box(v),
        svg: box(stage.querySelector('.stage-svg')),
        natural: [v?.videoWidth ?? 0, v?.videoHeight ?? 0],
        currentSrc: v?.currentSrc ?? '',
      });
    };
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(stage);
    stage.addEventListener('loadedmetadata', measure, true); // 영상 메타데이터 이벤트는 버블링하지 않아 capture 로 받는다
    window.addEventListener('resize', measure);
    return () => {
      ro.disconnect();
      stage.removeEventListener('loadedmetadata', measure, true);
      window.removeEventListener('resize', measure);
    };
  }, [stageRef, videoSrc, status]);

  const [nw, nh] = m.natural;
  const known = nw > 0 && nh > 0;
  const sameBox = !!m.video && !!m.svg && m.video.every((v, i) => Math.abs(v - (m.svg as Box)[i]) < 0.6);
  const idOk = m.currentSrc ? srcMatches(m.currentSrc, meta.video_id) : null;
  const ratio = m.video && m.video[3] > 0 ? m.video[2] / m.video[3] : 0;

  // 모서리: 이웃 셀이 공유하는 점은 한 번만 그린다
  const corners = new Map<string, [number, number]>();
  for (const c of meta.cells) for (const [x, y] of c.image_polygon) corners.set(`${x.toFixed(4)},${y.toFixed(4)}`, [x, y]);

  const fmt = ([x, y]: [number, number]) =>
    known ? `${Math.round(x * nw)},${Math.round(y * nh)}` : `${x.toFixed(3)},${y.toFixed(3)}`;
  const mark = (ok: boolean | null) => (ok === null ? '·' : ok ? '✔' : '✖');

  return (
    <div className="dbg-layer" aria-hidden="true">
      {meta.cells.map((c) => {
        const cx = c.image_polygon.reduce((s, p) => s + p[0], 0) / c.image_polygon.length;
        const cy = c.image_polygon.reduce((s, p) => s + p[1], 0) / c.image_polygon.length;
        return (
          <span key={c.cell_id} className="dbg-cell" style={{ left: `${cx * 100}%`, top: `${cy * 100}%` }}>
            {c.cell_id.slice(2)}
          </span>
        );
      })}
      {[...corners.values()].map(([x, y]) => (
        <span key={`${x}-${y}`} className="dbg-pt" style={{ left: `${x * 100}%`, top: `${y * 100}%` }}>
          <i />
          <b className={y > 0.9 ? 'up' : ''}>{fmt([x, y])}</b>
        </span>
      ))}
      <pre className="dbg-hud">
        {[
          `DEBUG grid  t=${t}s  영상 ${status}`,
          `영상 원본  ${known ? `${nw}×${nh}` : '?'}   화면 ${m.video ? `${m.video[2]}×${m.video[3]}` : '?'} (비율 ${ratio ? ratio.toFixed(4) : '?'})`,
          `${mark(m.video && m.svg ? sameBox : null)} 영상 박스 = SVG 박스   ${m.video ? `[${m.video[0]}, ${m.video[1]}]` : ''}`,
          `${mark(idOk)} 영상 파일 = meta.video_id (${meta.video_id})`,
          `셀 ${meta.cells.length}개 · 모서리 ${corners.size}개 · 좌표 ${known ? 'px(영상 원본)' : '0~1 (영상 크기 미확인)'}`,
          `src ${m.currentSrc || videoSrc || '-'}`,
        ].join('\n')}
      </pre>
    </div>
  );
}
