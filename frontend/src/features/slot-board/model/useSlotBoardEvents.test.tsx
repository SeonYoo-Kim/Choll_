import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { useSlotBoardEvents } from './useSlotBoardEvents';

import { SlotStatus } from '@/shared/api/generated/model';
import { getListSlotsQueryKey } from '@/shared/api/generated/slots/slots';
import { CartSocketContext } from '@/shared/api/ws/cartSocketContext';

import type { Slot } from '@/shared/api/generated/model';
import type { CartSocket, CartWsEvent, CartWsEventType } from '@/shared/api/ws/cartSocket';
import type { ReactNode } from 'react';

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

const emptySlot = (slotNumber: number): Slot => ({
  id: slotNumber,
  slotNumber,
  status: SlotStatus.EMPTY,
  isTarget: false,
  lastDetectedAt: null,
});

/** BE가 실제로 보내준 SLOT_UPDATED 샘플 (2026-07-30) */
const occupiedSlot1: Slot = {
  id: 1,
  slotNumber: 1,
  status: SlotStatus.OCCUPIED,
  isTarget: false,
  lastDetectedAt: '2026-07-30T16:59:23.026',
  book: {
    id: 143180,
    bookId: 112105,
    title: '초록 눈 코끼리',
    author: '강정연 글;백대승 그림',
    callNumber: '아 813.8-강74ㅊ',
    rfidTagId: null,
    bookshelfId: null,
    bookshelfNumber: null,
    shelfZoneId: null,
    zoneName: null,
  },
};

function setup(seed?: Slot[]) {
  const queryClient = new QueryClient();
  const socket = new FakeCartSocket();
  const queryKey = getListSlotsQueryKey(CART_ID);
  if (seed) {
    queryClient.setQueryData(queryKey, seed);
  }
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>
      <CartSocketContext.Provider value={socket as unknown as CartSocket}>
        {children}
      </CartSocketContext.Provider>
    </QueryClientProvider>
  );
  const view = renderHook(() => useSlotBoardEvents(CART_ID), { wrapper });
  return { queryClient, socket, queryKey, ...view };
}

describe('useSlotBoardEvents', () => {
  it('SLOT_UPDATED가 오면 해당 슬롯만 캐시에서 교체된다', () => {
    const { queryClient, socket, queryKey } = setup([emptySlot(1), emptySlot(2)]);

    socket.emit('SLOT_UPDATED', occupiedSlot1);

    const slots = queryClient.getQueryData<Slot[]>(queryKey);
    // setQueryData의 structural sharing이 새 객체를 만들므로 값으로 비교한다
    expect(slots?.[0]).toEqual(occupiedSlot1);
    expect(slots?.[0].book?.title).toBe('초록 눈 코끼리');
    expect(slots?.[1].status).toBe(SlotStatus.EMPTY);
  });

  it('캐시에 없는 슬롯이면 쿼리를 무효화해 서버 값으로 복구하게 한다', () => {
    const { queryClient, socket, queryKey } = setup([emptySlot(1)]);

    socket.emit('SLOT_UPDATED', { ...occupiedSlot1, slotNumber: 99 });

    expect(queryClient.getQueryState(queryKey)?.isInvalidated).toBe(true);
    // 캐시 자체는 손대지 않는다
    expect(queryClient.getQueryData<Slot[]>(queryKey)).toHaveLength(1);
  });

  it('언마운트하면 구독이 해제되어 캐시가 더 이상 갱신되지 않는다', () => {
    const { queryClient, socket, queryKey, unmount } = setup([emptySlot(1)]);

    unmount();
    socket.emit('SLOT_UPDATED', occupiedSlot1);

    expect(queryClient.getQueryData<Slot[]>(queryKey)?.[0].status).toBe(SlotStatus.EMPTY);
  });
});
