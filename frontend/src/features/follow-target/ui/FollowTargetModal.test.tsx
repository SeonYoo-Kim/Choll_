import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { FollowTargetModal } from './FollowTargetModal';

import { CartSocketContext } from '@/shared/api/ws/cartSocketContext';

import type { AxiosRequestConfig } from 'axios';
import type {
  CartSocket,
  CartWsEvent,
  CartWsEventType,
  TracksUpdatedPayload,
} from '@/shared/api/ws/cartSocket';

const { httpMock } = vi.hoisted(() => ({ httpMock: vi.fn() }));
vi.mock('@/shared/api/http', () => ({ http: httpMock }));

const CART_ID = 1;

/** CartSocket의 on/구독 해제 계약만 흉내 내는 테스트 대역 */
class FakeCartSocket {
  private handlers = new Map<CartWsEventType, Set<(event: CartWsEvent) => void>>();

  on<TPayload>(type: CartWsEventType, handler: (event: CartWsEvent<TPayload>) => void): () => void {
    const set = this.handlers.get(type) ?? new Set();
    set.add(handler as (event: CartWsEvent) => void);
    this.handlers.set(type, set);
    return () => {
      set.delete(handler as (event: CartWsEvent) => void);
    };
  }

  emit(type: CartWsEventType, payload: unknown): void {
    this.handlers.get(type)?.forEach((handler) => handler({ type, payload }));
  }
}

/**
 * 영상 채널 대역 — jsdom이 실제 연결을 시도하지 않도록 막는다.
 * 마지막 인스턴스를 보관해서 테스트가 연결 성공(onopen)을 직접 일으킬 수 있게 한다.
 */
class StubWebSocket {
  static last: StubWebSocket | null = null;
  binaryType = '';
  onopen: (() => void) | null = null;
  onmessage: ((event: MessageEvent) => void) | null = null;
  onclose: (() => void) | null = null;

  constructor() {
    StubWebSocket.last = this;
  }

  close(): void {}
}

const originalWebSocket = globalThis.WebSocket;

/** 영상 소켓이 열린 상태로 만든다 — "연결 중" 안내를 지나 실제 화면을 보게 된다 */
function connectVideo(): void {
  act(() => StubWebSocket.last?.onopen?.());
}

/** 640×480 영상 기준 — 좌상단에서 10% 지점의 20%×50% 크기 박스 */
const tracksPayload: TracksUpdatedPayload = {
  image_width: 640,
  image_height: 480,
  tracks: [
    { id: 3, x: 64, y: 48, w: 128, h: 240 },
    { id: 7, x: 320, y: 96, w: 96, h: 192 },
  ],
};

function setup() {
  const queryClient = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
  const socket = new FakeCartSocket();
  const onSelected = vi.fn();
  const onClose = vi.fn();

  render(
    <QueryClientProvider client={queryClient}>
      <CartSocketContext.Provider value={socket as unknown as CartSocket}>
        <FollowTargetModal cartId={CART_ID} onClose={onClose} onSelected={onSelected} />
      </CartSocketContext.Provider>
    </QueryClientProvider>,
  );

  return { socket, onSelected, onClose };
}

describe('FollowTargetModal', () => {
  beforeEach(() => {
    globalThis.WebSocket = StubWebSocket as unknown as typeof WebSocket;
    httpMock.mockReset();
    httpMock.mockImplementation((config: AxiosRequestConfig<{ trackId: number }>) =>
      Promise.resolve({ trackId: config.data?.trackId, status: 'SENT' }),
    );
  });

  afterEach(() => {
    globalThis.WebSocket = originalWebSocket;
  });

  it('영상이 붙기 전에는 카메라 연결 중이라고 안내한다', () => {
    setup();

    expect(screen.getByText(/카메라를 연결하는 중이에요/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /추종 대상으로 선택/ })).not.toBeInTheDocument();
  });

  it('영상은 붙었지만 아직 TRACKS_UPDATED가 없으면 사람을 찾는 중이라고 안내한다', () => {
    setup();

    connectVideo();

    expect(screen.getByText(/사람을 찾는 중이에요/)).toBeInTheDocument();
  });

  it('track마다 박스를 그리고, 좌표를 영상 해상도 기준 %로 변환한다', () => {
    const { socket } = setup();

    act(() => socket.emit('TRACKS_UPDATED', tracksPayload));

    const boxes = screen.getAllByRole('button', { name: /추종 대상으로 선택/ });
    expect(boxes).toHaveLength(2);
    // 64/640 = 10%, 48/480 = 10%, 128/640 = 20%, 240/480 = 50%
    expect(boxes[0]).toHaveStyle({ left: '10%', top: '10%', width: '20%', height: '50%' });
    expect(screen.getByText('ID 3')).toBeInTheDocument();
    expect(screen.getByText('ID 7')).toBeInTheDocument();
  });

  it('박스를 누르면 그 trackId로 선택 요청을 보내고 onSelected로 알린다', async () => {
    const { socket, onSelected } = setup();
    act(() => socket.emit('TRACKS_UPDATED', tracksPayload));

    await act(async () => {
      screen.getByRole('button', { name: '7번 사람을 추종 대상으로 선택' }).click();
    });

    expect(httpMock).toHaveBeenCalledWith(
      expect.objectContaining({
        url: `/api/carts/${CART_ID}/follow/target`,
        method: 'POST',
        data: { trackId: 7 },
      }),
    );
    expect(onSelected).toHaveBeenCalledWith(7);
  });

  it('영상은 나오는데 탐지된 사람이 없으면 박스 대신 그 사실을 알려준다', () => {
    const { socket } = setup();
    connectVideo();

    act(() => socket.emit('TRACKS_UPDATED', { ...tracksPayload, tracks: [] }));

    expect(screen.queryByRole('button', { name: /추종 대상으로 선택/ })).not.toBeInTheDocument();
    expect(screen.getByText('카메라에 잡히는 사람이 없어요')).toBeInTheDocument();
  });
});
