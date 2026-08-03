import { setupWorker } from 'msw/browser';

import { handlers } from '@/shared/api/mocks/handlers';
import { setCartOnline } from '@/shared/api/mocks/cartSimulator';

declare global {
  interface Window {
    /** 개발 편의 — 콘솔에서 카트 연결 끊김(WS-FE-03) 팝업을 확인할 때 쓴다 */
    __setCartOnline?: (online: boolean) => void;
  }
}

// 모킹 모드에서만 로드되는 파일이라 실제 서비스 번들에는 들어가지 않는다
window.__setCartOnline = setCartOnline;

/** 브라우저(개발 서버·E2E)용 MSW 워커. main.tsx에서 VITE_ENABLE_MSW=true일 때 시작된다. */
export const worker = setupWorker(...handlers);
