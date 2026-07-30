import { useEffect, useState } from 'react';

import { useQueryClient } from '@tanstack/react-query';

import { CartSocket } from './cartSocket';
import { CartSocketContext } from './cartSocketContext';

import { getGetCartQueryKey } from '@/shared/api/generated/carts/carts';
import { getListSlotsQueryKey } from '@/shared/api/generated/slots/slots';
import { getGetTaskProgressQueryKey } from '@/shared/api/generated/tasks/tasks';

import type { ReactNode } from 'react';

interface CartSocketProviderProps {
  cartId: number;
  children: ReactNode;
}

/**
 * 앱 전역 카트 WebSocket 연결 프로바이더.
 * 소켓 인스턴스를 하나만 만들어 모든 페이지가 공유하고(페이지 이동에도 연결 유지),
 * feature 훅들은 useCartSocket()으로 받아 구독만 한다.
 *
 * 인스턴스를 렌더 시점에 동기 생성하는 이유: 자식의 useEffect가 부모보다 먼저 실행되므로,
 * 자식 훅이 구독을 걸 때 소켓이 이미 존재해야 한다. 연결/해제만 effect에서 다뤄
 * StrictMode의 이중 실행(connect→close→connect)에도 안전하다.
 */
export function CartSocketProvider({ cartId, children }: CartSocketProviderProps) {
  const queryClient = useQueryClient();

  const [socket] = useState(
    () =>
      new CartSocket(String(cartId), {
        onReconnect: () => {
          // BE-WS-03: 재연결 시 REST 재조회로 상태 복구 — 전역 관심사라 여기서 처리한다
          void queryClient.invalidateQueries({ queryKey: getGetCartQueryKey(cartId) });
          void queryClient.invalidateQueries({ queryKey: getListSlotsQueryKey(cartId) });
          void queryClient.invalidateQueries({ queryKey: getGetTaskProgressQueryKey(cartId) });
        },
      }),
  );

  useEffect(() => {
    socket.connect();
    return () => socket.close();
  }, [socket]);

  return <CartSocketContext.Provider value={socket}>{children}</CartSocketContext.Provider>;
}
