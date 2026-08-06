import { SlotStatus } from '@/shared/api/generated/model';
import { PHYSICAL_SLOT_COUNT } from '@/shared/config/cart';

import type { Slot } from '@/shared/api/generated/model';

/**
 * 실물 카트에 존재하는 슬롯만 골라낸다 (슬롯 번호 오름차순).
 * 왜 걸러내야 하는지는 PHYSICAL_SLOT_COUNT 주석 참조.
 */
export function physicalSlots(slots: readonly Slot[]): Slot[] {
  return slots
    .filter((slot) => slot.slotNumber >= 1 && slot.slotNumber <= PHYSICAL_SLOT_COUNT)
    .sort((a, b) => a.slotNumber - b.slotNumber);
}

/**
 * 카트가 꽉 찼는지 — 실물 슬롯에 빈 자리가 하나도 없는 상태.
 *
 * EMPTY가 아니면 찬 것으로 본다. 인식 중(RECOGNIZING)이나 인식 실패(RECOGNITION_FAILED)도
 * 책이 물리적으로 올라가 있어 더 담을 수 없기 때문이다 — "책을 못 읽었으니 빈 칸"으로 세면
 * 사서에게 있지도 않은 자리를 알려주게 된다.
 *
 * 실물 슬롯을 다 받아보지 못했으면(응답 지연·부분 응답) 찬 것으로 판단하지 않는다.
 * 3개만 받은 상태에서 그 3개가 찼다고 "만적"을 띄우면 거짓 경고가 된다.
 */
export function isCartFull(slots: readonly Slot[]): boolean {
  const physical = physicalSlots(slots);
  return (
    physical.length === PHYSICAL_SLOT_COUNT &&
    physical.every((slot) => slot.status !== SlotStatus.EMPTY)
  );
}
