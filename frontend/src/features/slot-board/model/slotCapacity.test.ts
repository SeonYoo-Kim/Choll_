import { describe, expect, it } from 'vitest';

import { isCartFull, physicalSlots } from './slotCapacity';

import { SlotStatus } from '@/shared/api/generated/model';
import { PHYSICAL_SLOT_COUNT } from '@/shared/config/cart';

import type { Slot } from '@/shared/api/generated/model';

const slot = (slotNumber: number, status: Slot['status']): Slot => ({
  id: slotNumber + 100,
  slotNumber,
  status,
  isTarget: false,
  lastDetectedAt: null,
});

/** 실물 슬롯 전체를 주어진 상태로 채운 목록 */
const allPhysical = (status: Slot['status']): Slot[] =>
  Array.from({ length: PHYSICAL_SLOT_COUNT }, (_, i) => slot(i + 1, status));

describe('physicalSlots', () => {
  it('리더가 없는 슬롯(6번 이후)은 제외한다', () => {
    const slots = [
      ...allPhysical(SlotStatus.EMPTY),
      slot(6, SlotStatus.OCCUPIED),
      slot(12, SlotStatus.OCCUPIED),
    ];
    expect(physicalSlots(slots).map((s) => s.slotNumber)).toEqual([1, 2, 3, 4, 5]);
  });

  it('응답 순서와 무관하게 슬롯 번호 순으로 준다', () => {
    const slots = [slot(3, SlotStatus.EMPTY), slot(1, SlotStatus.EMPTY), slot(2, SlotStatus.EMPTY)];
    expect(physicalSlots(slots).map((s) => s.slotNumber)).toEqual([1, 2, 3]);
  });
});

describe('isCartFull', () => {
  it('실물 슬롯이 모두 차 있으면 만적이다', () => {
    expect(isCartFull(allPhysical(SlotStatus.OCCUPIED))).toBe(true);
  });

  it('한 칸이라도 비어 있으면 만적이 아니다', () => {
    const slots = allPhysical(SlotStatus.OCCUPIED);
    slots[2] = slot(3, SlotStatus.EMPTY);
    expect(isCartFull(slots)).toBe(false);
  });

  it('인식 중·인식 실패도 자리를 차지한 것으로 센다', () => {
    const slots = allPhysical(SlotStatus.OCCUPIED);
    slots[0] = slot(1, SlotStatus.RECOGNIZING);
    slots[1] = slot(2, SlotStatus.RECOGNITION_FAILED);
    expect(isCartFull(slots)).toBe(true);
  });

  it('리더 없는 슬롯이 비어 있어도 실물 슬롯이 찼으면 만적이다', () => {
    const slots = [...allPhysical(SlotStatus.OCCUPIED), slot(6, SlotStatus.EMPTY)];
    expect(isCartFull(slots)).toBe(true);
  });

  it('리더 없는 슬롯만 차 있으면 만적이 아니다', () => {
    const slots = [...allPhysical(SlotStatus.EMPTY), slot(6, SlotStatus.OCCUPIED)];
    expect(isCartFull(slots)).toBe(false);
  });

  it('실물 슬롯을 다 받지 못했으면 만적으로 보지 않는다', () => {
    // 부분 응답 — 받은 3개가 다 찼다고 만적을 띄우면 거짓 경고가 된다
    expect(isCartFull(allPhysical(SlotStatus.OCCUPIED).slice(0, 3))).toBe(false);
    expect(isCartFull([])).toBe(false);
  });
});
