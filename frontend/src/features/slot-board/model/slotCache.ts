import type { Slot } from '@/shared/api/generated/model';

/**
 * 슬롯 목록 캐시에서 slotNumber가 일치하는 항목을 갱신분으로 교체한 새 배열을 만든다.
 * 일치하는 슬롯이 없으면 null — 호출부가 캐시를 무효화해 서버 값으로 복구하게 한다.
 * (slotNumber는 카트 안에서 유일하다: BE uk cartId+slotNumber)
 */
export function replaceSlot(slots: readonly Slot[], updated: Slot): Slot[] | null {
  if (!slots.some((slot) => slot.slotNumber === updated.slotNumber)) {
    return null;
  }
  return slots.map((slot) => (slot.slotNumber === updated.slotNumber ? updated : slot));
}
