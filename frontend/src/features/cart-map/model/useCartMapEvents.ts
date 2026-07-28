import { useEffect, useRef } from 'react';

import { useQueryClient } from '@tanstack/react-query';

import { useCartMapStore } from './cartMapStore';
import { toMapPercent } from './mapTransform';
import { ZONE_POSITIONS, zoneIndexOf, zoneLabel } from './zones';

import { getGetCartQueryKey, useGetCart } from '@/shared/api/generated/carts/carts';
import { useGetMap } from '@/shared/api/generated/maps/maps';
import { getListSlotsQueryKey } from '@/shared/api/generated/slots/slots';
import { getGetTaskProgressQueryKey } from '@/shared/api/generated/tasks/tasks';
import { CartSocket } from '@/shared/api/ws/cartSocket';
import { useToastStore } from '@/shared/ui/toast/toastStore';

import type { MapInfo } from '@/shared/api/generated/model';
import type {
  CartArrivedPayload,
  CartPositionUpdatePayload,
} from '@/shared/api/ws/cartSocket';

/**
 * 지도 화면의 카트 상태 동기화 훅.
 * - 진입 시 REST(getCart)로 초기 위치·구역·이동 상태를 복구하고
 * - CartSocket으로 CART_POSITION_UPDATE / CART_ARRIVED를 구독해 스토어를 갱신한다.
 * - WS 재연결 시 관련 쿼리를 invalidate해 REST 재조회로 상태를 복구한다(BE-WS-03).
 */
export function useCartMapEvents(cartId: number): void {
  const queryClient = useQueryClient();
  const { data: cart } = useGetCart(cartId);
  const { data: mapInfo } = useGetMap(cart?.mapId ?? 0, {
    query: { enabled: cart?.mapId != null },
  });

  // 소켓 핸들러는 마운트 시 한 번 등록되므로, 최신 mapInfo는 ref로 전달한다
  const mapInfoRef = useRef<MapInfo | undefined>(mapInfo);
  useEffect(() => {
    mapInfoRef.current = mapInfo;
  }, [mapInfo]);

  const syncFromCart = useCartMapStore((state) => state.syncFromCart);

  useEffect(() => {
    if (!cart) {
      return;
    }
    syncFromCart({
      position:
        cart.position && mapInfo ? toMapPercent(cart.position, mapInfo) : undefined,
      zoneId: cart.currentZoneId ?? null,
      isMoving: cart.status === 'MOVING',
    });
  }, [cart, mapInfo, syncFromCart]);

  useEffect(() => {
    const socket = new CartSocket(String(cartId), {
      onReconnect: () => {
        void queryClient.invalidateQueries({ queryKey: getGetCartQueryKey(cartId) });
        void queryClient.invalidateQueries({ queryKey: getListSlotsQueryKey(cartId) });
        void queryClient.invalidateQueries({ queryKey: getGetTaskProgressQueryKey(cartId) });
      },
    });

    const offPosition = socket.on<CartPositionUpdatePayload>(
      'CART_POSITION_UPDATE',
      ({ payload }) => {
        const { applyPosition } = useCartMapStore.getState();
        const zone = payload.zoneId === null ? null : zoneIndexOf(payload.zoneId);
        const percent = mapInfoRef.current
          ? toMapPercent(payload.position, mapInfoRef.current)
          : zone !== null
            ? ZONE_POSITIONS[zone]
            : null;
        if (percent === null) {
          return;
        }
        const enteredZone = applyPosition(percent, payload.zoneId);
        if (enteredZone !== null) {
          useToastStore.getState().show(`카트가 ${zoneLabel(enteredZone)}에 진입했어요`);
        }
      },
    );

    const offArrived = socket.on<CartArrivedPayload>('CART_ARRIVED', ({ payload }) => {
      useCartMapStore.getState().applyArrival(payload.zoneId);
    });

    socket.connect();
    return () => {
      offPosition();
      offArrived();
      socket.close();
    };
  }, [cartId, queryClient]);
}
