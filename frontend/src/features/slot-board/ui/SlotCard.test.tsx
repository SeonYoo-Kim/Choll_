import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { SlotStatus } from '@/shared/api/generated/model';

import { SlotCard } from './SlotCard';

describe('SlotCard', () => {
  it('책이 있는 슬롯은 책 제목과 구역을 표시한다', () => {
    render(
      <SlotCard
        slot={{
          slotNo: 1,
          status: SlotStatus.OCCUPIED,
          book: { bookId: 'BK-0001', title: '어린 왕자', zone: 'A-1' },
        }}
      />,
    );

    expect(screen.getByText('슬롯 1')).toBeInTheDocument();
    expect(screen.getByText('책 있음')).toBeInTheDocument();
    expect(screen.getByText('어린 왕자')).toBeInTheDocument();
    expect(screen.getByText('A-1 · BK-0001')).toBeInTheDocument();
  });

  it('빈 슬롯은 "비어 있음" 상태를 표시한다', () => {
    render(<SlotCard slot={{ slotNo: 3, status: SlotStatus.EMPTY }} />);

    expect(screen.getByText('비어 있음')).toBeInTheDocument();
  });
});
