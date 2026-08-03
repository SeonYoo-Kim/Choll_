import { render, screen } from '@testing-library/react';
import type { ReactElement } from 'react';
import { RouterProvider, createMemoryRouter } from 'react-router';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { RouteErrorFallback } from './RouteErrorFallback';

/** 렌더 중 에러를 던지는 페이지 — errorElement가 뜨는 상황을 만든다 */
function ThrowingPage(): never {
  throw new Error('테스트용 렌더 에러');
}

/** 라우트에서 에러가 터진 뒤 errorElement가 렌더된 화면 */
function renderAfterRouteError(errorElement: ReactElement) {
  const router = createMemoryRouter([{ path: '/', element: <ThrowingPage />, errorElement }], {
    initialEntries: ['/'],
  });
  return render(<RouterProvider router={router} />);
}

/** 매칭되는 라우트가 없어 라우터가 404를 던진 화면 */
function renderUnmatchedPath(errorElement: ReactElement) {
  const router = createMemoryRouter([{ path: '/', element: <div>홈</div>, errorElement }], {
    initialEntries: ['/없는주소'],
  });
  return render(<RouterProvider router={router} />);
}

describe('RouteErrorFallback', () => {
  // React와 react-router가 잡은 에러를 콘솔에 찍어 테스트 출력이 시끄러워지는 것만 막는다
  beforeEach(() => {
    vi.spyOn(console, 'error').mockImplementation(() => {});
    vi.spyOn(console, 'warn').mockImplementation(() => {});
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('없는 주소면 없는 페이지 안내와 홈으로 버튼을 보여준다', () => {
    renderUnmatchedPath(<RouteErrorFallback />);

    expect(screen.getByText('없는 페이지예요')).toBeInTheDocument();
    expect(screen.getByText('주소를 다시 확인해 주세요.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '홈으로' })).toBeInTheDocument();
  });

  it('notFound prop을 주면 던져진 에러가 없어도 없는 페이지 안내를 보여준다', () => {
    // catch-all 라우트(path: '*')의 element로 쓰는 경우 — useRouteError()가 undefined다
    const router = createMemoryRouter([{ path: '*', element: <RouteErrorFallback notFound /> }], {
      initialEntries: ['/없는주소'],
    });
    render(<RouterProvider router={router} />);

    expect(screen.getByText('없는 페이지예요')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '홈으로' })).toBeInTheDocument();
  });

  it('렌더 에러면 넘겨준 페이지별 문구와 다시 시도 버튼을 보여준다', () => {
    renderAfterRouteError(
      <RouteErrorFallback
        title="지도를 불러오지 못했어요"
        description="카트 위치 정보를 받아오는 중 문제가 생겼어요."
      />,
    );

    expect(screen.getByText('지도를 불러오지 못했어요')).toBeInTheDocument();
    expect(screen.getByText('카트 위치 정보를 받아오는 중 문제가 생겼어요.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '다시 시도' })).toBeInTheDocument();
    // 404 문구가 섞이지 않아야 한다
    expect(screen.queryByText('없는 페이지예요')).not.toBeInTheDocument();
  });

  it('문구를 넘기지 않으면 일반 문구를 쓴다', () => {
    renderAfterRouteError(<RouteErrorFallback />);

    expect(screen.getByText('화면을 불러오지 못했어요')).toBeInTheDocument();
    expect(screen.getByText('잠시 후 다시 시도해 주세요.')).toBeInTheDocument();
  });

  it('에러 원문은 화면에 노출하지 않고 콘솔에만 남긴다', () => {
    renderAfterRouteError(<RouteErrorFallback />);

    expect(screen.queryByText('테스트용 렌더 에러')).not.toBeInTheDocument();
    expect(console.error).toHaveBeenCalledWith('[RouteError]', expect.any(Error));
  });
});
