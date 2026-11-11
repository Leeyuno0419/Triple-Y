/**
 * 셀 밀도 → 색상 매핑 설정. 임계값/색은 여기서만 조정한다 (컴포넌트에 하드코딩 금지).
 * 밀도 단위: 명/m². 기준은 기획서 3.2 위험 등급(정상/주의/경계/심각; 화면 표기는 '경계' 대신 '경고')을 따른다.
 * 심각의 "군중난류 감지" 조건과 깜빡임 표시는 난류 데이터가 timeline 규격에 정해지면 추가한다.
 */
export interface DensityLevel {
  /** 이 값 미만이면 해당 레벨 (마지막은 Infinity) */
  max: number;
  label: string;
  /** 지도 셀 채움 색 (선명) */
  color: string;
  /** 상세 패널용 파스텔 팔레트: 배지 배경 / 배지 글자 / 점·막대 */
  soft: { bg: string; ink: string; dot: string };
}

export const DENSITY_LEVELS: DensityLevel[] = [
  { max: 3, label: '정상', color: '#7fb77e', soft: { bg: '#e4eede', ink: '#46663f', dot: '#a9c8a0' } }, // 초록, 3명 미만
  { max: 4, label: '주의', color: '#f2b38f', soft: { bg: '#fdeadd', ink: '#9a5232', dot: '#f5c3a4' } }, // 소프트 피치, 3명 이상
  { max: 5, label: '경고', color: '#fb7c72', soft: { bg: '#ffe1dc', ink: '#b3392f', dot: '#ffa59c' } }, // 소프트 코랄, 4명 이상
  { max: Infinity, label: '심각', color: '#e0525c', soft: { bg: '#fbd0d4', ink: '#a1212f', dot: '#f08a92' } }, // 뮤트 레드, 5명 이상
];

/** 시계열 차트 선 색: 최대(피크) 밀도 = 코랄, 평균 밀도 = 슬레이트 */
export const CHART_COLORS = { max: '#ff6b6b', mean: '#8294ad' };

/** 기본 지도 모드에서 데이터 구역의 위치를 알려 주는 테두리 (kakao.maps.Polyline 옵션) */
export const ZONE_OUTLINE = {
  strokeColor: '#94a3b8',
  strokeWeight: 2,
  strokeOpacity: 0.9,
  strokeStyle: 'dash',
  zIndex: 5,
};

/** 사용자가 지도에서 직접 지정한 구역의 표시 스타일 (kakao.maps.Polygon 옵션) */
export const CUSTOM_AREA_STYLE = {
  strokeColor: '#5b73c9',
  strokeWeight: 3,
  strokeOpacity: 0.95,
  strokeStyle: 'dash',
  fillColor: '#5b73c9',
  fillOpacity: 0.1,
  previewFillOpacity: 0.16,
};

/** '위험 구역'으로 세는 최소 단계 (DENSITY_LEVELS 인덱스; 2 = 경고 이상) */
export const RISK_MIN_LEVEL_INDEX = 2;

/** 막대 그래프에서 밀도 100% 로 보는 값(명/m²). 가장 높은 임계값 + 1 */
export const DENSITY_BAR_MAX = (DENSITY_LEVELS[DENSITY_LEVELS.length - 2]?.max ?? 5) + 1;

/** 값이 없는 셀 (null: 예측 입력이 모자라 예측이 없거나 측정하지 못한 셀) */
export const UNOBSERVED = {
  label: '값 없음',
  color: '#98a2b3',
  soft: { bg: '#f1f5f9', ink: '#475569', dot: '#cbd5e1' },
};

export const CELL_STYLE = {
  fillOpacity: 0.55,
  unobservedFillOpacity: 0.25,
  strokeWeight: 1,
  strokeColor: '#ffffff',
  strokeOpacity: 0.5,
  /** 밀도가 이 값 이하인 셀은 거의 투명하게 처리해 지도가 가려지지 않게 한다 */
  emptyDensity: 0.02,
  emptyFillOpacity: 0.08,
};

/**
 * 심각 단계 깜빡임 (기획서 3.2: 심각 = 빨강 깜빡임). 난류 조건은 규격 확정 후 추가.
 * - 지도 셀: periodMs 마다 한 번 깜빡(밝음→어두움→밝음), 어두울 때 채움 투명도를 dimFactor 배로.
 * - 예측 프레임은 기본적으로 깜빡이지 않는다(점선 표시로 구분, 경보처럼 보이는 것을 방지).
 * - 사용자가 '동작 줄이기'(prefers-reduced-motion)를 켜면 깜빡이지 않는다.
 */
export const SEVERE_BLINK = {
  enabled: true,
  periodMs: 1200,
  dimFactor: 0.25,
  includePredicted: false,
};

/** 선택한 구역의 지도 테두리 강조 (kakao.maps.Polyline 옵션) */
export const REGION_OUTLINE = {
  strokeColor: '#ff6b6b',
  strokeWeight: 3,
  strokeOpacity: 1,
  strokeStyle: 'solid',
  zIndex: 10,
};

/**
 * 예측 프레임 표시 (기획서 3.2: 예측 지점은 같은 색을 반투명 또는 점선으로 구분).
 * 채움은 관측의 절반 투명도, 테두리는 등급 색의 점선.
 */
export const PREDICTED_STYLE = {
  fillOpacityFactor: 0.5,
  /** kakao.maps.Rectangle strokeStyle 값 */
  strokeStyle: 'dash',
  strokeWeight: 2,
  strokeOpacity: 0.9,
};
