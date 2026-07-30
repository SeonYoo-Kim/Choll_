import { createBrowserRouter } from 'react-router';

import { AppLayout } from '@/app/AppLayout';
import { HomePage } from '@/pages/home/HomePage';
import { MapPage } from '@/pages/map/MapPage';
import { SearchPage } from '@/pages/search/SearchPage';
// import { SettingsPage } from '@/pages/settings/SettingsPage';
import { SlotsPage } from '@/pages/slots/SlotsPage';
import { RouteErrorFallback } from '@/shared/ui/error-boundary/RouteErrorFallback';

/**
 * 라우트 정의 — AppLayout(사이드바/하단탭) 아래에 페이지가 배치된다.
 * errorElement를 자식에 걸면 레이아웃은 남고 콘텐츠 영역만 폴백으로 바뀐다.
 * 루트의 errorElement는 AppLayout 자체(WS 연결 등)가 터진 경우를 받는다.
 * 예정: 추종 대상 선택(/follow-target, WebRTC).
 */
export const router = createBrowserRouter([
  {
    path: '/',
    element: <AppLayout />,
    errorElement: <RouteErrorFallback />,
    children: [
      { index: true, element: <HomePage />, errorElement: <RouteErrorFallback /> },
      {
        path: 'map',
        element: <MapPage />,
        errorElement: (
          <RouteErrorFallback
            emoji="🗺️"
            title="지도를 불러오지 못했어요"
            description="카트 위치 정보를 받아오는 중 문제가 생겼어요."
          />
        ),
      },
      {
        path: 'slots',
        element: <SlotsPage />,
        errorElement: (
          <RouteErrorFallback
            emoji="📦"
            title="슬롯 정보를 불러오지 못했어요"
            description="카트의 슬롯 상태를 받아오는 중 문제가 생겼어요."
          />
        ),
      },
      {
        path: 'search',
        element: <SearchPage />,
        errorElement: (
          <RouteErrorFallback
            emoji="🔎"
            title="도서 검색을 불러오지 못했어요"
            description="검색 기능에 문제가 생겼어요."
          />
        ),
      },
      // { path: 'settings', element: <SettingsPage /> },
      // 없는 주소 — 레이아웃 안에서 안내해 사이드바로 바로 되돌아갈 수 있게 한다
      { path: '*', element: <RouteErrorFallback notFound /> },
    ],
  },
]);
