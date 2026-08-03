import { HttpResponse, http } from 'msw';

import type { StartNavigationBody } from '@/features/cart-map/api/moveCommands';
import { zoneIndexOfBookshelf } from '@/features/cart-map/model/zones';
import { zoneIdOf } from '@/features/cart-map/model/zoneStore';
import type { SelectFollowTargetBody } from '@/features/follow-target/api/followTarget';
import { getGetCartMockHandler } from '@/shared/api/generated/carts/carts.msw';
import type { Slot, SlotBook } from '@/shared/api/generated/model';
import { SlotStatus } from '@/shared/api/generated/model';
import {
  getGetMapMockHandler,
  getListShelfZonesMockHandler,
} from '@/shared/api/generated/maps/maps.msw';
import { getListSlotsMockHandler } from '@/shared/api/generated/slots/slots.msw';
import { getGetTaskProgressMockHandler } from '@/shared/api/generated/tasks/tasks.msw';
import {
  cartDetailFixture,
  cartWsHandler,
  currentCartZoneId,
  mapInfoFixture,
  pauseCartFollow,
  shelfZonesFixture,
  startCartFollow,
  startCartMove,
  stopCartFollow,
  stopCartMove,
} from '@/shared/api/mocks/cartSimulator';
import { cartVideoWsHandler } from '@/shared/api/mocks/videoSimulator';

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
 * 개발용 슬롯 고정 픽스처 (슬롯 12개, 책 11권 적재).
 * 카트는 출발 지점에서 시작한다 — 300·400 책장 책 9권(슬롯 1·2·4~10)은
 * 3구역에 도착하면 정리 대상이 된다.
 *
 * `isTarget`은 여기에 고정해두지 않는다 — 실제 BE처럼 **응답을 만들 때 카트의 현재 구역과
 * 비교해 계산한다**(`withTargetFlag`). 고정값이면 카트가 어디 있든 항상 대상으로 보인다.
 */
const slotsFixture: Slot[] = [
  {
    ...emptySlot(1),
    status: SlotStatus.OCCUPIED,
    book: book(1, '정의란 무엇인가', '마이클 샌델', '300', '340.1-샌24ㅈ'),
  },
  {
    ...emptySlot(2),
    status: SlotStatus.OCCUPIED,
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
    book: book(4, '넛지', '리처드 탈러', '300', '321.97-탈54ㄴ'),
  },
  {
    ...emptySlot(5),
    status: SlotStatus.OCCUPIED,
    book: book(5, '아픔이 길이 되려면', '김승섭', '300', '331.4-김57ㅇ'),
  },
  {
    ...emptySlot(6),
    status: SlotStatus.OCCUPIED,
    book: book(6, '선량한 차별주의자', '김지혜', '300', '342.1-김78ㅅ'),
  },
  {
    ...emptySlot(7),
    status: SlotStatus.OCCUPIED,
    book: book(7, '팩트풀니스', '한스 로슬링', '300', '331-로58ㅍ'),
  },
  {
    ...emptySlot(8),
    status: SlotStatus.OCCUPIED,
    book: book(8, '이기적 유전자', '리처드 도킨스', '400', '476.01-도67ㅇ'),
  },
  {
    ...emptySlot(9),
    status: SlotStatus.OCCUPIED,
    book: book(9, '시간은 흐르지 않는다', '카를로 로벨리', '400', '420.1-로44ㅅ'),
  },
  {
    ...emptySlot(10),
    status: SlotStatus.OCCUPIED,
    book: book(10, '물고기는 존재하지 않는다', '룰루 밀러', '400', '407.4-밀54ㅁ'),
  },
  { ...emptySlot(11), status: SlotStatus.RECOGNITION_FAILED },
  {
    ...emptySlot(12),
    status: SlotStatus.OCCUPIED,
    book: book(12, '불편한 편의점', '김호연', '800', '813.7-김95ㅂ'),
  },
];

/**
 * 실제 BE와 같은 규칙으로 isTarget을 계산한다 —
 * "이 책이 꽂힐 구역 == 카트가 지금 있는 구역". 카트가 움직이면 값이 따라 바뀐다.
 */
const withTargetFlag = (slots: Slot[]): Slot[] => {
  const zoneId = currentCartZoneId();
  return slots.map((slot) => ({
    ...slot,
    isTarget: zoneId !== null && slot.book?.shelfZoneId === zoneId,
  }));
};

/** 전체 API 모킹 핸들러. 특정 응답을 바꾸고 싶으면 개별 MockHandler에 override를 넘긴다. */
export const handlers = [
  getListSlotsMockHandler(() => withTargetFlag(slotsFixture)),
  // 카트에 11권 적재, 이 중 3구역(300·400 책장) 도착 시 대상은 9권(슬롯 1·2·4~10)
  getGetTaskProgressMockHandler({
    totalSlots: 12,
    totalBooks: 16,
    shelvedBooks: 5,
    remainingBooks: 11,
    currentZoneSlotNumbers: [1, 2, 4, 5, 6, 7, 8, 9, 10],
  }),
  // 카트 이동은 시뮬레이터 연동 — call 접수 시 WS로 위치/도착 이벤트가 브로드캐스트된다
  getGetCartMockHandler(({ params }) => cartDetailFixture(Number(params.cartId))),
  // 이동 명령(NAV-01·NAV-02)은 BE Swagger에 아직 없어 orval 생성물이 없다 — 노션 명세 기준 수동 모킹.
  // BE 구현 후 openapi 재생성 시 생성 MockHandler로 교체할 것.
  http.post('*/api/carts/:cartId/navigation', async ({ request }) => {
    const body = (await request.json()) as StartNavigationBody;
    // 클릭 지점이 오면 그 자리로, 없으면 구역 중심으로 — 실제 BE와 같은 규칙
    const point =
      body.x !== undefined && body.y !== undefined ? { x: body.x, y: body.y } : undefined;
    startCartMove(body.zoneId, point);
    return new HttpResponse(null, { status: 202 });
  }),
  http.delete('*/api/carts/:cartId/navigation', () => {
    stopCartMove();
    return new HttpResponse(null, { status: 202 });
  }),
  // 추종 명령(시작/일시정지/종료)도 BE Swagger에 아직 없다 — followCommands.ts와 짝 맞춘 수동 모킹.
  http.post('*/api/carts/:cartId/follow', () => {
    startCartFollow();
    return new HttpResponse(null, { status: 202 });
  }),
  http.post('*/api/carts/:cartId/follow/pause', () => {
    pauseCartFollow();
    return new HttpResponse(null, { status: 202 });
  }),
  http.delete('*/api/carts/:cartId/follow', () => {
    stopCartFollow();
    return new HttpResponse(null, { status: 202 });
  }),
  // 추종 대상 선택 — 실제 BE는 카트로 명령을 하행하고 202 {trackId, status:"SENT"}를 준다
  http.post('*/api/carts/:cartId/follow/target', async ({ request }) => {
    const body = (await request.json()) as SelectFollowTargetBody;
    return HttpResponse.json({ trackId: body.trackId, status: 'SENT' }, { status: 202 });
  }),
  getGetMapMockHandler(mapInfoFixture),
  getListShelfZonesMockHandler(shelfZonesFixture),
  cartWsHandler,
  cartVideoWsHandler,
];
