import { useContext, useEffect, useRef } from 'react';
import { DENSITY_BAR_MAX, DENSITY_LEVELS } from '../config/density';
import { cellAt, cellBounds } from '../lib/grid';
import type { Frame, ZoneMeta } from '../types/timeline';
import type { CellRef } from './DensityLayer';
import { MapContext } from './KakaoMap';

interface Props {
  zones: ZoneMeta[];
  frame: Frame | undefined;
  /** 히트맵 모드일 때만 그린다 */
  active: boolean;
  /** 지도에서 숨길 구역 (구역 필터) */
  hiddenZones?: Set<string>;
  /** 히트맵 위를 클릭하면 그 자리의 셀을 선택 */
  onCellSelect?: (cell: CellRef) => void;
}

const MAP_EVENTS = ['bounds_changed', 'center_changed', 'zoom_changed', 'drag', 'idle'];
const MIN_VALUE = 0.05; // 이 밀도 이하는 그리지 않는다

/** 밀도 0 → 6+ 를 위험 단계 색(세이지 → 피치 → 코랄 → 뮤트 레드)으로 잇는 256단계 색표 */
function buildPalette(): Uint8ClampedArray {
  const c = document.createElement('canvas');
  c.width = 256;
  c.height = 1;
  const ctx = c.getContext('2d')!;
  const g = ctx.createLinearGradient(0, 0, 256, 0);
  const at = (d: number) => Math.min(Math.max(d / DENSITY_BAR_MAX, 0), 1);
  g.addColorStop(0, DENSITY_LEVELS[0].color);
  g.addColorStop(at(DENSITY_LEVELS[0].max - 0.5), DENSITY_LEVELS[0].color);
  g.addColorStop(at(DENSITY_LEVELS[0].max), DENSITY_LEVELS[1].color);
  g.addColorStop(at(DENSITY_LEVELS[1].max), DENSITY_LEVELS[2].color);
  g.addColorStop(at(DENSITY_LEVELS[2].max), DENSITY_LEVELS[3].color);
  g.addColorStop(1, '#b3263f');
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, 256, 1);
  return ctx.getImageData(0, 0, 256, 1).data;
}

/**
 * 밀도 히트맵 레이어 (카카오맵에는 히트맵이 없어 캔버스로 직접 그린다).
 * 셀마다 밀도에 비례한 밝기의 방사형 그라데이션을 "겹치면 큰 값" 방식(lighten)으로 칠한 뒤,
 * 밝기를 위험 단계 색표로 바꿔 입힌다. 지도 이동·확대·크기 변경 시 다시 그린다.
 */
export function HeatmapLayer({ zones, frame, active, hiddenZones, onCellSelect }: Props) {
  const map = useContext(MapContext);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const paletteRef = useRef<Uint8ClampedArray | null>(null);
  const onSelectRef = useRef(onCellSelect);
  onSelectRef.current = onCellSelect;

  useEffect(() => {
    if (!map || !active) return;
    const canvas = canvasRef.current;
    if (!canvas) return;
    if (!paletteRef.current) paletteRef.current = buildPalette();
    const palette = paletteRef.current;
    const intensity = document.createElement('canvas'); // 밝기(그레이스케일) 작업용
    let raf = 0;

    const draw = () => {
      raf = 0;
      const w = canvas.clientWidth;
      const h = canvas.clientHeight;
      if (!w || !h) return;
      if (canvas.width !== w || canvas.height !== h) {
        canvas.width = w;
        canvas.height = h;
      }
      intensity.width = w;
      intensity.height = h;
      const out = canvas.getContext('2d')!;
      out.clearRect(0, 0, w, h);
      if (!frame) return;

      const ictx = intensity.getContext('2d', { willReadFrequently: true })!;
      ictx.fillStyle = '#000';
      ictx.fillRect(0, 0, w, h);
      ictx.globalCompositeOperation = 'lighten';

      const proj = map.getProjection();
      for (const zf of frame.zones) {
        if (hiddenZones?.has(zf.zone_id)) continue;
        const zone = zones.find((z) => z.zone_id === zf.zone_id);
        if (!zone) continue;
        zf.density.forEach((rowVals, row) =>
          rowVals.forEach((v, col) => {
            if (v === null || !Number.isFinite(v) || v <= MIN_VALUE) return;
            const b = cellBounds(zone, row, col);
            const p1 = proj.containerPointFromCoords(new kakao.maps.LatLng(b.north, b.west));
            const p2 = proj.containerPointFromCoords(new kakao.maps.LatLng(b.south, b.east));
            const cx = (p1.x + p2.x) / 2;
            const cy = (p1.y + p2.y) / 2;
            const r = Math.max(Math.abs(p2.x - p1.x), Math.abs(p2.y - p1.y)) * 0.85 + 6;
            if (cx < -r || cy < -r || cx > w + r || cy > h + r) return;
            const level = Math.round(Math.min(v / DENSITY_BAR_MAX, 1) * 255);
            const g = ictx.createRadialGradient(cx, cy, 0, cx, cy, r);
            g.addColorStop(0, `rgb(${level},${level},${level})`);
            g.addColorStop(0.4, `rgb(${level},${level},${level})`);
            g.addColorStop(1, 'rgb(0,0,0)');
            ictx.fillStyle = g;
            ictx.fillRect(cx - r, cy - r, r * 2, r * 2);
          }),
        );
      }

      // 밝기 → 색표. 낮은 밝기는 투명하게 두어 지도가 비치게 한다 (예측 프레임은 더 연하게)
      const src = ictx.getImageData(0, 0, w, h);
      const dst = out.createImageData(w, h);
      const factor = frame.kind === 'predicted' ? 0.55 : 0.78;
      for (let i = 0; i < src.data.length; i += 4) {
        const v = src.data[i];
        if (v < 6) continue;
        dst.data[i] = palette[v * 4];
        dst.data[i + 1] = palette[v * 4 + 1];
        dst.data[i + 2] = palette[v * 4 + 2];
        dst.data[i + 3] = Math.min(v / 50, 1) * factor * 255;
      }
      out.putImageData(dst, 0, 0);
    };
    const schedule = () => {
      if (!raf) raf = requestAnimationFrame(draw);
    };

    const onClick = (e: { latLng: kakao.maps.LatLng }) => {
      const hit = cellAt(
        zones.filter((z) => !hiddenZones?.has(z.zone_id)),
        e.latLng.getLat(),
        e.latLng.getLng(),
      );
      if (hit) onSelectRef.current?.(hit);
    };

    MAP_EVENTS.forEach((t) => kakao.maps.event.addListener(map, t, schedule));
    kakao.maps.event.addListener(map, 'click', onClick);
    const ro = typeof ResizeObserver !== 'undefined' ? new ResizeObserver(schedule) : null;
    ro?.observe(canvas);
    schedule();

    return () => {
      MAP_EVENTS.forEach((t) => kakao.maps.event.removeListener(map, t, schedule));
      kakao.maps.event.removeListener(map, 'click', onClick);
      ro?.disconnect();
      if (raf) cancelAnimationFrame(raf);
    };
  }, [map, active, zones, frame, hiddenZones]);

  return active ? <canvas ref={canvasRef} className="heat-canvas" aria-hidden="true" /> : null;
}
