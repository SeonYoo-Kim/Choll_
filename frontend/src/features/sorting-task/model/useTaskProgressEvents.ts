import { useEffect } from 'react';

import { useQueryClient } from '@tanstack/react-query';

import { getGetTaskProgressQueryKey } from '@/shared/api/generated/tasks/tasks';

import type { TaskProgressUpdatedPayload } from '@/shared/api/ws/cartSocket';
import { useCartSocket } from '@/shared/api/ws/useCartSocket';

/**
 * 정리 진행률 실시간 동기화 훅 (앱 레이아웃에서 한 번만 마운트).
 * WS-FE-10 TASK_PROGRESS_UPDATED를 구독해 진행률 쿼리 캐시를 즉시 교체한다 —
 * RFID 태깅(적재/정리 완료)이 새로고침 없이 정리 현황 카드에 반영된다.
 */

export function useTaskProgressEvents(cartId: number): void {
  const queryClient = useQueryClient();
  const socket = useCartSocket();

  useEffect(
    () =>
      socket.on<TaskProgressUpdatedPayload>('TASK_PROGRESS_UPDATED', ({ payload }) => {
        queryClient.setQueryData(getGetTaskProgressQueryKey(cartId), payload);
      }),
    [cartId, queryClient, socket],
  );
}
