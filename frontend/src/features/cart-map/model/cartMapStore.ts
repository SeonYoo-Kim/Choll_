import { create } from 'zustand';

import { ZONE_POSITIONS, zoneIndexOf } from './zones';

import type { MapPercent } from './mapTransform';
import type { CartDetailStatus } from '@/shared/api/generated/model';
import type { NavigationStatus } from '@/shared/api/ws/cartSocket';

/** 이동 중으로 취급하는 이동 상태 (접수·시작) */
const MOVING_STATUSES: readonly NavigationStatus[] = ['ACCEPTED', 'STARTED'];

interface CartMapState {
  /** 카트가 있는 구역 인덱스 (0-base, 구역 밖이면 null) */
  cartZone: number | null;
  /** 지도 위 카트 좌표 (%) */
  cartPosition: MapPercent;
  /** 지도 이미지 기준 카트 방향각 (라디안) */
  cartYaw: number;
  /** 카트 동작 상태 (CART-01 응답 CartStatus: IDLE·MOVING·FOLLOWING·ERROR) */
  cartStatus: CartDetailStatus;
  /** 마지막으로 수신한 목적지 이동 상태 (WS-FE-06, 이동 명령 전이면 null) */
  navStatus: NavigationStatus | null;
  /** cartStatus가 MOVING인지의 편의 플래그 */
  isMoving: boolean;
  /** 도착 알림 모달에 표시할 구역 인덱스 (null이면 닫힘) */
  arrivalZone: number | null;
  /** 이동 명령(NAV-01) 접수 성공 시 낙관적 표시 — WS 이벤트 도착 전 버튼 잠금용 */
  startMove: () => void;
  /** WS CART_POSITION_UPDATE(WS-FE-01) 반영 */
  applyPosition: (position: MapPercent, yaw: number) => void;
  /** WS CURRENT_ZONE_UPDATED(WS-FE-05) 반영. 새 구역에 진입했으면 그 인덱스를 반환(진입 알림용) */
  applyZone: (currentZoneId: number | null) => number | null;
  /** WS NAVIGATION_STATUS_UPDATED(WS-FE-06) 반영 — ARRIVED면 도착 모달을 연다 */
  applyNavigation: (status: NavigationStatus, destinationZoneId?: number) => void;
  /** 워치독 발동 시 이동 상태 강제 리셋 — 이후 REST 재조회(syncFromCart)로 실제 상태를 복구한다 */
  abortMove: () => void;
  /** REST 재조회(초기 진입·재연결) 결과로 상태 동기화 */
  syncFromCart: (params: {
    position?: MapPercent;
    zoneId?: number | null;
    status?: CartDetailStatus;
  }) => void;
  dismissArrival: () => void;
}

/**
 * 지도 화면의 카트 위치/이동 상태 스토어.
 * 상태 변경은 REST 응답과 WS 이벤트(useCartMapEvents)로만 일어난다.
 * 개발 중 이동 시뮬레이션은 MSW 계층(shared/api/mocks/cartSimulator.ts)에 있다.
 */
export const useCartMapStore = create<CartMapState>()((set, get) => ({
  cartZone: null,
  cartPosition: ZONE_POSITIONS[2],
  cartYaw: 0,
  cartStatus: 'IDLE',
  navStatus: null,
  isMoving: false,
  arrivalZone: null,
  startMove: () => set({ isMoving: true, cartStatus: 'MOVING', navStatus: 'ACCEPTED' }),
  applyPosition: (position, yaw) => set({ cartPosition: position, cartYaw: yaw }),
  applyZone: (currentZoneId) => {
    const previousZone = get().cartZone;
    const zone = currentZoneId === null ? null : zoneIndexOf(currentZoneId);
    set({ cartZone: zone });
    return zone !== null && zone !== previousZone ? zone : null;
  },
  applyNavigation: (status, destinationZoneId) => {
    if (MOVING_STATUSES.includes(status)) {
      set({ navStatus: status, isMoving: true, cartStatus: 'MOVING' });
      return;
    }
    if (status === 'ARRIVED') {
      const zone = destinationZoneId === undefined ? get().cartZone : zoneIndexOf(destinationZoneId);
      set({
        navStatus: status,
        isMoving: false,
        cartStatus: 'IDLE',
        ...(zone !== null && { cartZone: zone, arrivalZone: zone }),
      });
      return;
    }
    // STOPPED · CANCELLED · FAILED — 이동만 끝나고 카트는 대기 상태로 돌아간다
    set({ navStatus: status, isMoving: false, cartStatus: 'IDLE' });
  },
  abortMove: () => set({ isMoving: false, cartStatus: 'IDLE', navStatus: null }),
  syncFromCart: ({ position, zoneId, status }) =>
    set((state) => ({
      cartPosition: position ?? state.cartPosition,
      cartZone: zoneId === undefined ? state.cartZone : zoneId === null ? null : zoneIndexOf(zoneId),
      cartStatus: status ?? state.cartStatus,
      isMoving: status === undefined ? state.isMoving : status === 'MOVING',
    })),
  dismissArrival: () => set({ arrivalZone: null }),
}));
