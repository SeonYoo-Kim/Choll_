/** 도서관 구역 정보 (SLAM 지도 연동 전 데모용 — Figma 목업 기준 8개 구역) */
export const ZONE_NAMES = ['문학', '인문', '아동', '과학', '예술', '역사', '자연', '영어'] as const;

/** 지도 패널 내 각 구역의 좌표 (% 단위) */
export const ZONE_POSITIONS: readonly { x: number; y: number }[] = [
  { x: 13, y: 29 },
  { x: 38, y: 29 },
  { x: 62, y: 29 },
  { x: 87, y: 29 },
  { x: 13, y: 77 },
  { x: 38, y: 77 },
  { x: 62, y: 77 },
  { x: 87, y: 77 },
];

/** 상/하단 구역을 잇는 중앙 통로의 y 좌표 (%) */
export const CORRIDOR_Y = 53;

/** 구역 인덱스(0-base) → 표시명: "3구역" */
export function zoneLabel(zoneIndex: number): string {
  return `${zoneIndex + 1}구역`;
}
