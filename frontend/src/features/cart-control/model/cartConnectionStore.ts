import { create } from 'zustand';

interface CartConnectionState {
  /** 카트가 붙어 있는지. 확인 전에는 true — 화면 진입 직후 팝업이 잠깐 번쩍이지 않게 한다 */
  online: boolean;
  /** 마지막 통신 시각 (BE LocalDateTime 문자열, 모르면 null) */
  lastSeenAt: string | null;
  /** 사용자가 팝업을 닫았는지 — 같은 끊김 동안 다시 띄우지 않는다 */
  dismissed: boolean;
  /**
   * 연결 상태 반영 (WS-FE-03 또는 REST CART-01).
   * 끊겼다가 다시 붙은 경우에만 true를 반환한다 — 복구 알림을 띄울지 판단하는 용도.
   */
  applyConnection: (online: boolean, lastSeenAt?: string | null) => boolean;
  /** 팝업 닫기 */
  dismiss: () => void;
}

/**
 * 카트 연결 상태 스토어 (WS-FE-03).
 * 어느 화면에 있든 카트가 끊기면 알 수 있어야 해서 전역으로 둔다.
 */
export const useCartConnectionStore = create<CartConnectionState>()((set, get) => ({
  online: true,
  lastSeenAt: null,
  dismissed: false,
  applyConnection: (online, lastSeenAt) => {
    const wasOnline = get().online;
    set({
      online,
      ...(lastSeenAt !== undefined && { lastSeenAt }),
      // 상태가 바뀌었으면 닫음 표시를 푼다 — 새로 끊기면 다시 띄우고,
      // 복구되면 다음 끊김을 위해 초기화한다
      ...(online !== wasOnline && { dismissed: false }),
    });
    return online && !wasOnline;
  },
  dismiss: () => set({ dismissed: true }),
}));
