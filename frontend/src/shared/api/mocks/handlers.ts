import { HttpResponse, http } from 'msw';

import type { StartNavigationBody } from '@/features/cart-map/api/moveCommands';
import { zoneIdOf, zoneIndexOfBookshelf } from '@/features/cart-map/model/zones';
import { getGetCartMockHandler } from '@/shared/api/generated/carts/carts.msw';
import type { Slot, SlotBook } from '@/shared/api/generated/model';
import { SlotStatus } from '@/shared/api/generated/model';
import { getGetMapMockHandler } from '@/shared/api/generated/maps/maps.msw';
import { getListSlotsMockHandler } from '@/shared/api/generated/slots/slots.msw';
import { getGetTaskProgressMockHandler } from '@/shared/api/generated/tasks/tasks.msw';
import {
  cartDetailFixture,
  cartWsHandler,
  mapInfoFixture,
  startCartMove,
  stopCartMove,
} from '@/shared/api/mocks/cartSimulator';

/** 빈 슬롯 픽스처 생성 (slot.id는 slotNumber + 100으로 고정) */
const emptySlot = (slotNumber: number): Slot => ({
  id: slotNumber + 100,
  slotNumber,
  status: SlotStatus.EMPTY,
  isTarget: false,
  lastDetectedAt: null,
});

/**
 * 책 픽스처 — 책장 번호(KDC 백단위)를 주면 담당 구역(zones.ts의 ZONE_BOOKSHELVES 기준)을
 * 자동으로 유도한다. 구역·책장·청구기호가 항상 지도와 일치하도록 유지할 것.
 */
const book = (
  id: number,
  title: string,
  author: string,
  bookshelfNumber: string,
  callNumber: string,
): SlotBook => {
  const zoneIndex = zoneIndexOfBookshelf(bookshelfNumber);
  const shelfZoneId = zoneIndex === null ? null : zoneIdOf(zoneIndex);
  return {
    id,
    bookId: id,
    title,
    author,
    callNumber,
    rfidTagId: `E200-3412-DC03-${String(id).padStart(4, '0')}`,
    bookshelfId: Number(bookshelfNumber) / 100 + 1,
    bookshelfNumber,
    shelfZoneId,
    zoneName: shelfZoneId === null ? null : `${shelfZoneId}구역`,
  };
};

/**
 * 개발용 슬롯 고정 픽스처 (슬롯 30개, 책 15권 적재).
 * 카트는 출발 지점에서 시작한다 — 300·400 책장 책 11권(슬롯 1·2·4~10·15·16)은
 * 3구역 도착 시 정리 대상이 되는 데모 데이터다(isTarget).
 */
const slotsFixture: Slot[] = [
  {
    ...emptySlot(1),
    status: SlotStatus.OCCUPIED,
    isTarget: true,
    book: book(1, '정의란 무엇인가', '마이클 샌델', '300', '340.1-샌24ㅈ'),
  },
  {
    ...emptySlot(2),
    status: SlotStatus.OCCUPIED,
    isTarget: true,
    book: book(2, '코스모스', '칼 세이건', '400', '443.1-세68ㅋ'),
  },
  {
    ...emptySlot(3),
    status: SlotStatus.OCCUPIED,
    book: book(3, '어린 왕자', '생텍쥐페리', '800', '863-생884ㅇ'),
  },
  {
    ...emptySlot(4),
    status: SlotStatus.OCCUPIED,
    isTarget: true,
    book: book(4, '넛지', '리처드 탈러', '300', '321.97-탈54ㄴ'),
  },
  {
    ...emptySlot(5),
    status: SlotStatus.OCCUPIED,
    isTarget: true,
    book: book(5, '아픔이 길이 되려면', '김승섭', '300', '331.4-김57ㅇ'),
  },
  {
    ...emptySlot(6),
    status: SlotStatus.OCCUPIED,
    isTarget: true,
    book: book(6, '선량한 차별주의자', '김지혜', '300', '342.1-김78ㅅ'),
  },
  {
    ...emptySlot(7),
    status: SlotStatus.OCCUPIED,
    isTarget: true,
    book: book(7, '팩트풀니스', '한스 로슬링', '300', '331-로58ㅍ'),
  },
  {
    ...emptySlot(8),
    status: SlotStatus.OCCUPIED,
    isTarget: true,
    book: book(8, '이기적 유전자', '리처드 도킨스', '400', '476.01-도67ㅇ'),
  },
  {
    ...emptySlot(9),
    status: SlotStatus.OCCUPIED,
    isTarget: true,
    book: book(9, '시간은 흐르지 않는다', '카를로 로벨리', '400', '420.1-로44ㅅ'),
  },
  {
    ...emptySlot(10),
    status: SlotStatus.OCCUPIED,
    isTarget: true,
    book: book(10, '물고기는 존재하지 않는다', '룰루 밀러', '400', '407.4-밀54ㅁ'),
  },
  { ...emptySlot(11), status: SlotStatus.RECOGNITION_FAILED },
  {
    ...emptySlot(12),
    status: SlotStatus.OCCUPIED,
    book: book(12, '불편한 편의점', '김호연', '800', '813.7-김95ㅂ'),
  },
  {
    ...emptySlot(13),
    status: SlotStatus.OCCUPIED,
    book: book(13, '사피엔스', '유발 하라리', '900', '909-하293ㅅ'),
  },
  {
    ...emptySlot(14),
    status: SlotStatus.OCCUPIED,
    book: book(14, '오늘도 책을 읽습니다', '김겨울', '000', '029.8-김441ㅇ'),
  },
  {
    ...emptySlot(15),
    status: SlotStatus.OCCUPIED,
    isTarget: true,
    book: book(15, '국가란 무엇인가', '유시민', '300', '340.2-유58ㄱ'),
  },
  {
    ...emptySlot(16),
    status: SlotStatus.OCCUPIED,
    isTarget: true,
    book: book(16, '하리하라의 생물학 카페', '이은희', '400', '470.4-이68ㅎ'),
  },
  ...Array.from({ length: 14 }, (_, i) => emptySlot(i + 17)),
];

/** 전체 API 모킹 핸들러. 특정 응답을 바꾸고 싶으면 개별 MockHandler에 override를 넘긴다. */
export const handlers = [
  getListSlotsMockHandler(slotsFixture),
  // 카트에 15권 적재, 이 중 3구역(300·400 책장) 도착 시 대상은 11권(슬롯 1·2·4~10·15·16)
  getGetTaskProgressMockHandler({
    totalBooks: 20,
    shelvedBooks: 5,
    remainingBooks: 15,
    currentZoneSlotNumbers: [1, 2, 4, 5, 6, 7, 8, 9, 10, 15, 16],
  }),
  // 카트 이동은 시뮬레이터 연동 — call 접수 시 WS로 위치/도착 이벤트가 브로드캐스트된다
  getGetCartMockHandler(({ params }) => cartDetailFixture(Number(params.cartId))),
  // 이동 명령(NAV-01·NAV-02)은 BE Swagger에 아직 없어 orval 생성물이 없다 — 노션 명세 기준 수동 모킹.
  // BE 구현 후 openapi 재생성 시 생성 MockHandler로 교체할 것.
  http.post('*/api/carts/:cartId/navigation', async ({ request }) => {
    const body = (await request.json()) as StartNavigationBody;
    startCartMove(body.zoneId);
    return new HttpResponse(null, { status: 202 });
  }),
  http.delete('*/api/carts/:cartId/navigation', () => {
    stopCartMove();
    return new HttpResponse(null, { status: 202 });
  }),
  getGetMapMockHandler(mapInfoFixture),
  cartWsHandler,
];
