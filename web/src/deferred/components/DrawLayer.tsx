import { useContext, useEffect, useMemo, useRef, useState, type PointerEvent } from 'react';
import { CUSTOM_AREA_STYLE } from '../config/density';
import { circleArea, distanceM, rectArea, type CustomArea, type LatLngPoint } from '../lib/customArea';
import { MapContext } from './KakaoMap';

export type DrawMode = 'off' | 'rect' | 'polygon' | 'circle';

interface Props {
  mode: DrawMode;
  /** 확정된 사용자 구역 (지도에 표시) */
  area: CustomArea | null;
  onComplete: (area: CustomArea) => void;
  onCancel: () => void;
  /** 그리는 중인 구역이 바뀔 때마다 알려 준다 (사이드바 지표를 실시간으로 계산하는 데 쓴다). 없으면 null */
  onPreview?: (area: CustomArea | null) => void;
}

const CLICK_PX = 5; // 이 픽셀 이상 움직이면 클릭이 아니라 드래그로 본다
const MIN_DRAG_PX = 8; // 사각형·원이 이보다 작으면 실수로 보고 무시
const CLOSE_PX = 14; // 다각형: 첫 점 근처를 클릭하면 닫기
const DEFAULT_RADIUS_M = 300;
const MIN_RADIUS_M = 5;
const MAX_RADIUS_M = 50_000;

type Unit = 'm' | 'km';

const toKakao = (p: LatLngPoint) => new kakao.maps.LatLng(p.lat, p.lng);

/** 입력한 반경 문자열을 미터로. 숫자가 아니거나 범위 밖이면 null */
function parseRadius(text: string, unit: Unit): number | null {
  const v = Number(text);
  if (!Number.isFinite(v) || v <= 0) return null;
  const m = unit === 'km' ? v * 1000 : v;
  return m >= MIN_RADIUS_M && m <= MAX_RADIUS_M ? m : null;
}

/** 미터 값을 입력창에 보여 줄 문자열로 (m: 정수, km: 소수 둘째 자리까지) */
function radiusText(m: number, unit: Unit): string {
  return unit === 'm' ? String(Math.round(m)) : String(Number((m / 1000).toFixed(2)));
}

/**
 * 사용자 구역 지정 레이어.
 * - 확정된 구역을 지도에 그린다 (사각형·다각형은 Polygon, 원은 Circle).
 * - mode 가 rect/polygon/circle 이면 지도 위에 투명 오버레이를 덮어 마우스/터치 입력을 직접 받는다
 *   (그동안 지도 이동·확대는 잠시 막힌다). 화면 좌표는 지도 projection 으로 위·경도로 바꾼다.
 *   · 사각형: 드래그 → 놓으면 확정
 *   · 다각형: 클릭으로 꼭짓점 추가 → 더블클릭 / Enter / 첫 점 클릭 / "완료" 로 확정, Backspace 되돌리기
 *   · 원형: 중심점에서 드래그해 반경을 정하면(놓으면 확정), 또는 한 점을 클릭하고 반경(m/km)을 입력한 뒤 완료
 *   · Esc 또는 "취소" 로 중단
 */
export function DrawLayer({ mode, area, onComplete, onCancel, onPreview }: Props) {
  const map = useContext(MapContext);
  const overlay = useRef<HTMLDivElement>(null);
  const gesture = useRef<{ x: number; y: number; start: LatLngPoint; moved: boolean } | null>(null);
  const [points, setPoints] = useState<LatLngPoint[]>([]); // 다각형 확정 꼭짓점
  const [hover, setHover] = useState<LatLngPoint | null>(null);
  const [drag, setDrag] = useState<{ a: LatLngPoint; b: LatLngPoint } | null>(null); // 사각형 미리보기
  // 원형: 중심점, 반경(m)과 입력창 상태
  const [center, setCenter] = useState<LatLngPoint | null>(null);
  const [radiusM, setRadiusM] = useState(DEFAULT_RADIUS_M);
  const [unit, setUnit] = useState<Unit>('m');
  const [radiusInput, setRadiusInput] = useState(String(DEFAULT_RADIUS_M));

  // 모드가 바뀌면 진행 중이던 입력을 비운다
  useEffect(() => {
    setPoints([]);
    setHover(null);
    setDrag(null);
    setCenter(null);
    gesture.current = null;
  }, [mode]);

  // 확정된 구역 표시
  useEffect(() => {
    if (!map || !area) return;
    const style = {
      strokeColor: CUSTOM_AREA_STYLE.strokeColor,
      strokeWeight: CUSTOM_AREA_STYLE.strokeWeight,
      strokeOpacity: CUSTOM_AREA_STYLE.strokeOpacity,
      strokeStyle: CUSTOM_AREA_STYLE.strokeStyle,
      fillColor: CUSTOM_AREA_STYLE.fillColor,
      fillOpacity: CUSTOM_AREA_STYLE.fillOpacity,
      zIndex: 9,
    };
    const shape =
      area.shape === 'circle' && area.center && area.radiusM
        ? new kakao.maps.Circle({ map, center: toKakao(area.center), radius: area.radiusM, ...style })
        : new kakao.maps.Polygon({ map, path: area.path.map(toKakao), ...style });
    return () => shape.setMap(null);
  }, [map, area]);

  // 그리는 중인 구역 (사이드바 지표와 미리보기 도형이 같이 쓴다)
  const previewArea = useMemo<CustomArea | null>(() => {
    if (mode === 'rect' && drag) return rectArea(drag.a, drag.b);
    if (mode === 'polygon' && points.length >= 3) return { shape: 'polygon', path: points };
    if (mode === 'circle' && center) return circleArea(center, radiusM);
    return null;
  }, [mode, drag, points, center, radiusM]);
  useEffect(() => {
    onPreview?.(previewArea);
  }, [previewArea, onPreview]);

  // 미리보기 도형: 사각형·다각형은 선(점 2개부터), 원은 Circle
  const outline = useMemo<LatLngPoint[] | null>(() => {
    if (mode === 'rect' && drag) return rectArea(drag.a, drag.b).path;
    if (mode === 'polygon' && points.length > 0) return hover ? [...points, hover] : points;
    return null;
  }, [mode, drag, points, hover]);
  useEffect(() => {
    if (!map) return;
    const common = {
      map,
      strokeColor: CUSTOM_AREA_STYLE.strokeColor,
      strokeWeight: 2,
      strokeOpacity: 0.9,
      strokeStyle: 'solid',
      fillColor: CUSTOM_AREA_STYLE.fillColor,
      fillOpacity: CUSTOM_AREA_STYLE.previewFillOpacity,
      zIndex: 10,
    };
    if (mode === 'circle' && center) {
      const c = new kakao.maps.Circle({ ...common, center: toKakao(center), radius: radiusM });
      return () => c.setMap(null);
    }
    if (outline && outline.length >= 2) {
      const poly = new kakao.maps.Polygon({ ...common, path: outline.map(toKakao) });
      return () => poly.setMap(null);
    }
  }, [map, mode, center, radiusM, outline]);

  const finishPolygon = () => {
    if (points.length >= 3) onComplete({ shape: 'polygon', path: points });
  };
  const finishCircle = () => {
    if (center && radiusM >= MIN_RADIUS_M) onComplete(circleArea(center, radiusM));
  };

  // 키보드: Esc 취소, Enter 완료, Backspace 되돌리기(다각형)
  useEffect(() => {
    if (mode === 'off') return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onCancel();
      else if (e.key === 'Enter' && mode === 'polygon') finishPolygon();
      else if (e.key === 'Enter' && mode === 'circle') finishCircle();
      else if (e.key === 'Backspace' && mode === 'polygon') setPoints((p) => p.slice(0, -1));
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode, points, center, radiusM, onCancel]);

  if (mode === 'off') return null;

  /** 포인터 이벤트 → 오버레이 기준 픽셀과 위·경도 */
  const locate = (e: PointerEvent) => {
    const el = overlay.current;
    if (!map || !el) return null;
    const r = el.getBoundingClientRect();
    const x = e.clientX - r.left;
    const y = e.clientY - r.top;
    const ll = map.getProjection().coordsFromContainerPoint(new kakao.maps.Point(x, y));
    return { x, y, ll: { lat: ll.getLat(), lng: ll.getLng() } };
  };
  const pixelOf = (p: LatLngPoint) => {
    const pt = map!.getProjection().containerPointFromCoords(toKakao(p));
    return { x: pt.x, y: pt.y };
  };

  const onDown = (e: PointerEvent) => {
    if (e.button !== 0) return;
    const at = locate(e);
    if (!at) return;
    gesture.current = { x: at.x, y: at.y, start: at.ll, moved: false };
    e.currentTarget.setPointerCapture(e.pointerId);
    if (mode === 'rect') setDrag({ a: at.ll, b: at.ll });
    if (mode === 'circle') {
      // 새 중심점. 반경은 입력창에 적힌 값(없으면 기본값)으로 시작하고, 드래그하면 거리로 바뀐다
      setCenter(at.ll);
      setRadiusM(parseRadius(radiusInput, unit) ?? DEFAULT_RADIUS_M);
    }
  };
  const onMove = (e: PointerEvent) => {
    const at = locate(e);
    if (!at) return;
    const g = gesture.current;
    if (g && Math.hypot(at.x - g.x, at.y - g.y) > CLICK_PX) g.moved = true;
    if (mode === 'rect') {
      if (g) setDrag({ a: g.start, b: at.ll });
    } else if (mode === 'circle') {
      if (g?.moved) {
        const m = Math.min(Math.max(distanceM(g.start, at.ll), MIN_RADIUS_M), MAX_RADIUS_M);
        setRadiusM(m);
        setRadiusInput(radiusText(m, unit));
      }
    } else {
      setHover(at.ll);
    }
  };
  const onUp = (e: PointerEvent) => {
    const g = gesture.current;
    gesture.current = null;
    if (!g) return;
    const at = locate(e);
    if (!at) return;

    if (mode === 'rect') {
      setDrag(null);
      if (g.moved && Math.hypot(at.x - g.x, at.y - g.y) >= MIN_DRAG_PX) onComplete(rectArea(g.start, at.ll));
      return;
    }

    if (mode === 'circle') {
      // 드래그로 반경을 정했으면 바로 확정, 클릭만 했으면 중심점만 두고 반경 입력을 기다린다
      if (g.moved && Math.hypot(at.x - g.x, at.y - g.y) >= MIN_DRAG_PX) {
        onComplete(circleArea(g.start, Math.min(Math.max(distanceM(g.start, at.ll), MIN_RADIUS_M), MAX_RADIUS_M)));
      }
      return;
    }

    if (g.moved) return; // 다각형은 드래그가 아니라 클릭으로만 점을 찍는다
    if (points.length >= 3) {
      const first = pixelOf(points[0]);
      if (Math.hypot(first.x - at.x, first.y - at.y) <= CLOSE_PX) {
        finishPolygon();
        return;
      }
    }
    setPoints((prev) => {
      const last = prev[prev.length - 1];
      if (last) {
        const lp = pixelOf(last);
        if (Math.hypot(lp.x - at.x, lp.y - at.y) < 4) return prev; // 더블클릭으로 생긴 중복 점
      }
      return [...prev, at.ll];
    });
  };

  const onRadiusChange = (text: string) => {
    setRadiusInput(text);
    const m = parseRadius(text, unit);
    if (m !== null) setRadiusM(m);
  };
  const onUnitChange = (u: Unit) => {
    setUnit(u);
    const m = parseRadius(radiusInput, u);
    if (m !== null) setRadiusM(m);
  };

  const stop = (e: { stopPropagation: () => void }) => e.stopPropagation();
  const radiusValid = parseRadius(radiusInput, unit) !== null;

  return (
    <div
      ref={overlay}
      className="draw-overlay"
      onPointerDown={onDown}
      onPointerMove={onMove}
      onPointerUp={onUp}
      onDoubleClick={() => mode === 'polygon' && finishPolygon()}
    >
      <div className="draw-hint" role="status" onPointerDown={stop} onPointerUp={stop} onPointerMove={stop} onDoubleClick={stop}>
        {mode === 'rect' && <span>지도를 드래그해 사각형 구역을 지정하세요 · Esc 취소</span>}
        {mode === 'polygon' && (
          <>
            <span>클릭으로 꼭짓점을 추가하세요 ({points.length}개) · 더블클릭 또는 Enter로 완료</span>
            <button type="button" className="draw-btn" onClick={() => setPoints((p) => p.slice(0, -1))} disabled={points.length === 0}>
              되돌리기
            </button>
            <button type="button" className="draw-btn primary" onClick={finishPolygon} disabled={points.length < 3}>
              완료
            </button>
          </>
        )}
        {mode === 'circle' && (
          <>
            <span>
              {center
                ? '반경을 입력하거나 중심점에서 드래그하세요'
                : '중심점을 클릭하거나, 중심점에서 드래그해 반경을 정하세요'}
            </span>
            <label className="draw-radius">
              <span>반경</span>
              <input
                type="number"
                inputMode="decimal"
                min="0"
                step="any"
                value={radiusInput}
                aria-label="반경"
                aria-invalid={!radiusValid}
                onChange={(e) => onRadiusChange(e.target.value)}
              />
              <select value={unit} aria-label="반경 단위" onChange={(e) => onUnitChange(e.target.value as Unit)}>
                <option value="m">m</option>
                <option value="km">km</option>
              </select>
            </label>
            <button type="button" className="draw-btn primary" onClick={finishCircle} disabled={!center || !radiusValid}>
              완료
            </button>
          </>
        )}
        <button type="button" className="draw-btn" onClick={onCancel}>
          취소
        </button>
      </div>
    </div>
  );
}
