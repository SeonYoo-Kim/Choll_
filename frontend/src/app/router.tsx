import { createBrowserRouter } from 'react-router';

import { DashboardPage } from '@/pages/dashboard/DashboardPage';

/**
 * 라우트 정의.
 * 페이지가 추가되면 여기에 등록한다 (지도 / 정리 작업 / 추종 대상 선택 등).
 */
export const router = createBrowserRouter([
  {
    path: '/',
    element: <DashboardPage />,
  },
]);
