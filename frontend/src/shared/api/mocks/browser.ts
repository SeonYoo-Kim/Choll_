import { setupWorker } from 'msw/browser';

import { handlers } from '@/shared/api/mocks/handlers';

/** 브라우저(개발 서버·E2E)용 MSW 워커. main.tsx에서 VITE_ENABLE_MSW=true일 때 시작된다. */
export const worker = setupWorker(...handlers);
