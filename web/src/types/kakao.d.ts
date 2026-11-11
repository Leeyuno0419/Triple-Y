/**
 * 이 프로젝트에서 사용하는 카카오 지도 JS SDK 의 최소 타입 선언.
 * (SDK 는 <script> 로 동적 로드되므로 전역 `kakao` 로 접근한다.)
 * 사용 API 를 늘릴 때만 여기에 추가한다.
 */
declare namespace kakao.maps {
  function load(callback: () => void): void;

  class LatLng {
    constructor(lat: number, lng: number);
    getLat(): number;
    getLng(): number;
  }
  class Point {
    constructor(x: number, y: number);
    x: number;
    y: number;
  }
  /** 화면(컨테이너) 좌표 ↔ 위·경도 변환 */
  interface Projection {
    coordsFromContainerPoint(point: Point): LatLng;
    containerPointFromCoords(latlng: LatLng): Point;
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
    setLevel(level: number): void;
    getProjection(): Projection;
    getNode(): HTMLElement;
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

  interface PolygonOptions {
    map?: Map | null;
    path?: LatLng[];
    strokeWeight?: number;
    strokeColor?: string;
    strokeOpacity?: number;
    strokeStyle?: string;
    fillColor?: string;
    fillOpacity?: number;
    zIndex?: number;
  }
  class Polygon {
    constructor(options: PolygonOptions);
    setMap(map: Map | null): void;
    setPath(path: LatLng[]): void;
  }

  interface CircleOptions {
    map?: Map | null;
    center?: LatLng;
    radius?: number;
    strokeWeight?: number;
    strokeColor?: string;
    strokeOpacity?: number;
    strokeStyle?: string;
    fillColor?: string;
    fillOpacity?: number;
    zIndex?: number;
  }
  class Circle {
    constructor(options: CircleOptions);
    setMap(map: Map | null): void;
    setRadius(radius: number): void;
  }

  interface MarkerOptions {
    map?: Map | null;
    position: LatLng;
    title?: string;
  }
  class Marker {
    constructor(options: MarkerOptions);
    setMap(map: Map | null): void;
  }

  /** 장소 검색 등 (SDK 를 libraries=services 로 로드해야 한다) */
  namespace services {
    interface PlacesSearchResultItem {
      place_name: string;
      address_name: string;
      /** 경도 */
      x: string;
      /** 위도 */
      y: string;
    }
    const Status: { OK: string; ZERO_RESULT: string; ERROR: string };
    interface RegionCodeResult {
      region_type: string;
      address_name: string;
      region_1depth_name: string;
      region_2depth_name: string;
      region_3depth_name: string;
    }
    class Geocoder {
      constructor();
      coord2RegionCode(lng: number, lat: number, callback: (result: RegionCodeResult[], status: string) => void): void;
    }
    class Places {
      constructor();
      keywordSearch(keyword: string, callback: (data: PlacesSearchResultItem[], status: string) => void): void;
    }
  }

  namespace event {
    function addListener(target: object, type: string, handler: (...args: any[]) => void): void;
    function removeListener(target: object, type: string, handler: (...args: any[]) => void): void;
  }
}

interface Window {
  kakao?: typeof kakao;
}
