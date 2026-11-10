/**
 * 이 프로젝트에서 사용하는 카카오 지도 JS SDK 의 최소 타입 선언.
 * (SDK 는 <script> 로 동적 로드되므로 전역 `kakao` 로 접근한다.)
 * 사용 API 를 늘릴 때만 여기에 추가한다.
 */
declare namespace kakao.maps {
  function load(callback: () => void): void;

  class LatLng {
    constructor(lat: number, lng: number);
  }
  class LatLngBounds {
    constructor(sw?: LatLng, ne?: LatLng);
    extend(latlng: LatLng): void;
  }

  interface MapOptions {
    center: LatLng;
    level?: number;
  }
  class Map {
    constructor(container: HTMLElement, options: MapOptions);
    setBounds(bounds: LatLngBounds, paddingTop?: number, paddingRight?: number, paddingBottom?: number, paddingLeft?: number): void;
    setCenter(latlng: LatLng): void;
    getCenter(): LatLng;
    relayout(): void;
  }

  interface RectangleOptions {
    map?: Map | null;
    bounds?: LatLngBounds;
    strokeWeight?: number;
    strokeColor?: string;
    strokeOpacity?: number;
    strokeStyle?: string;
    fillColor?: string;
    fillOpacity?: number;
    zIndex?: number;
  }
  class Rectangle {
    constructor(options: RectangleOptions);
    setMap(map: Map | null): void;
    setOptions(options: RectangleOptions): void;
  }

  interface PolylineOptions {
    map?: Map | null;
    path?: LatLng[];
    strokeWeight?: number;
    strokeColor?: string;
    strokeOpacity?: number;
    strokeStyle?: string;
    zIndex?: number;
  }
  class Polyline {
    constructor(options: PolylineOptions);
    setMap(map: Map | null): void;
  }

  namespace event {
    function addListener(target: object, type: string, handler: (...args: any[]) => void): void;
  }
}

interface Window {
  kakao?: typeof kakao;
}
