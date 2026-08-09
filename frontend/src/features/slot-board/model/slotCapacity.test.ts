import { describe, expect, it } from 'vitest';

import { isCartFull, physicalSlots } from './slotCapacity';

import { SlotStatus } from '@/shared/api/generated/model';
import { CART_FULL_THRESHOLD, PHYSICAL_SLOT_COUNT } from '@/shared/config/cart';

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

  it('임계값(4칸)만 차도 만적이다 — 빈 칸이 남아 있어도 미리 알린다', () => {
    const slots = allPhysical(SlotStatus.OCCUPIED);
    slots[2] = slot(3, SlotStatus.EMPTY);
    expect(isCartFull(slots)).toBe(true);
  });

  it('임계값 미만이면 만적이 아니다', () => {
    const slots = allPhysical(SlotStatus.EMPTY);
    for (let i = 0; i < CART_FULL_THRESHOLD - 1; i += 1) {
      slots[i] = slot(i + 1, SlotStatus.OCCUPIED);
    }
    expect(isCartFull(slots)).toBe(false);
  });

  it('인식 중·인식 실패도 자리를 차지한 것으로 센다', () => {
    const slots = allPhysical(SlotStatus.EMPTY);
    slots[0] = slot(1, SlotStatus.RECOGNIZING);
    slots[1] = slot(2, SlotStatus.RECOGNITION_FAILED);
    slots[2] = slot(3, SlotStatus.OCCUPIED);
    slots[3] = slot(4, SlotStatus.OCCUPIED);
    expect(isCartFull(slots)).toBe(true);
  });

  it('리더 없는 슬롯이 비어 있어도 실물 슬롯이 찼으면 만적이다', () => {
    const slots = [...allPhysical(SlotStatus.OCCUPIED), slot(6, SlotStatus.EMPTY)];
    expect(isCartFull(slots)).toBe(true);
  });

  it('리더 없는 슬롯이 차 있어도 임계값에 세지 않는다', () => {
    const slots = allPhysical(SlotStatus.EMPTY);
    slots[0] = slot(1, SlotStatus.OCCUPIED);
    slots[1] = slot(2, SlotStatus.OCCUPIED);
    slots[2] = slot(3, SlotStatus.OCCUPIED);
    expect(isCartFull([...slots, slot(6, SlotStatus.OCCUPIED)])).toBe(false);
  });

  it('부분 응답은 실제로 임계값만큼 찼을 때만 만적이다', () => {
    // 받은 슬롯이 적으면 찬 칸을 실제보다 적게 셀 수만 있다 — 거짓 경고 없음
    expect(isCartFull(allPhysical(SlotStatus.OCCUPIED).slice(0, CART_FULL_THRESHOLD - 1))).toBe(
      false,
    );
    expect(isCartFull(allPhysical(SlotStatus.OCCUPIED).slice(0, CART_FULL_THRESHOLD))).toBe(true);
    expect(isCartFull([])).toBe(false);
  });
});
