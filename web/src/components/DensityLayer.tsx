import { useContext, useEffect, useRef } from 'react';
import { CELL_STYLE, SEVERE_BLINK, UNOBSERVED } from '../config/density';
import { cellStyle } from '../lib/density';
import { cellBounds } from '../lib/grid';
import type { Frame, ZoneMeta } from '../types/timeline';
import { MapContext } from './KakaoMap';

export interface CellRef {
  zone_id: string;
  row: number;
  col: number;
}

export const cellKey = (zoneId: string, row: number, col: number) => `${zoneId}:${row}:${col}`;

interface Props {
  zones: ZoneMeta[];
  frame: Frame | undefined;
  onCellSelect?: (cell: CellRef) => void;
  /** 지도에서 숨길 구역 (구역 필터) */
  hiddenZones?: Set<string>;
}

/**
 * 셀 밀도 색상 시각화 레이어.
 * - zones 가 바뀔 때만 Rectangle 을 (재)생성하고,
 * - frame 이 바뀔 때는 색/투명도만 갱신한다 (재생 중 깜빡임/비용 최소화).
 * 셀이 수천 개 이상으로 늘면 Rectangle 대신 Canvas 오버레이로 교체를 검토.
 */
export function DensityLayer({ zones, frame, onCellSelect, hiddenZones }: Props) {
  const map = useContext(MapContext);
  const rects = useRef(new Map<string, kakao.maps.Rectangle>());
  // 깜빡일 셀(key → 기본 투명도)과 현재 위상(true = 어두운 상태)
  const blinkCells = useRef(new Map<string, number>());
  const dimPhase = useRef(false);
  const onSelectRef = useRef(onCellSelect);
  onSelectRef.current = onCellSelect;

  // 1) 셀 사각형 생성
  useEffect(() => {
    if (!map) return;
    const created = new Map<string, kakao.maps.Rectangle>();
    for (const zone of zones) {
      for (let row = 0; row < zone.rows; row++) {
        for (let col = 0; col < zone.cols; col++) {
          const b = cellBounds(zone, row, col);
          const rect = new kakao.maps.Rectangle({
            map,
            bounds: new kakao.maps.LatLngBounds(
              new kakao.maps.LatLng(b.south, b.west),
              new kakao.maps.LatLng(b.north, b.east),
            ),
            strokeWeight: CELL_STYLE.strokeWeight,
            strokeColor: CELL_STYLE.strokeColor,
            strokeOpacity: CELL_STYLE.strokeOpacity,
            fillColor: UNOBSERVED.color,
            fillOpacity: CELL_STYLE.unobservedFillOpacity,
          });
          kakao.maps.event.addListener(rect, 'click', () =>
            onSelectRef.current?.({ zone_id: zone.zone_id, row, col }),
          );
          created.set(cellKey(zone.zone_id, row, col), rect);
        }
      }
    }
    rects.current = created;
    return () => {
      created.forEach((r) => r.setMap(null));
      rects.current = new Map();
    };
  }, [map, zones]);

  // 1-b) 구역 필터: 숨길 구역의 셀은 지도에서 떼어 내 클릭도 막는다
  useEffect(() => {
    if (!map) return;
    rects.current.forEach((rect, key) => {
      const zoneId = key.slice(0, key.indexOf(':'));
      rect.setMap(hiddenZones?.has(zoneId) ? null : map);
    });
  }, [map, zones, hiddenZones]);

  // 2) 프레임별 색 갱신
  useEffect(() => {
    if (!map || !frame) return;
    const predicted = frame.kind === 'predicted';
    const blinking = new Map<string, number>();
    for (const zf of frame.zones) {
      zf.density.forEach((rowVals, row) =>
        rowVals.forEach((value, col) => {
          const rect = rects.current.get(cellKey(zf.zone_id, row, col));
          if (!rect) return;
          const s = cellStyle(value, predicted);
          const key = cellKey(zf.zone_id, row, col);
          if (s.blink) blinking.set(key, s.opacity);
          rect.setOptions({
            fillColor: s.color,
            fillOpacity: s.blink && dimPhase.current ? s.opacity * SEVERE_BLINK.dimFactor : s.opacity,
            strokeColor: s.strokeColor,
            strokeOpacity: s.strokeOpacity,
            strokeWeight: s.strokeWeight,
            strokeStyle: s.strokeStyle,
          });
        }),
      );
    }
    blinkCells.current = blinking;
  }, [map, zones, frame]);

  // 3) 심각 셀 깜빡임: 타이머 하나로 해당 셀의 투명도만 번갈아 바꾼다 (프레임 갱신과 독립)
  useEffect(() => {
    if (!map || !SEVERE_BLINK.enabled) return;
    if (window.matchMedia?.('(prefers-reduced-motion: reduce)').matches) return;
    const id = setInterval(() => {
      dimPhase.current = !dimPhase.current;
      blinkCells.current.forEach((opacity, key) =>
        rects.current.get(key)?.setOptions({
          fillOpacity: dimPhase.current ? opacity * SEVERE_BLINK.dimFactor : opacity,
        }),
      );
    }, SEVERE_BLINK.periodMs / 2);
    return () => {
      clearInterval(id);
      dimPhase.current = false;
    };
  }, [map]);

  return null;
}
