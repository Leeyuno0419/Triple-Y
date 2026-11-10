import {
  CELL_STYLE,
  DENSITY_LEVELS,
  PREDICTED_STYLE,
  SEVERE_BLINK,
  UNOBSERVED,
  type DensityLevel,
} from '../config/density';

export interface CellStyle {
  /** 채움 색 (등급 색) */
  color: string;
  opacity: number;
  label: string;
  strokeColor: string;
  strokeOpacity: number;
  strokeWeight: number;
  /** 'solid' | 'dash' (kakao strokeStyle) */
  strokeStyle: string;
  /** 예측 프레임의 셀인지 (반투명 + 점선) */
  predicted: boolean;
  /** 심각 단계라 깜빡여야 하는 셀인지 */
  blink: boolean;
}

export function levelOf(density: number): DensityLevel {
  return DENSITY_LEVELS.find((l) => density < l.max) ?? DENSITY_LEVELS[DENSITY_LEVELS.length - 1];
}

/** 심각 단계(가장 높은 단계)인가? */
export const isSevereLevel = (level: DensityLevel | null | undefined) =>
  level === DENSITY_LEVELS[DENSITY_LEVELS.length - 1];

/** 이 단계를 지금 깜빡여야 하는가 (설정 + 예측 프레임 여부) */
export const shouldBlink = (level: DensityLevel | null | undefined, predicted: boolean) =>
  SEVERE_BLINK.enabled && isSevereLevel(level) && (!predicted || SEVERE_BLINK.includePredicted);

const baseStroke = {
  strokeColor: CELL_STYLE.strokeColor,
  strokeOpacity: CELL_STYLE.strokeOpacity,
  strokeWeight: CELL_STYLE.strokeWeight,
  strokeStyle: 'solid',
};

/**
 * 셀 밀도(null=화각 밖) → 지도에 칠할 색/투명도/테두리.
 * predicted=true 면 같은 등급 색을 반투명 + 점선 테두리로 그려 측정값과 구분한다.
 */
export function cellStyle(density: number | null, predicted = false): CellStyle {
  if (density === null || !Number.isFinite(density)) {
    return {
      color: UNOBSERVED.color,
      opacity: CELL_STYLE.unobservedFillOpacity,
      label: UNOBSERVED.label,
      ...baseStroke,
      predicted: false,
      blink: false,
    };
  }
  const level = levelOf(density);
  const empty = density <= CELL_STYLE.emptyDensity;
  const opacity = empty ? CELL_STYLE.emptyFillOpacity : CELL_STYLE.fillOpacity;

  // 거의 비어 있는 셀은 점선을 그리지 않는다 (격자 전체가 점선으로 뒤덮이는 것 방지)
  if (!predicted || empty) {
    return { color: level.color, opacity, label: level.label, ...baseStroke, predicted: false, blink: !empty && shouldBlink(level, false) };
  }
  return {
    color: level.color,
    opacity: opacity * PREDICTED_STYLE.fillOpacityFactor,
    label: level.label,
    strokeColor: level.color,
    strokeOpacity: PREDICTED_STYLE.strokeOpacity,
    strokeWeight: PREDICTED_STYLE.strokeWeight,
    strokeStyle: PREDICTED_STYLE.strokeStyle,
    predicted: true,
    blink: shouldBlink(level, true),
  };
}
