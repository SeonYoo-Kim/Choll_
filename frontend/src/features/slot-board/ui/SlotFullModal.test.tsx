import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router';
import { describe, expect, it } from 'vitest';

import { SlotFullModal } from './SlotFullModal';

import { SlotStatus } from '@/shared/api/generated/model';
import { getListSlotsQueryKey } from '@/shared/api/generated/slots/slots';
import { CART_FULL_THRESHOLD, DEMO_CART_ID, PHYSICAL_SLOT_COUNT } from '@/shared/config/cart';

import type { Slot } from '@/shared/api/generated/model';

const slot = (slotNumber: number, status: Slot['status']): Slot => ({
  id: slotNumber + 100,
  slotNumber,
  status,
  isTarget: false,
  lastDetectedAt: null,
  ...(status === SlotStatus.OCCUPIED && {
    book: { title: `책 ${slotNumber}` } as Slot['book'],
  }),
});

const fullSlots = (): Slot[] =>
  Array.from({ length: PHYSICAL_SLOT_COUNT }, (_, i) => slot(i + 1, SlotStatus.OCCUPIED));

/** 실물 슬롯 중 앞에서부터 count개만 찬 목록 (나머지는 빈 칸) */
const partiallyFullSlots = (count: number): Slot[] =>
  Array.from({ length: PHYSICAL_SLOT_COUNT }, (_, i) =>
    slot(i + 1, i < count ? SlotStatus.OCCUPIED : SlotStatus.EMPTY),
  );

/**
 * 슬롯 목록은 쿼리 캐시에서 읽으므로 캐시에 직접 심는다.
 * staleTime을 무한으로 두어 테스트 중 네트워크 재조회가 끼어들지 않게 한다.
 */
function renderModal(slots: Slot[]) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: 0, staleTime: Infinity } },
  });
  client.setQueryData(getListSlotsQueryKey(DEMO_CART_ID), slots);
  const view = render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <SlotFullModal />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  // TanStack v5는 구독자 알림을 setTimeout(0)으로 미룬다 — 매크로태스크까지 흘려보내야
  // 컴포넌트가 새 목록을 보고 다시 그린다. await만으로는(마이크로태스크) 리렌더가 일어나지 않는다.
  const setSlots = (next: Slot[]) =>
    act(async () => {
      client.setQueryData(getListSlotsQueryKey(DEMO_CART_ID), next);
      await new Promise((resolve) => setTimeout(resolve, 0));
    });
  return { ...view, setSlots };
}

const popup = () => screen.queryByRole('alertdialog');

describe('SlotFullModal', () => {
  it('임계값(4칸)만큼 차면 정리 요청 팝업을 띄운다', () => {
    renderModal(partiallyFullSlots(CART_FULL_THRESHOLD));
    expect(popup()).toBeInTheDocument();
    expect(screen.getByText('카트가 가득 찼어요')).toBeInTheDocument();
    expect(screen.getByText(/북카트를 정리해주세요/)).toBeInTheDocument();
  });

  it('임계값 미만이면 띄우지 않는다', () => {
    renderModal(partiallyFullSlots(CART_FULL_THRESHOLD - 1));
    expect(popup()).not.toBeInTheDocument();
  });

  it('빈 슬롯은 담긴 책 목록에 표시하지 않는다', () => {
    renderModal(partiallyFullSlots(CART_FULL_THRESHOLD));
    // 찬 4칸만 나열 — 빈 5번 슬롯이 "인식 중"으로 잘못 표시되면 안 된다
    expect(screen.getAllByRole('listitem')).toHaveLength(CART_FULL_THRESHOLD);
    expect(screen.queryByText('인식 중')).not.toBeInTheDocument();
  });

  it('담긴 책 목록을 슬롯 번호와 함께 보여준다', () => {
    renderModal(fullSlots());
    expect(screen.getByText('A-01')).toBeInTheDocument();
    expect(screen.getByText('책 1')).toBeInTheDocument();
  });

  it('책을 못 읽은 슬롯도 자리를 차지한 것으로 표시한다', () => {
    const slots = fullSlots();
    slots[0] = slot(1, SlotStatus.RECOGNITION_FAILED);
    renderModal(slots);
    expect(popup()).toBeInTheDocument();
    expect(screen.getByText('인식 실패')).toBeInTheDocument();
  });

  it('닫으면 사라지고, 같은 만적 상태에서는 다시 뜨지 않는다', async () => {
    const { setSlots } = renderModal(fullSlots());
    await userEvent.click(screen.getByRole('button', { name: '확인' }));
    expect(popup()).not.toBeInTheDocument();

    // 여전히 꽉 찬 목록이 다시 들어와도 조용히 있어야 한다
    await setSlots(fullSlots());
    expect(popup()).not.toBeInTheDocument();
  });

  /** 닫음 표시가 영구히 남으면 다음 만적을 놓친다 — 자리가 생기면 리셋돼야 한다 */
  it('책을 꺼내 자리가 생긴 뒤 다시 차면 또 띄운다', async () => {
    const { setSlots } = renderModal(fullSlots());
    await userEvent.click(screen.getByRole('button', { name: '확인' }));
    expect(popup()).not.toBeInTheDocument();

    // 임계값 아래로 내려가야 만적이 풀린다
    await setSlots(partiallyFullSlots(CART_FULL_THRESHOLD - 1));
    expect(popup()).not.toBeInTheDocument();

    await setSlots(fullSlots());
    expect(popup()).toBeInTheDocument();
  });
});
