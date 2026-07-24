import { getCartsMock } from '@/shared/api/generated/carts/carts.msw';
import { getFollowMock } from '@/shared/api/generated/follow/follow.msw';
import type { Slot } from '@/shared/api/generated/model';
import { SlotStatus } from '@/shared/api/generated/model';
import { getListSlotsMockHandler } from '@/shared/api/generated/slots/slots.msw';
import { getGetTaskProgressMockHandler } from '@/shared/api/generated/tasks/tasks.msw';

/**
 * 개발용 슬롯 고정 픽스처 (Figma 목업 데이터 기준, 슬롯 30개).
 * orval이 faker로 만드는 랜덤 값 대신, 화면 확인이 쉬운 현실적인 데이터를 쓴다.
 */
const slotsFixture: Slot[] = [
  {
    slotNo: 1,
    status: SlotStatus.OCCUPIED,
    book: { bookId: 'BK-0001', title: '오늘도 책을 읽습니다', author: '김겨울', zone: '3구역' },
  },
  {
    slotNo: 2,
    status: SlotStatus.OCCUPIED,
    book: { bookId: 'BK-0002', title: '마음의 지도', author: '최은영', zone: '3구역' },
  },
  {
    slotNo: 3,
    status: SlotStatus.OCCUPIED,
    book: { bookId: 'BK-0003', title: '어린 왕자', author: '생텍쥐페리', zone: '2구역' },
  },
  ...Array.from({ length: 7 }, (_, i) => ({ slotNo: i + 4, status: SlotStatus.EMPTY })),
  { slotNo: 11, status: SlotStatus.RECOGNITION_FAILED },
  {
    slotNo: 12,
    status: SlotStatus.OCCUPIED,
    book: { bookId: 'BK-0012', title: '불편한 편의점', author: '김호연', zone: '5구역' },
  },
  {
    slotNo: 13,
    status: SlotStatus.OCCUPIED,
    book: { bookId: 'BK-0013', title: '달러구트 꿈 백화점', author: '이미예', zone: '4구역' },
  },
  ...Array.from({ length: 17 }, (_, i) => ({ slotNo: i + 14, status: SlotStatus.EMPTY })),
];

/** 전체 API 모킹 핸들러. 특정 응답을 바꾸고 싶으면 개별 MockHandler에 override를 넘긴다. */
export const handlers = [
  getListSlotsMockHandler(slotsFixture),
  getGetTaskProgressMockHandler({
    totalBooks: 11,
    shelvedBooks: 5,
    remainingBooks: 6,
    currentZoneSlotNos: [1, 2],
  }),
  ...getCartsMock(),
  ...getFollowMock(),
];
