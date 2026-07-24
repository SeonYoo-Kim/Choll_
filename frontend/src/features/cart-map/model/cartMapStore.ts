import { create } from 'zustand';

import { CORRIDOR_Y, ZONE_NAMES, ZONE_POSITIONS, zoneLabel } from './zones';

interface CartMapState {
  /** 카트가 있는 구역 인덱스 (0-base) */
  cartZone: number;
  /** 지도 위 카트 좌표 (%) */
  cartPosition: { x: number; y: number };
  isMoving: boolean;
  /** 도착 알림 모달에 표시할 구역 인덱스 (null이면 닫힘) */
  arrivalZone: number | null;
  moveCart: (zone: number, notify: (message: string) => void) => void;
  dismissArrival: () => void;
}

const STEP_MS = 340;

/**
 * 지도 화면의 카트 위치/이동 상태 스토어.
 * 지금은 데모용 타이머 애니메이션이며, WS CART_POSITION_UPDATE 연동 시
 * moveCart 내부를 REST 명령(callCart) + 이벤트 수신으로 교체한다.
 */
export const useCartMapStore = create<CartMapState>()((set, get) => ({
  cartZone: 2,
  cartPosition: ZONE_POSITIONS[2],
  isMoving: false,
  arrivalZone: null,
  moveCart: (zone, notify) => {
    const { cartZone, isMoving } = get();
    if (isMoving) {
      return;
    }
    if (zone === cartZone) {
      notify(`${zoneLabel(zone)}에 이미 카트가 있어요`);
      return;
    }
    const start = ZONE_POSITIONS[cartZone];
    const destination = ZONE_POSITIONS[zone];
    set({ isMoving: true });
    notify(`${zoneLabel(zone)}으로 카트가 통로를 따라 이동해요`);
    // 구역 → 통로 → 목적지 순서로 경유지를 밟는다
    setTimeout(() => set({ cartPosition: { x: start.x, y: CORRIDOR_Y } }), 30);
    setTimeout(() => set({ cartPosition: { x: destination.x, y: CORRIDOR_Y } }), STEP_MS + 30);
    setTimeout(() => set({ cartPosition: destination }), STEP_MS * 2 + 30);
    setTimeout(
      () => {
        set({ cartZone: zone, isMoving: false, arrivalZone: zone });
        notify(`${zoneLabel(zone)} ${ZONE_NAMES[zone]} 서가에 도착했어요`);
      },
      STEP_MS * 3 + 60,
    );
  },
  dismissArrival: () => set({ arrivalZone: null }),
}));
