import { useEffect, useRef } from 'react';

import { useQueryClient } from '@tanstack/react-query';

import { useCartMapStore } from './cartMapStore';
import { displayToPercent } from './mapTransform';
import { zoneLabel } from './zones';

import { getGetCartQueryKey, useGetCart } from '@/shared/api/generated/carts/carts';
import { useGetMap } from '@/shared/api/generated/maps/maps';
import { getListSlotsQueryKey } from '@/shared/api/generated/slots/slots';
import { getGetTaskProgressQueryKey } from '@/shared/api/generated/tasks/tasks';
import { CartSocket } from '@/shared/api/ws/cartSocket';
import { useToastStore } from '@/shared/ui/toast/toastStore';

import type { MapInfo } from '@/shared/api/generated/model';
import type {
  CartPositionUpdatePayload,
  CurrentZoneUpdatedPayload,
  NavigationStatusUpdatedPayload,
} from '@/shared/api/ws/cartSocket';

/**
 * 지도 화면의 카트 상태 동기화 훅.
 * - 진입 시 REST(getCart)로 초기 위치·구역·이동 상태를 복구하고
 * - CartSocket으로 위치(WS-FE-01)·구역(WS-FE-05)·이동 상태(WS-FE-06)를 구독해 스토어를 갱신한다.
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
        cart.position && mapInfo ? displayToPercent(cart.position, mapInfo) : undefined,
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
        const mapInfo = mapInfoRef.current;
        if (!payload.valid || !mapInfo) {
          return;
        }
        useCartMapStore.getState().applyPosition(displayToPercent(payload, mapInfo));
      },
    );

    const offZone = socket.on<CurrentZoneUpdatedPayload>('CURRENT_ZONE_UPDATED', ({ payload }) => {
      const enteredZone = useCartMapStore.getState().applyZone(payload.currentZoneId);
      if (enteredZone !== null) {
        useToastStore.getState().show(`카트가 ${zoneLabel(enteredZone)}에 진입했어요`);
      }
    });

    const offNavigation = socket.on<NavigationStatusUpdatedPayload>(
      'NAVIGATION_STATUS_UPDATED',
      ({ payload }) => {
        useCartMapStore.getState().applyNavigation(payload.status, payload.destinationZoneId);
      },
    );

    socket.connect();
    return () => {
      offPosition();
      offZone();
      offNavigation();
      socket.close();
    };
  }, [cartId, queryClient]);
}
