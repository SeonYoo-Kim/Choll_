import { create } from 'zustand';

/** 카트 운행 상태 (WS CART_* 이벤트 및 제어 명령 응답으로 갱신) */
export type CartRunState = 'STOPPED' | 'MOVING' | 'FOLLOWING';

interface CartControlState {
  runState: CartRunState;
  /** WS 연결 여부 — 화면에 연결 끊김 표시용 */
  connected: boolean;
  setRunState: (state: CartRunState) => void;
  setConnected: (connected: boolean) => void;
}

/**
 * 카트 제어 클라이언트 상태 스토어.
 * 서버 데이터(슬롯·작업 목록 등)는 TanStack Query가 담당하고,
 * 여기는 WS로 갱신되는 실시간 상태와 UI 상태만 둔다.
 */
export const useCartControlStore = create<CartControlState>()((set) => ({
  runState: 'STOPPED',
  connected: false,
  setRunState: (runState) => set({ runState }),
  setConnected: (connected) => set({ connected }),
}));
