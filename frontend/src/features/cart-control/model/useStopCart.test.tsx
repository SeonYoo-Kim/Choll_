import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { useCartControlStore } from './cartControlStore';
import { useStopCart } from './useStopCart';

import { useCartMapStore } from '@/features/cart-map/model/cartMapStore';
import { useToastStore } from '@/shared/ui/toast/toastStore';

import type { AxiosRequestConfig } from 'axios';
import type { ReactNode } from 'react';

const { httpMock } = vi.hoisted(() => ({ httpMock: vi.fn() }));
vi.mock('@/shared/api/http', () => ({ http: httpMock }));

const CART_ID = 1;

function setup() {
  const queryClient = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
  return renderHook(() => useStopCart(CART_ID), { wrapper });
}

/** 실제로 나간 요청을 (메서드 URL) 문자열로 모아 본다 */
const sentRequests = (): string[] =>
  httpMock.mock.calls.map((call) => {
    const config = call[0] as AxiosRequestConfig;
    return `${config.method} ${config.url}`;
  });

/** 토스트 호출 횟수를 세기 위해 스토어의 show를 스파이로 갈아끼운다 (훅이 렌더 시점에 집어간다) */
let showSpy = vi.fn();

/** 정지 안내가 몇 번 떴는지 */
const stopNoticeCount = (): number =>
  showSpy.mock.calls.filter((call) => call[0] === '카트를 멈추라고 전달했어요').length;

describe('useStopCart', () => {
  beforeEach(() => {
    httpMock.mockReset();
    httpMock.mockResolvedValue(undefined);
    showSpy = vi.fn();
    useToastStore.setState({ show: showSpy });
    useCartControlStore.setState({ runState: 'STOPPED' });
    useCartMapStore.setState({ isMoving: false, cartStatus: 'IDLE' });
  });

  it('멈출 것이 없으면 버튼을 잠근다', () => {
    const { result } = setup();

    expect(result.current.canStop).toBe(false);
  });

  it('추종 중이면 추종 종료만 보낸다', async () => {
    useCartControlStore.setState({ runState: 'FOLLOWING' });
    const { result } = setup();

    expect(result.current.canStop).toBe(true);
    act(() => result.current.stop());

    await waitFor(() => expect(sentRequests()).toEqual([`DELETE /api/carts/${CART_ID}/follow`]));
  });

  it('일시정지도 추종 세션이므로 종료 대상이다', async () => {
    useCartControlStore.setState({ runState: 'PAUSED' });
    const { result } = setup();

    expect(result.current.canStop).toBe(true);
    act(() => result.current.stop());

    await waitFor(() => expect(sentRequests()).toEqual([`DELETE /api/carts/${CART_ID}/follow`]));
  });

  it('목적지 이동 중이면 이동 취소만 보낸다', async () => {
    useCartMapStore.setState({ isMoving: true });
    const { result } = setup();

    expect(result.current.canStop).toBe(true);
    act(() => result.current.stop());

    await waitFor(() =>
      expect(sentRequests()).toEqual([`DELETE /api/carts/${CART_ID}/navigation`]),
    );
  });

  it('추종과 목적지 이동이 겹쳐 있으면 둘 다 보낸다', async () => {
    useCartControlStore.setState({ runState: 'FOLLOWING' });
    useCartMapStore.setState({ isMoving: true });
    const { result } = setup();

    act(() => result.current.stop());

    await waitFor(() =>
      expect(sentRequests().sort()).toEqual([
        `DELETE /api/carts/${CART_ID}/follow`,
        `DELETE /api/carts/${CART_ID}/navigation`,
      ]),
    );
  });

  it('명령을 둘 보내도 정지 안내는 한 번만 띄운다', async () => {
    useCartControlStore.setState({ runState: 'FOLLOWING' });
    useCartMapStore.setState({ isMoving: true });
    const { result } = setup();

    act(() => result.current.stop());

    await waitFor(() => expect(sentRequests()).toHaveLength(2));
    await waitFor(() => expect(stopNoticeCount()).toBe(1));
  });

  it('추종을 다시 시작한 뒤 또 멈추면 안내를 다시 띄운다', async () => {
    useCartControlStore.setState({ runState: 'FOLLOWING' });
    const { result } = setup();

    act(() => result.current.stop());
    await waitFor(() => expect(stopNoticeCount()).toBe(1));

    // 첫 정지로 runState가 STOPPED가 되어 멈출 것이 없어진다 — 추종을 다시 켜야 두 번째 정지가 성립한다
    act(() => useCartControlStore.setState({ runState: 'FOLLOWING' }));
    act(() => result.current.stop());

    await waitFor(() => expect(sentRequests()).toHaveLength(2));
    await waitFor(() => expect(stopNoticeCount()).toBe(2));
  });

  it('추종을 끊으면 위치에서 파생된 이동 중 표시도 바로 내린다', async () => {
    useCartControlStore.setState({ runState: 'FOLLOWING' });
    // 추종 중 위치 이벤트가 올려 둔 상태 — 정지 감지(3초)를 기다리지 않고 즉시 풀려야 한다
    useCartMapStore.setState({ cartStatus: 'MOVING', isMoving: false });
    const { result } = setup();

    act(() => result.current.stop());

    await waitFor(() => expect(useCartMapStore.getState().cartStatus).toBe('IDLE'));
    expect(useCartControlStore.getState().runState).toBe('STOPPED');
  });
});
