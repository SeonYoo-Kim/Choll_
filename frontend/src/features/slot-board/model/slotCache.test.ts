import { describe, expect, it } from 'vitest';

import { replaceSlot } from './slotCache';

import { SlotStatus } from '@/shared/api/generated/model';

import type { Slot } from '@/shared/api/generated/model';

const emptySlot = (slotNumber: number): Slot => ({
  id: slotNumber,
  slotNumber,
  status: SlotStatus.EMPTY,
  isTarget: false,
  lastDetectedAt: null,
});

describe('replaceSlot', () => {
  it('slotNumber가 일치하는 항목만 교체한다', () => {
    const slots = [emptySlot(1), emptySlot(2), emptySlot(3)];
    const updated: Slot = { ...emptySlot(2), status: SlotStatus.OCCUPIED };

    const next = replaceSlot(slots, updated);

    expect(next).not.toBeNull();
    expect(next?.[1]).toBe(updated);
    // 나머지 항목은 참조가 그대로다 — 불필요한 리렌더를 만들지 않는다
    expect(next?.[0]).toBe(slots[0]);
    expect(next?.[2]).toBe(slots[2]);
  });

  it('원본 배열은 변경하지 않는다', () => {
    const slots = [emptySlot(1)];
    const updated: Slot = { ...emptySlot(1), status: SlotStatus.RECOGNITION_FAILED };

    replaceSlot(slots, updated);

    expect(slots[0].status).toBe(SlotStatus.EMPTY);
  });

  it('일치하는 슬롯이 없으면 null을 반환한다', () => {
    const slots = [emptySlot(1), emptySlot(2)];

    expect(replaceSlot(slots, emptySlot(99))).toBeNull();
  });
});
