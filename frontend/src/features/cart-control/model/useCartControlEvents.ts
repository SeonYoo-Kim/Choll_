import { useEffect } from 'react';

import { useCartControlStore } from './cartControlStore';

import { useCartSocket } from '@/shared/api/ws/useCartSocket';

import type { FollowStatus, FollowStatusUpdatedPayload } from '@/shared/api/ws/cartSocket';

/** 스토어가 아는 추종 상태 값 — BE가 모르는 값을 보냈을 때 걸러내기 위한 목록 */
const KNOWN_FOLLOW_STATUSES: readonly FollowStatus[] = ['STARTED', 'PAUSED', 'STOPPED'];

/**
 * 카트 추종 상태 동기화 훅 (앱 레이아웃에서 한 번만 마운트).
 * WS-FE-07 FOLLOW_STATUS_UPDATED를 구독해 스토어에 반영한다.
 *
 * 버튼 조작 시에는 CartControlCard가 낙관적으로 먼저 갱신하고 이 훅이 서버 상태로 확정한다.
 * 카트가 스스로 추종을 멈춘 경우(사서를 놓침·AI 실패 등)에는 버튼을 누르지 않아도
 * 이 구독으로만 화면이 따라간다 — 이게 없으면 계속 "추종 중"으로 남는다.
 *
 * cartId를 받지 않는 이유: 소켓이 이미 /ws/carts/{cartId}로 카트에 묶여 있다.
 */
export function useCartControlEvents(): void {
  const socket = useCartSocket();

  useEffect(
    () =>
      socket.on<FollowStatusUpdatedPayload>('FOLLOW_STATUS_UPDATED', ({ payload }) => {
        // 상태 값 이름은 BE 확정 전이다(cartSocket.ts TODO). 모르는 값이 오면
        // runState를 undefined로 만들지 않고 로그만 남기고 무시한다.
        if (!KNOWN_FOLLOW_STATUSES.includes(payload.status)) {
          console.warn('[CartControl] 알 수 없는 추종 상태:', payload.status);
          return;
        }
        useCartControlStore.getState().applyFollowStatus(payload.status);
      }),
    [socket],
  );
}
