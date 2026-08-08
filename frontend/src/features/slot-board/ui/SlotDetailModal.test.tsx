import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { SlotDetailModal } from './SlotDetailModal';

import { SlotStatus } from '@/shared/api/generated/model';

import type { Slot } from '@/shared/api/generated/model';

const EMPTY_SLOT: Slot = {
  id: 1,
  slotNumber: 1,
  status: SlotStatus.EMPTY,
  isTarget: false,
  lastDetectedAt: null,
};

const OCCUPIED_SLOT: Slot = {
  id: 2,
  slotNumber: 2,
  status: SlotStatus.OCCUPIED,
  isTarget: true,
  lastDetectedAt: '2026-08-04T09:00:00',
  book: { title: '어린 왕자', author: '생텍쥐페리', zoneName: '언어·문학' } as Slot['book'],
};

function renderModal(slot: Slot) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: 0 } } });
  return render(
    <QueryClientProvider client={client}>
      <SlotDetailModal slot={slot} onClose={vi.fn()} />
    </QueryClientProvider>,
  );
}

describe('SlotDetailModal', () => {
  /** 빈 슬롯에는 비울 것이 없다 — 눌러도 아무 일이 없는 버튼을 보여주면 안 된다 */
  it('빈 슬롯이면 비움 확인 버튼을 숨긴다', () => {
    renderModal(EMPTY_SLOT);
    expect(screen.queryByRole('button', { name: /비움 확인/ })).not.toBeInTheDocument();
  });

  it('책이 있는 슬롯에는 비움 확인 버튼을 보여준다', () => {
    renderModal(OCCUPIED_SLOT);
    expect(screen.getByRole('button', { name: /비움 확인/ })).toBeInTheDocument();
  });

  it('빈 슬롯도 상세 정보와 닫기는 그대로 보여준다', () => {
    renderModal(EMPTY_SLOT);
    expect(screen.getByText('비어 있는 슬롯')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '닫기' })).toBeInTheDocument();
  });
});
