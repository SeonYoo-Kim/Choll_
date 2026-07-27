import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { SlotStatus } from '@/shared/api/generated/model';

import { SlotTile } from './SlotTile';

describe('SlotTile', () => {
  it('책이 있는 슬롯은 라벨·제목·저자·구역을 표시한다', () => {
    render(
      <SlotTile
        slot={{
          id: 103,
          slotNumber: 3,
          status: SlotStatus.OCCUPIED,
          isTarget: false,
          lastDetectedAt: null,
          book: {
            id: 3,
            bookId: 3,
            title: '어린 왕자',
            author: '생텍쥐페리',
            callNumber: '863-생884ㅇ',
            rfidTagId: 'E200-3412-DC03-0003',
            bookshelfId: 2,
            bookshelfNumber: '800',
            shelfZoneId: 2,
            zoneName: '2구역',
          },
        }}
      />,
    );

    expect(screen.getByText('A-03')).toBeInTheDocument();
    expect(screen.getByText('어린 왕자')).toBeInTheDocument();
    expect(screen.getByText('생텍쥐페리')).toBeInTheDocument();
    expect(screen.getByText('2구역')).toBeInTheDocument();
  });

  it('빈 슬롯은 안내 문구를 표시한다', () => {
    render(
      <SlotTile
        slot={{
          id: 104,
          slotNumber: 4,
          status: SlotStatus.EMPTY,
          isTarget: false,
          lastDetectedAt: null,
        }}
      />,
    );

    expect(screen.getByText('비어 있는 슬롯')).toBeInTheDocument();
    expect(screen.getByText('다음 책을 꽂아주세요')).toBeInTheDocument();
  });

  it('인식 실패 슬롯은 RFID 오류 문구를 표시한다', () => {
    render(
      <SlotTile
        slot={{
          id: 111,
          slotNumber: 11,
          status: SlotStatus.RECOGNITION_FAILED,
          isTarget: false,
          lastDetectedAt: null,
        }}
      />,
    );

    expect(screen.getByText('RFID를 읽을 수 없어요')).toBeInTheDocument();
    expect(screen.getByText('태그 상태를 확인해 주세요')).toBeInTheDocument();
  });
});
