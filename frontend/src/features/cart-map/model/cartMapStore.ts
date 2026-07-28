import { create } from 'zustand';

import { ZONE_POSITIONS, zoneIndexOf } from './zones';

import type { MapPercent } from './mapTransform';

interface CartMapState {
  /** 카트가 있는 구역 인덱스 (0-base, 구역 밖이면 null) */
  cartZone: number | null;
  /** 지도 위 카트 좌표 (%) */
  cartPosition: MapPercent;
  isMoving: boolean;
  /** 도착 알림 모달에 표시할 구역 인덱스 (null이면 닫힘) */
  arrivalZone: number | null;
  /** 이동 명령(callCart) 접수 성공 시 호출 */
  startMove: () => void;
  /** WS CART_POSITION_UPDATE 반영. 구역이 바뀌면 바뀐 구역 인덱스를 반환한다(진입 알림용) */
  applyPosition: (position: MapPercent, zoneId: number | null) => number | null;
  /** WS CART_ARRIVED 반영 — 도착 모달을 연다 */
  applyArrival: (zoneId: number) => void;
  /** REST 재조회(초기 진입·재연결) 결과로 상태 동기화 */
  syncFromCart: (params: {
    position?: MapPercent;
    zoneId?: number | null;
    isMoving?: boolean;
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
  isMoving: false,
  arrivalZone: null,
  startMove: () => set({ isMoving: true }),
  applyPosition: (position, zoneId) => {
    const previousZone = get().cartZone;
    const zone = zoneId === null ? null : zoneIndexOf(zoneId);
    set({ cartPosition: position, cartZone: zone });
    return zone !== null && zone !== previousZone ? zone : null;
  },
  applyArrival: (zoneId) => {
    const zone = zoneIndexOf(zoneId);
    set({ isMoving: false, ...(zone !== null && { cartZone: zone, arrivalZone: zone }) });
  },
  syncFromCart: ({ position, zoneId, isMoving }) =>
    set((state) => ({
      cartPosition: position ?? state.cartPosition,
      cartZone: zoneId === undefined ? state.cartZone : zoneId === null ? null : zoneIndexOf(zoneId),
      isMoving: isMoving ?? state.isMoving,
    })),
  dismissArrival: () => set({ arrivalZone: null }),
}));
