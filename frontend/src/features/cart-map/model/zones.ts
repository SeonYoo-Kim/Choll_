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
 * 값은 assets/map.png(1000×600, SLAM 실측 기반 신판 2026-08-07)에서 색 영역의 바운딩 박스를
 * 캔버스 픽셀 스캔으로 측정해 넣었다 (청록=통로, 노랑·주황=테이블, 진회색=서가).
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
  { left: 82.7, top: 21.3, width: 16.2, height: 75.7 }, // Z1 — 우측 통로 (000 총류 서가 앞)
  { left: 45.0, top: 21.3, width: 18.1, height: 75.7 }, // Z2 — 중앙 통로 (100 철학·200 종교 서가 앞)
  { left: 1.0, top: 21.3, width: 24.5, height: 75.7 }, // Z3 — 좌측 통로 (800 문학 서가 앞)
];

/** 지도 패널 내 각 구역의 카트 정차 좌표 (% 단위, 클릭 영역의 중심) */
export const ZONE_POSITIONS: readonly { x: number; y: number }[] = ZONE_RECTS.map((rect) => ({
  x: rect.left + rect.width / 2,
  y: rect.top + rect.height / 2,
}));

/**
 * 통로 세 개를 잇는 상단 통로의 y 좌표 (%).
 * 평면도에서 테이블 아래(17.8%)·통로 위(21.3%) 사이의 빈 바닥이다 — 통로 간 이동은 이 높이를 지나간다.
 */
export const CORRIDOR_Y = 19.5;

/** 카트 대기 지점(상단 통로의 오른쪽, 반납 테이블 왼쪽 빈 바닥)의 좌표 (%) — 이동·추종 전 초기 위치 */
export const START_POSITION: { x: number; y: number } = { x: 80, y: 19.5 };

/**
 * 지도 위 고정 목적지 — 장애물(서가·테이블) 위 클릭을 **정해진 한 지점**으로 바꾸는 버튼.
 *
 * 이동 명령은 두 갈래다: 바닥(구역·통로)을 찍으면 그 좌표 그대로, 장애물을 찍으면 그 앞의
 * 고정 정차점으로. 카트가 들어갈 수 없는 자리를 목적지로 흘리지 않는 책임은 FE에 있다 —
 * BE는 좌표를 그대로 하행하고, 그래도 도달 불가면 Nav2가 거부해 실패 토스트가 뜬다(안전망).
 *
 * `stop`은 통로 안, 그 장애물에 실제로 붙어 작업할 수 있는 자리로 잡는다 (카트 폭 고려 여유 5%≈0.5m).
 */
export interface MapLandmark {
  /** React key·테스트 식별용 (서버로 가지 않는다) */
  key: string;
  name: string;
  /** 지도 이미지 위 클릭 영역 (%) — 평면도에 그려진 장애물 */
  rect: ZoneRect;
  /** 카트 정차 지점 (%) — 통로(구역) 안이어야 한다 */
  stop: { x: number; y: number };
  /**
   * 도착을 어떻게 알릴까.
   * 'zone' — 구역 정리 모달 (서가: 그 자리에서 꽂을 책 목록이 필요하다)
   * 'toast' — 이름 토스트만 (테이블: 꽂을 책이 없어 모달이 소음이다)
   */
  arrival: 'zone' | 'toast';
}

export const MAP_LANDMARKS: readonly MapLandmark[] = [
  {
    key: 'librarianTable',
    name: '사서 테이블',
    rect: { left: 0, top: 0, width: 36.2, height: 17.8 },
    // 테이블 오른쪽 끝 바로 아래 — 흰 바닥(구역 밖)이지만 자유 좌표 이동이라 목적지가 될 수 있다
    stop: { x: 35.0, y: 23.0 },
    arrival: 'toast',
  },
  {
    key: 'returnTable',
    name: '반납 테이블',
    rect: { left: 85.0, top: 0, width: 15.0, height: 17.8 },
    // 테이블 아래쪽 끝 아래 — Z1 통로의 상단
    stop: { x: 92.5, y: 23.0 },
    arrival: 'toast',
  },
  // 서가 4면 — 클릭 영역은 어두운 서가 블록의 해당 면 절반, 정차점은 그 면이 바라보는 통로 안
  // (경계에서 5%≈0.5m 여유). 800·200이 한 블록, 100·000이 한 블록이고 두 면이 맞붙어 있어
  // 블록 가운데에서 나눈다. 왼쪽 면은 왼쪽 통로를, 오른쪽 면은 오른쪽 통로를 본다.
  {
    key: 'shelf800',
    name: '800 문학 서가',
    rect: { left: 26.6, top: 43.8, width: 8.6, height: 21.7 },
    stop: { x: 20.5, y: 54.7 }, // Z3 통로 오른쪽, 서가 앞
    arrival: 'zone',
  },
  {
    key: 'shelf200',
    name: '200 종교 서가',
    rect: { left: 35.3, top: 43.8, width: 8.6, height: 21.7 },
    stop: { x: 50.0, y: 54.7 }, // Z2 통로 왼쪽, 서가 앞
    arrival: 'zone',
  },
  {
    key: 'shelf100',
    name: '100 철학 서가',
    rect: { left: 64.2, top: 43.8, width: 8.6, height: 21.7 },
    stop: { x: 58.1, y: 54.7 }, // Z2 통로 오른쪽, 서가 앞
    arrival: 'zone',
  },
  {
    key: 'shelf000',
    name: '000 총류 서가',
    rect: { left: 72.9, top: 43.8, width: 8.7, height: 21.7 },
    stop: { x: 87.7, y: 54.7 }, // Z1 통로 왼쪽, 서가 앞
    arrival: 'zone',
  },
];

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
