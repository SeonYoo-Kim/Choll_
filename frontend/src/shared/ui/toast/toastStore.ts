import { create } from 'zustand';

interface ToastState {
  message: string;
  show: (message: string) => void;
}

const TOAST_DURATION_MS = 2_200;

let hideTimer: ReturnType<typeof setTimeout> | null = null;

/** 하단 토스트 알림 스토어. `useToastStore.getState().show('...')` 또는 훅으로 사용. */
export const useToastStore = create<ToastState>()((set) => ({
  message: '',
  show: (message) => {
    set({ message });
    if (hideTimer !== null) {
      clearTimeout(hideTimer);
    }
    hideTimer = setTimeout(() => set({ message: '' }), TOAST_DURATION_MS);
  },
}));
