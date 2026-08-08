import type { Slot } from '@/shared/api/generated/model';

/**
 * 정리 대상 슬롯 판정 — "이 슬롯의 책을 어느 구역에서 꺼내야 하는가".
 *
 * 구역 이름 문자열("3구역") 비교로 판정하지 않는다. 서버가 주는 이름과 화면이 만드는 이름이
 * 한 글자라도 다르면 오류 없이 조용히 0건이 되기 때문이다. 구역 id(숫자)로만 맞춘다.
 *
 * 서버도 같은 뜻의 `Slot.isTarget`을 주지만 쓰지 않는다. 그 값은 **서버가 응답을 만든 시점의
 * 카트 구역** 기준이라, 이동 중에 받아온 응답은 전부 false이고 도착 후에도 캐시가 만료될
 * 때까지(staleTime 30초) 그대로 남는다. 여기서 쓰는 두 값(책의 `shelfZoneId`, WS로 오는
 * 카트 현재 구역)은 서버가 isTarget을 계산할 때 쓰는 것과 같은 값이므로 결과는 같으면서
 * 캐시 시점에 흔들리지 않는다.
 */

/**
 * 이 슬롯의 책이 주어진 구역(shelf_zone.id)에 꽂을 책인가.
 *
 * `zoneId`가 null이면(구역 밖 — 통로·출발 지점) 어떤 슬롯도 대상이 아니다.
 * 카트가 지금 있는 구역을 물으려면 현재 구역 id를 넘기면 된다.
 */
export function isSlotForZone(slot: Slot, zoneId: number | null): boolean {
  return zoneId !== null && slot.book?.shelfZoneId === zoneId;
}
