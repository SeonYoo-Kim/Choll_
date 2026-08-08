import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { HomePage } from './HomePage';

import { useCartConnectionStore } from '@/features/cart-control/model/cartConnectionStore';
import { useCartControlStore } from '@/features/cart-control/model/cartControlStore';
import { useCartMapStore } from '@/features/cart-map/model/cartMapStore';

const { httpMock } = vi.hoisted(() => ({ httpMock: vi.fn() }));
vi.mock('@/shared/api/http', () => ({ http: httpMock }));

function renderHome() {
  // retry 0 — 슬롯 조회는 이 테스트의 관심사가 아니라 실패해도 그냥 두고 배지만 본다
  const client = new QueryClient({ defaultOptions: { queries: { retry: 0 } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <HomePage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  httpMock.mockResolvedValue([]);
  useCartConnectionStore.setState({ online: true, lastSeenAt: null, dismissed: false });
  useCartControlStore.setState({ runState: 'STOPPED' });
  useCartMapStore.setState({ isMoving: false, cartStatus: 'IDLE' });
});

describe('HomePage 상단 배지', () => {
  it('연결이 끊기면 경고 배지를 띄운다', () => {
    useCartConnectionStore.setState({ online: false });
    renderHome();
    expect(screen.getByText('카트와 연결이 끊겼어요')).toBeInTheDocument();
  });

  /**
   * 팝업(CartOfflineModal)은 닫으면 사라지므로, 닫은 뒤에도 남는 표시는 이 배지뿐이다.
   * 이게 없으면 사서가 끊긴 카트를 연결된 것으로 착각한 채 계속 조작한다.
   */
  it('팝업을 닫아도 배지는 남는다', () => {
    useCartConnectionStore.setState({ online: false, dismissed: true });
    renderHome();
    expect(screen.getByText('카트와 연결이 끊겼어요')).toBeInTheDocument();
  });

  it('연결이 끊기면 추종·이동 상태보다 끊김을 먼저 알린다', () => {
    useCartConnectionStore.setState({ online: false });
    useCartControlStore.setState({ runState: 'FOLLOWING' });
    renderHome();
    expect(screen.getByText('카트와 연결이 끊겼어요')).toBeInTheDocument();
    expect(screen.queryByText('카트가 따라오는 중')).not.toBeInTheDocument();
  });

  it('연결되어 있으면 기존 운행 상태를 그대로 보여준다', () => {
    useCartControlStore.setState({ runState: 'FOLLOWING' });
    renderHome();
    expect(screen.getByText('카트가 따라오는 중')).toBeInTheDocument();
  });
});
