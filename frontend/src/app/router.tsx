import { createBrowserRouter } from 'react-router';

import { AppLayout } from '@/app/AppLayout';
import { HomePage } from '@/pages/home/HomePage';
import { MapPage } from '@/pages/map/MapPage';
import { SearchPage } from '@/pages/search/SearchPage';
import { SettingsPage } from '@/pages/settings/SettingsPage';
import { SlotsPage } from '@/pages/slots/SlotsPage';

/**
 * 라우트 정의 — AppLayout(사이드바/하단탭) 아래에 페이지가 배치된다.
 * 예정: 추종 대상 선택(/follow-target, WebRTC).
 */
export const router = createBrowserRouter([
  {
    path: '/',
    element: <AppLayout />,
    children: [
      { index: true, element: <HomePage /> },
      { path: 'map', element: <MapPage /> },
      { path: 'slots', element: <SlotsPage /> },
      { path: 'search', element: <SearchPage /> },
      { path: 'settings', element: <SettingsPage /> },
    ],
  },
]);
