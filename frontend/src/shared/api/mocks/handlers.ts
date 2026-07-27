import { getCartsMock } from '@/shared/api/generated/carts/carts.msw';
import { getFollowMock } from '@/shared/api/generated/follow/follow.msw';
import type { Book, Slot } from '@/shared/api/generated/model';
import { SlotStatus } from '@/shared/api/generated/model';
import { getListSlotsMockHandler } from '@/shared/api/generated/slots/slots.msw';
import { getGetTaskProgressMockHandler } from '@/shared/api/generated/tasks/tasks.msw';

/** 빈 슬롯 픽스처 생성 (slot.id는 slotNumber + 100으로 고정) */
const emptySlot = (slotNumber: number): Slot => ({
  id: slotNumber + 100,
  slotNumber,
  status: SlotStatus.EMPTY,
  isTarget: false,
});

const book = (
  id: number,
  title: string,
  author: string,
  shelfZoneId: number,
  callNumber: string,
): Book => ({
  id,
  title,
  author,
  callNumber,
  rfidTagId: `E200-3412-DC03-${String(id).padStart(4, '0')}`,
  shelfZoneId,
  zoneName: `${shelfZoneId}구역`,
});

/**
 * 개발용 슬롯 고정 픽스처 (Figma 목업 데이터 기준, 슬롯 30개).
 * orval이 faker로 만드는 랜덤 값 대신, 화면 확인이 쉬운 현실적인 데이터를 쓴다.
 */
const slotsFixture: Slot[] = [
  {
    ...emptySlot(1),
    status: SlotStatus.OCCUPIED,
    isTarget: true,
    book: book(1, '오늘도 책을 읽습니다', '김겨울', 3, '029.8-김441ㅇ'),
  },
  {
    ...emptySlot(2),
    status: SlotStatus.OCCUPIED,
    isTarget: true,
    book: book(2, '마음의 지도', '최은영', 3, '813.7-최67ㅁ'),
  },
  {
    ...emptySlot(3),
    status: SlotStatus.OCCUPIED,
    book: book(3, '어린 왕자', '생텍쥐페리', 2, '863-생884ㅇ'),
  },
  ...Array.from({ length: 7 }, (_, i) => emptySlot(i + 4)),
  { ...emptySlot(11), status: SlotStatus.RECOGNITION_FAILED },
  {
    ...emptySlot(12),
    status: SlotStatus.OCCUPIED,
    book: book(12, '불편한 편의점', '김호연', 5, '813.7-김95ㅂ'),
  },
  {
    ...emptySlot(13),
    status: SlotStatus.OCCUPIED,
    book: book(13, '달러구트 꿈 백화점', '이미예', 4, '813.7-이39ㄷ'),
  },
  ...Array.from({ length: 17 }, (_, i) => emptySlot(i + 14)),
];

/** 전체 API 모킹 핸들러. 특정 응답을 바꾸고 싶으면 개별 MockHandler에 override를 넘긴다. */
export const handlers = [
  getListSlotsMockHandler(slotsFixture),
  getGetTaskProgressMockHandler({
    totalBooks: 11,
    shelvedBooks: 5,
    remainingBooks: 6,
    currentZoneSlotNumbers: [1, 2],
  }),
  ...getCartsMock(),
  ...getFollowMock(),
];
