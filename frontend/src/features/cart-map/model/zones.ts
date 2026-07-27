/** 도서관 구역 정보 (SLAM 지도 연동 전 데모용 — assets/map.png 평면도 기준 5개 구역) */
export const ZONE_NAMES = ['문학', '인문', '아동', '과학', '예술'] as const;

/** 지도 이미지 위 각 구역의 클릭 영역 (% 단위, 이미지 좌상단 기준) */
export interface ZoneRect {
  left: number;
  top: number;
  width: number;
  height: number;
}

export const ZONE_RECTS: readonly ZoneRect[] = [
  { left: 17.6, top: 5.9, width: 29.3, height: 38.0 }, // 1구역 (상단 좌)
  { left: 49.8, top: 5.9, width: 29.6, height: 38.0 }, // 2구역 (상단 우)
  { left: 14.8, top: 49.3, width: 21.3, height: 37.6 }, // 3구역 (하단 좌)
  { left: 37.8, top: 49.3, width: 21.2, height: 37.6 }, // 4구역 (하단 중)
  { left: 60.2, top: 49.3, width: 24.4, height: 37.6 }, // 5구역 (하단 우)
];

/** 지도 패널 내 각 구역의 카트 정차 좌표 (% 단위, 클릭 영역의 중심) */
export const ZONE_POSITIONS: readonly { x: number; y: number }[] = ZONE_RECTS.map((rect) => ({
  x: rect.left + rect.width / 2,
  y: rect.top + rect.height / 2,
}));

/** 상/하단 구역을 잇는 중앙 통로의 y 좌표 (%) */
export const CORRIDOR_Y = 47;

/** 구역 인덱스(0-base) → 표시명: "3구역" */
export function zoneLabel(zoneIndex: number): string {
  return `${zoneIndex + 1}구역`;
}
