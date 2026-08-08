import { useEffect } from 'react';

import { useCartConnectionStore } from './cartConnectionStore';

import { useGetCart } from '@/shared/api/generated/carts/carts';
import { useCartSocket } from '@/shared/api/ws/useCartSocket';
import { useToastStore } from '@/shared/ui/toast/toastStore';

import type { CartConnectionUpdatedPayload } from '@/shared/api/ws/cartSocket';

/**
 * 카트 연결 상태 동기화 훅 (앱 레이아웃에서 한 번만 마운트).
 *
 * BE는 연결 상태가 **바뀌는 순간에만** WS-FE-03을 보낸다. 그래서 두 곳에서 채운다:
 * - 진입·재연결 시: REST CART-01의 `online`으로 현재 상태를 잡는다
 *   (이미 끊긴 채로 들어오면 WS만으로는 영영 알 수 없다)
 * - 이후 변화: WS CART_CONNECTION_UPDATED
 */
export function useCartConnectionEvents(cartId: number): void {
  const socket = useCartSocket();
  // 카트를 못 불러와도 화면이 죽지 않게 던지지 않는다 (useCartMapEvents와 같은 방침).
  // 같은 쿼리를 useCartMapEvents도 쓰므로 요청이 중복되지는 않는다.
  const { data: cart } = useGetCart(cartId, { query: { throwOnError: false } });

  useEffect(() => {
    if (cart) {
      useCartConnectionStore.getState().applyConnection(cart.online, cart.lastSeenAt);
    }
  }, [cart]);

  useEffect(
    () =>
      socket.on<CartConnectionUpdatedPayload>('CART_CONNECTION_UPDATED', ({ payload }) => {
        const recovered = useCartConnectionStore
          .getState()
          .applyConnection(payload.online, payload.lastSeenAt);
        if (recovered) {
          useToastStore.getState().show('카트와 다시 연결됐어요');
        }
      }),
    [socket],
  );
}
