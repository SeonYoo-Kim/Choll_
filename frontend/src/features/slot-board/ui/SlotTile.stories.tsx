import type { Meta, StoryObj } from '@storybook/react-vite';

import { SlotStatus } from '@/shared/api/generated/model';

import { SlotTile } from './SlotTile';

const meta = {
  title: 'features/slot-board/SlotTile',
  component: SlotTile,
} satisfies Meta<typeof SlotTile>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Occupied: Story = {
  args: {
    slot: {
      id: 103,
      slotNumber: 3,
      status: SlotStatus.OCCUPIED,
      isTarget: false,
      book: {
        id: 3,
        title: '어린 왕자',
        author: '생텍쥐페리',
        callNumber: '863-생884ㅇ',
        rfidTagId: 'E200-3412-DC03-0003',
        shelfZoneId: 2,
        zoneName: '2구역',
      },
    },
  },
};

export const Empty: Story = {
  args: {
    slot: { id: 104, slotNumber: 4, status: SlotStatus.EMPTY, isTarget: false },
  },
};

export const RecognitionFailed: Story = {
  args: {
    slot: { id: 111, slotNumber: 11, status: SlotStatus.RECOGNITION_FAILED, isTarget: false },
  },
};

export const Selected: Story = {
  args: {
    ...Occupied.args,
    active: true,
  },
};
