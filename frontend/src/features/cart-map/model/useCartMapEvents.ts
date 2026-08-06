import { useEffect, useRef, useState } from 'react';

import { useQueryClient } from '@tanstack/react-query';

import { useCartMapStore } from './cartMapStore';
import { displayToPercent } from './mapTransform';
import { useShelfZones } from './useShelfZones';
import { zoneLabel } from './zones';

import { getGetCartQueryKey, useGetCart } from '@/shared/api/generated/carts/carts';
import { useGetMap } from '@/shared/api/generated/maps/maps';
import { useCartSocket } from '@/shared/api/ws/useCartSocket';
import { useToastStore } from '@/shared/ui/toast/toastStore';

import type { MapInfo } from '@/shared/api/generated/model';
import type {
  CartPositionUpdatePayload,
  CurrentZoneUpdatedPayload,
  NavigationStatusUpdatedPayload,
} from '@/shared/api/ws/cartSocket';

/** 이동 중 이 시간 동안 카트에서 아무 이동 이벤트가 없으면 워치독이 상태를 리셋한다 */
const MOVE_WATCHDOG_MS = 30_000;

/** 이 시간 동안 좌표 변화가 없으면 위치 파생 이동 중 상태를 대기로 되돌린다 (위치 발행 주기 1초 기준) */
const STILLNESS_MS = 3_000;

/**
 * 카트 지도 상태 동기화 훅 (앱 레이아웃에서 한 번만 마운트).
 * - 진입 시 REST(getCart)로 초기 위치·구역·이동 상태를 복구하고
 * - 전역 CartSocket으로 위치(WS-FE-01)·구역(WS-FE-05)·이동 상태(WS-FE-06)를 구독해 스토어를 갱신한다.
 *   (연결 수명과 재연결 복구(BE-WS-03)는 CartSocketProvider가 담당)
 * - 이동 중 워치독: 일정 시간 이동 이벤트가 끊기면 상태를 리셋하고 REST로 실제 상태를 재확인한다.
 */
export function useCartMapEvents(cartId: number): void {
  const queryClient = useQueryClient();
  const socket = useCartSocket();
  // 이 훅은 AppLayout에서 마운트되므로 여기서 던지면 사이드바까지 사라진다.
  // 초기 복구가 실패해도 WS가 위치를 계속 주므로, 던지지 않고 토스트로만 알린다.
  const { data: cart, isError: isCartError } = useGetCart(cartId, {
    query: { throwOnError: false },
  });
  // WS 위치 이벤트가 알려준 지도 id — REST(cart.mapId)가 비어 있어도 지도를 조회할 수 있게 한다
  const [wsMapId, setWsMapId] = useState<number | null>(null);
  const mapId = wsMapId ?? cart?.mapId ?? null;
  const { data: mapInfo, isError: isMapError } = useGetMap(mapId ?? 0, {
    query: { enabled: mapId != null, throwOnError: false },
  });
  // 책장 구역 목록(MAP-02) — 평면도 구역에 서버 id를 채워 목적지를 지정할 수 있게 한다
  useShelfZones(mapId);

  // 던지지 않는 대신 조용히 넘어가지도 않게 한 번 알린다
  useEffect(() => {
    if (isCartError || isMapError) {
      useToastStore.getState().show('카트 상태를 불러오지 못했어요. 실시간 정보만 표시됩니다');
    }
  }, [isCartError, isMapError]);

  // 소켓 핸들러는 마운트 시 한 번 등록되므로, 최신 mapInfo는 ref로 전달한다
  const mapInfoRef = useRef<MapInfo | undefined>(mapInfo);
  useEffect(() => {
    mapInfoRef.current = mapInfo;
  }, [mapInfo]);

  const syncFromCart = useCartMapStore((state) => state.syncFromCart);
  const applyMapInfo = useCartMapStore((state) => state.applyMapInfo);

  // 바탕 그림은 번들 평면도를 쓰지만(floorPlanImage.ts) 좌표 기준은 서버 지도 메타를 따른다 —
  // WS 위치와 NAV-01 클릭 지점이 모두 BE 지도 픽셀이라 imageWidth·imageHeight가 필요하다
  useEffect(() => {
    // mapId를 아직 모르면 조회 자체가 시작되지 않은 것이므로 실패로 보지 않는다
    applyMapInfo(mapId === null ? undefined : mapInfo, isMapError);
  }, [mapId, mapInfo, isMapError, applyMapInfo]);

  useEffect(() => {
    if (!cart) {
      return;
    }
    syncFromCart({
      position: cart.position && mapInfo ? displayToPercent(cart.position, mapInfo) : undefined,
      zoneId: cart.currentZoneId ?? null,
      status: cart.status,
    });
  }, [cart, mapInfo, syncFromCart]);

  useEffect(() => {
    // 이동 워치독 — 이동 이벤트가 올 때마다 타이머를 되감고, 시간 초과 시 상태를 리셋한다
    let watchdogTimer: ReturnType<typeof setTimeout> | null = null;
    const clearWatchdog = () => {
      if (watchdogTimer !== null) {
        clearTimeout(watchdogTimer);
        watchdogTimer = null;
      }
    };
    const feedWatchdog = () => {
      clearWatchdog();
      if (!useCartMapStore.getState().isMoving) {
        return;
      }
      watchdogTimer = setTimeout(() => {
        if (!useCartMapStore.getState().isMoving) {
          return;
        }
        useCartMapStore.getState().abortMove();
        useToastStore.getState().show('카트 응답이 없어요. 상태를 다시 확인할게요');
        void queryClient.invalidateQueries({ queryKey: getGetCartQueryKey(cartId) });
      }, MOVE_WATCHDOG_MS);
    };
    // 이동 시작(startMove)·종료를 감지해 워치독을 시동/해제
    const unsubscribeWatchdog = useCartMapStore.subscribe((state, prevState) => {
      if (state.isMoving !== prevState.isMoving) {
        feedWatchdog();
      }
    });

    // 정지 감지 — 좌표가 움직일 때마다 되감고, 시간 초과 시 위치 파생 이동 중 상태를 해제한다
    let stillnessTimer: ReturnType<typeof setTimeout> | null = null;
    const clearStillness = () => {
      if (stillnessTimer !== null) {
        clearTimeout(stillnessTimer);
        stillnessTimer = null;
      }
    };
    const feedStillness = () => {
      clearStillness();
      stillnessTimer = setTimeout(() => useCartMapStore.getState().markStationary(), STILLNESS_MS);
    };

    const offPosition = socket.on<CartPositionUpdatePayload>(
      'CART_POSITION_UPDATE',
      ({ payload }) => {
        feedWatchdog();
        setWsMapId(payload.mapId); // 지도 미로딩 상태면 이 값으로 useGetMap이 시작된다
        const mapInfo = mapInfoRef.current;
        if (!payload.valid || !mapInfo) {
          return;
        }
        const { moved, enteredZone } = useCartMapStore
          .getState()
          .applyPosition(displayToPercent(payload, mapInfo), payload.yaw);
        if (enteredZone !== null) {
          useToastStore.getState().show(`카트가 ${zoneLabel(enteredZone)}에 진입했어요`);
        }
        if (moved) {
          feedStillness();
        }
      },
    );

    const offZone = socket.on<CurrentZoneUpdatedPayload>('CURRENT_ZONE_UPDATED', ({ payload }) => {
      feedWatchdog();
      const enteredZone = useCartMapStore.getState().applyZone(payload.currentZoneId);
      if (enteredZone !== null) {
        useToastStore.getState().show(`카트가 ${zoneLabel(enteredZone)}에 진입했어요`);
      }
    });

    const offNavigation = socket.on<NavigationStatusUpdatedPayload>(
      'NAVIGATION_STATUS_UPDATED',
      ({ payload }) => {
        useCartMapStore.getState().applyNavigation(payload.status, payload.destinationZoneId);
        feedWatchdog(); // 도착·취소로 isMoving이 꺼졌으면 타이머 해제, 진행 중이면 되감기
        // 실패는 조용히 대기 상태로 돌아가면 사서가 이유를 알 길이 없다.
        // BE가 사유를 주면 함께 보여주고, 없으면 실패 사실만 알린다
        if (payload.status === 'FAILED') {
          const reason = payload.failReason?.trim();
          useToastStore
            .getState()
            .show(reason ? `카트가 이동하지 못했어요 — ${reason}` : '카트가 이동하지 못했어요');
        }
      },
    );

    return () => {
      unsubscribeWatchdog();
      clearWatchdog();
      clearStillness();
      offPosition();
      offZone();
      offNavigation();
    };
  }, [cartId, queryClient, socket]);
}
