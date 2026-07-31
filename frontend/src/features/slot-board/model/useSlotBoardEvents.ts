import { useEffect } from 'react';

import { useQueryClient } from '@tanstack/react-query';

import { replaceSlot } from './slotCache';

import { getListSlotsQueryKey } from '@/shared/api/generated/slots/slots';
import { useCartSocket } from '@/shared/api/ws/useCartSocket';

import type { Slot } from '@/shared/api/generated/model';
import type { SlotUpdatedPayload } from '@/shared/api/ws/cartSocket';

/**
 * 슬롯 실시간 동기화 훅 (앱 레이아웃에서 한 번만 마운트).
 * WS-FE-04 SLOT_UPDATED를 구독해 슬롯 목록 쿼리 캐시를 즉시 갱신한다 —
 * RFID 태깅(적재/제거/인식 실패)이 새로고침 없이 슬롯 보드에 반영된다.
 *
 * 캐시가 없거나(슬롯 화면 미방문) 모르는 슬롯이면 무효화만 해서
 * 다음 조회 때 서버 값으로 복구한다.
 */
export function useSlotBoardEvents(cartId: number): void {
  const queryClient = useQueryClient();
  const socket = useCartSocket();

  useEffect(
    () =>
      socket.on<SlotUpdatedPayload>('SLOT_UPDATED', ({ payload }) => {
        const queryKey = getListSlotsQueryKey(cartId);
        const cached = queryClient.getQueryData<Slot[]>(queryKey);
        const next = cached ? replaceSlot(cached, payload) : null;
        if (next === null) {
          void queryClient.invalidateQueries({ queryKey });
          return;
        }
        queryClient.setQueryData(queryKey, next);
      }),
    [cartId, queryClient, socket],
  );
}
