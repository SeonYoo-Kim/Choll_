/**
 * 도서관 구역 정보 (assets/map.png 평면도 기준 7개 구역 Z1~Z7).
 * 구역 이름은 평면도의 인접 서가 KDC 분류를 따른다.
 * (Z1|000·100|Z2|200·300|Z3|400·500|Z4 / Z5|600·700|Z6|800·900|Z7)
 *
 * 여기 있는 좌표·이름은 **MAP-02 응답을 받기 전까지 쓰는 데모 값**이다.
 * 실제 구역은 useShelfZones가 서버에서 받아 zoneStore에 넣으며,
 * 구역을 조회하는 코드는 이 파일이 아니라 zoneStore의 함수를 쓴다.
 */
export const ZONE_NAMES = [
  '총류', // Z1 (하단 좌) — 000 총류
  '철학·종교', // Z2 (하단 중좌) — 100 철학 · 200 종교
  '사회과학·자연과학', // Z3 (하단 중우) — 300 사회과학 · 400 자연과학
  '기술과학', // Z4 (하단 우) — 500 기술과학
  '예술', // Z5 (상단 좌) — 600 예술
  '언어·문학', // Z6 (상단 중) — 700 언어 · 800 문학
  '역사', // Z7 (상단 우) — 900 역사
] as const;

/** 지도 이미지 위 각 구역의 클릭 영역 (% 단위, 이미지 좌상단 기준) */
export interface ZoneRect {
  left: number;
  top: number;
  width: number;
  height: number;
}

// 우상단(left 81.2, top 7.0)은 카트 출발 지점 — 구역이 아니므로 클릭 영역을 두지 않는다
export const ZONE_RECTS: readonly ZoneRect[] = [
  { left: 3.5, top: 52.6, width: 15.0, height: 40.6 }, // Z1 (하단 좌)
  { left: 29.4, top: 52.6, width: 15.0, height: 40.6 }, // Z2 (하단 중좌)
  { left: 55.3, top: 52.6, width: 15.0, height: 40.6 }, // Z3 (하단 중우)
  { left: 81.2, top: 52.6, width: 15.0, height: 40.6 }, // Z4 (하단 우)
  { left: 3.5, top: 7.0, width: 15.0, height: 40.6 }, // Z5 (상단 좌)
  { left: 29.4, top: 7.0, width: 15.0, height: 40.6 }, // Z6 (상단 중)
  { left: 55.3, top: 7.0, width: 15.0, height: 40.6 }, // Z7 (상단 우)
];

/** 지도 패널 내 각 구역의 카트 정차 좌표 (% 단위, 클릭 영역의 중심) */
export const ZONE_POSITIONS: readonly { x: number; y: number }[] = ZONE_RECTS.map((rect) => ({
  x: rect.left + rect.width / 2,
  y: rect.top + rect.height / 2,
}));

/** 상/하단 구역을 잇는 중앙 통로의 y 좌표 (%) */
export const CORRIDOR_Y = 50;

/** 출발 지점(평면도 우상단 노란 영역, 구역 아님)의 카트 대기 좌표 (%) — 이동·추종 전 초기 위치 */
export const START_POSITION: { x: number; y: number } = { x: 88.7, y: 27.3 };

/**
 * 구역별 담당 책장 번호(KDC 백단위) — 평면도 서가 배치 기준.
 * 카트가 해당 구역에 도착하면 이 책장들의 책을 정리할 수 있다.
 * Z1:000 / Z2:100·200 / Z3:300·400 / Z4:500 / Z5:600 / Z6:700·800 / Z7:900
 */
export const ZONE_BOOKSHELVES: readonly (readonly string[])[] = [
  ['000'], // Z1 총류
  ['100', '200'], // Z2 철학·종교
  ['300', '400'], // Z3 사회과학·자연과학
  ['500'], // Z4 기술과학
  ['600'], // Z5 예술
  ['700', '800'], // Z6 언어·문학
  ['900'], // Z7 역사
];

/** 책장 번호(예: "300") → 담당 구역 인덱스(0-base). 목록에 없으면 null */
export function zoneIndexOfBookshelf(bookshelfNumber: string): number | null {
  const index = ZONE_BOOKSHELVES.findIndex((shelves) => shelves.includes(bookshelfNumber));
  return index === -1 ? null : index;
}

/** 구역 인덱스(0-base) → 표시명: "3구역" */
export function zoneLabel(zoneIndex: number): string {
  return `${zoneIndex + 1}구역`;
}
