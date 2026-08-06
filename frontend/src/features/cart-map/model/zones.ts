/**
 * 번들 평면도(assets/map.png)의 구역 기하 — **지도 화면 좌표의 기준**.
 *
 * 서버가 SLAM 지도로 만든 그림 대신 FE가 그린 평면도를 띄우므로, "구역이 그림 위 어디인가"도
 * 서버 폴리곤(MAP-02 `boundaryData`)이 아니라 이 파일이 정한다. 두 그림은 같은 방을 그렸어도
 * 여백·비율이 달라, 한쪽 그림에 다른 쪽 폴리곤을 얹으면 클릭 영역이 그림과 따로 논다.
 * 서버에서 받는 것은 구역의 **id뿐**이다(NAV-01에 실어야 하므로) — zoneStore의 applyServerZones 참조.
 *
 * 좌표는 모두 그림 좌상단 기준 %다. %로 두면 그림의 해상도가 바뀌어도, 또 BE 지도 메타
 * (imageWidth·imageHeight)와 그림의 픽셀 크기가 달라도 그대로 쓸 수 있다.
 *
 * 값은 assets/map.png에서 색 영역의 바운딩 박스를 측정해 넣었다.
 * **그림을 교체하면 이 파일의 좌표도 함께 갱신해야 한다.**
 */

/** 구역 코드 — 서버 구역(MAP-02)과 짝을 맞추는 키. 배열 순서가 화면의 구역 순서(1·2·3구역)다 */
export const ZONE_CODES = ['Z1', 'Z2', 'Z3'] as const;

/**
 * 구역 표시명 — 평면도에 그려진 통로별 담당 서가를 요약한 이름.
 * 서버 구역 이름을 쓰지 않는 이유: 이름은 "그림 위 어디"를 설명하는 값이라
 * 좌표와 같은 출처(이 평면도)에서 나와야 한다.
 */
export const ZONE_NAMES = ['총류', '철학·사회과학', '문학·역사'] as const;

/** 지도 이미지 위 각 구역의 클릭 영역 (% 단위, 이미지 좌상단 기준) */
export interface ZoneRect {
  left: number;
  top: number;
  width: number;
  height: number;
}

/**
 * 평면도의 통로 3개 — 카트가 들어가 정차할 수 있는 영역.
 * 통로 사이의 어두운 서가(책장 면)와 사서·반납 테이블은 카트가 지나갈 수 없어 클릭 영역이 아니다.
 */
export const ZONE_RECTS: readonly ZoneRect[] = [
  { left: 70.1, top: 20.4, width: 16.1, height: 73.8 }, // Z1 — 우측 통로 (000 총류 서가 앞)
  { left: 37.0, top: 20.4, width: 17.1, height: 73.8 }, // Z2 — 중앙 통로 (100 철학·200 종교 서가 앞)
  { left: 4.1, top: 20.4, width: 16.9, height: 73.8 }, // Z3 — 좌측 통로 (800 문학 서가 앞)
];

/** 지도 패널 내 각 구역의 카트 정차 좌표 (% 단위, 클릭 영역의 중심) */
export const ZONE_POSITIONS: readonly { x: number; y: number }[] = ZONE_RECTS.map((rect) => ({
  x: rect.left + rect.width / 2,
  y: rect.top + rect.height / 2,
}));

/**
 * 통로 세 개를 잇는 상단 통로의 y 좌표 (%).
 * 평면도에서 사서 테이블 아래·통로 위의 빈 바닥이다 — 통로 간 이동은 이 높이를 지나간다.
 */
export const CORRIDOR_Y = 17;

/** 카트 대기 지점(평면도 우상단 빈 바닥)의 좌표 (%) — 이동·추종 전 초기 위치 */
export const START_POSITION: { x: number; y: number } = { x: 93, y: 16 };

/**
 * 구역별 담당 책장 번호(KDC 백단위) — 평면도의 서가 배치 기준.
 * 카트가 해당 구역에 도착하면 이 책장들의 책을 정리할 수 있다.
 *
 * 평면도에 실제로 그려진 서가 면은 000·100·200·800 네 개이고, 좌→우로 KDC가 내려가는
 * 배치다(Z3 앞 800 / Z2 앞 200·100 / Z1 앞 000). 나머지 분류는 그 순서를 이어 배정했다.
 *
 * ⚠️ **실제 매핑의 정본은 BE의 `bookshelves.zone_id`다.** 이 표는 서버 없이 화면을 돌릴 때
 * (MSW 픽스처) 책과 구역을 일관되게 엮기 위한 값이다.
 */
export const ZONE_BOOKSHELVES: readonly (readonly string[])[] = [
  ['000'], // Z1 총류
  ['100', '200', '300', '400'], // Z2 철학·종교·사회과학·자연과학
  ['500', '600', '700', '800', '900'], // Z3 기술과학·예술·언어·문학·역사
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
