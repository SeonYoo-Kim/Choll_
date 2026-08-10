import { SlotStatus } from '@/shared/api/generated/model';
import { CART_FULL_THRESHOLD, PHYSICAL_SLOT_COUNT } from '@/shared/config/cart';

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
 * 카트가 꽉 찼는지 — 실물 슬롯 중 CART_FULL_THRESHOLD개 이상 책이 올라간 상태.
 *
 * EMPTY가 아니면 찬 것으로 본다. 인식 중(RECOGNIZING)이나 인식 실패(RECOGNITION_FAILED)도
 * 책이 물리적으로 올라가 있어 더 담을 수 없기 때문이다 — "책을 못 읽었으니 빈 칸"으로 세면
 * 사서에게 있지도 않은 자리를 알려주게 된다.
 *
 * 부분 응답(응답 지연으로 실물 슬롯 일부만 도착)은 찬 슬롯을 실제보다 적게 셀 수만 있어
 * 거짓 경고가 나지 않는다 — 받은 것 중 임계값만큼 찼다면 그 책들은 실제로 카트에 있다.
 */
export function isCartFull(slots: readonly Slot[]): boolean {
  const occupied = physicalSlots(slots).filter((slot) => slot.status !== SlotStatus.EMPTY);
  return occupied.length >= CART_FULL_THRESHOLD;
}
