import { create } from 'zustand';

import type { FollowStatus } from '@/shared/api/ws/cartSocket';

/** 카트 운행 상태 (WS CART_* 이벤트 및 제어 명령 응답으로 갱신) */
export type CartRunState = 'STOPPED' | 'MOVING' | 'FOLLOWING' | 'PAUSED';

/** WS-FE-07 추종 상태 → 운행 상태 매핑 */
const RUN_STATE_BY_FOLLOW: Record<FollowStatus, CartRunState> = {
  STARTED: 'FOLLOWING',
  PAUSED: 'PAUSED',
  STOPPED: 'STOPPED',
};

// 카트 연결 여부는 cartConnectionStore(WS-FE-03)가 담당한다 — 여기 있던 connected/setConnected는
// 아무도 쓰지 않는 값이어서 제거했다.
interface CartControlState {
  runState: CartRunState;
  setRunState: (state: CartRunState) => void;
  /** 추종 명령 응답·WS FOLLOW_STATUS_UPDATED(WS-FE-07) 반영 */
  applyFollowStatus: (status: FollowStatus) => void;
}

/**
 * 카트 제어 클라이언트 상태 스토어.
 * 서버 데이터(슬롯·작업 목록 등)는 TanStack Query가 담당하고,
 * 여기는 WS로 갱신되는 실시간 상태와 UI 상태만 둔다.
 */
export const useCartControlStore = create<CartControlState>()((set) => ({
  runState: 'STOPPED',
  setRunState: (runState) => set({ runState }),
  applyFollowStatus: (status) => set({ runState: RUN_STATE_BY_FOLLOW[status] }),
}));
