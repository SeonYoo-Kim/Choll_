import { getCartsMock } from '@/shared/api/generated/carts/carts.msw';
import { getFollowMock } from '@/shared/api/generated/follow/follow.msw';
import type { Slot } from '@/shared/api/generated/model';
import { SlotStatus } from '@/shared/api/generated/model';
import { getListSlotsMockHandler } from '@/shared/api/generated/slots/slots.msw';
import { getTasksMock } from '@/shared/api/generated/tasks/tasks.msw';

/**
 * 개발용 슬롯 고정 픽스처.
 * orval이 faker로 만드는 랜덤 값 대신, 화면 확인이 쉬운 현실적인 데이터를 쓴다.
 */
const slotsFixture: Slot[] = [
  {
    slotNo: 1,
    status: SlotStatus.OCCUPIED,
    book: { bookId: 'BK-0001', title: '어린 왕자', zone: 'A-1' },
  },
  {
    slotNo: 2,
    status: SlotStatus.OCCUPIED,
    book: { bookId: 'BK-0002', title: '데미안', zone: 'A-3' },
  },
  { slotNo: 3, status: SlotStatus.EMPTY },
  { slotNo: 4, status: SlotStatus.RECOGNITION_FAILED },
  {
    slotNo: 5,
    status: SlotStatus.OCCUPIED,
    book: { bookId: 'BK-0005', title: '코스모스', zone: 'B-2' },
  },
  { slotNo: 6, status: SlotStatus.EMPTY },
];

/** 전체 API 모킹 핸들러. 특정 응답을 바꾸고 싶으면 개별 MockHandler에 override를 넘긴다. */
export const handlers = [
  getListSlotsMockHandler(slotsFixture),
  ...getCartsMock(),
  ...getTasksMock(),
  ...getFollowMock(),
];
