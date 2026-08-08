import { describe, expect, it } from 'vitest';

import { isSlotForZone } from './slotTargeting';

import { SlotStatus } from '@/shared/api/generated/model';

import type { Slot } from '@/shared/api/generated/model';

const slot = (overrides: Partial<Slot> & { shelfZoneId?: number | null }): Slot => {
  const { shelfZoneId = 3, ...rest } = overrides;
  return {
    id: 101,
    slotNumber: 1,
    status: SlotStatus.OCCUPIED,
    isTarget: false,
    lastDetectedAt: null,
    book: {
      id: 1,
      bookId: 1,
      title: '정의란 무엇인가',
      author: '마이클 샌델',
      callNumber: '340.1-샌24ㅈ',
      rfidTagId: 'E200-0001',
      bookshelfId: 4,
      bookshelfNumber: '300',
      shelfZoneId,
      zoneName: '3구역',
    },
    ...rest,
  };
};

describe('isSlotForZone', () => {
  it('책의 구역 id가 같으면 그 구역의 책이다', () => {
    expect(isSlotForZone(slot({ shelfZoneId: 3 }), 3)).toBe(true);
  });

  it('구역 id가 다르면 아니다', () => {
    expect(isSlotForZone(slot({ shelfZoneId: 3 }), 5)).toBe(false);
  });

  it('구역 밖(null)이면 어떤 슬롯도 해당하지 않는다', () => {
    expect(isSlotForZone(slot({ shelfZoneId: 3 }), null)).toBe(false);
  });

  it('책이 없거나 구역이 지정되지 않은 슬롯은 해당하지 않는다', () => {
    expect(isSlotForZone(slot({ book: undefined }), 3)).toBe(false);
    expect(isSlotForZone(slot({ shelfZoneId: null }), 3)).toBe(false);
  });

  it('구역 id가 null인 슬롯과 null 구역을 섞어도 참이 되지 않는다', () => {
    expect(isSlotForZone(slot({ shelfZoneId: null }), null)).toBe(false);
  });

  it('빈 슬롯은 어떤 구역에도 해당하지 않는다', () => {
    expect(isSlotForZone(slot({ status: SlotStatus.EMPTY, book: undefined }), 3)).toBe(false);
  });

  it('서버의 isTarget과 무관하게 구역 id로만 판정한다 — 이동 중 받아온 응답에 흔들리지 않게', () => {
    // 이동 중이라 서버가 isTarget=false로 준 응답이라도, 도착한 구역의 책이면 대상이다
    expect(isSlotForZone(slot({ isTarget: false, shelfZoneId: 3 }), 3)).toBe(true);
  });
});
