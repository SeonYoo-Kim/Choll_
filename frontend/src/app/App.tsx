import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ConfigProvider } from 'antd';
import koKR from 'antd/locale/ko_KR';
import { RouterProvider } from 'react-router';

import { router } from '@/app/router';
import { ErrorBoundary } from '@/shared/ui/error-boundary/ErrorBoundary';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      staleTime: 30_000,
      refetchOnWindowFocus: false,
      // 쿼리 실패를 렌더 에러로 던져 라우트 errorElement가 받게 한다.
      // 사서에게 "0권"이라고 거짓 숫자를 보여주는 것보다 에러 화면이 안전하다.
      // 단, AppLayout에서 도는 쿼리(useGetCart·useGetMap)는 던지면 사이드바까지
      // 사라지므로 useCartMapEvents에서 개별로 끈다.
      throwOnError: true,
    },
  },
});

export default function App() {
  return (
    <ErrorBoundary>
      <QueryClientProvider client={queryClient}>
        <ConfigProvider locale={koKR}>
          <RouterProvider router={router} />
        </ConfigProvider>
      </QueryClientProvider>
    </ErrorBoundary>
  );
}
