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
      slotNo: 3,
      status: SlotStatus.OCCUPIED,
      book: { bookId: 'BK-0003', title: '어린 왕자', author: '생텍쥐페리', zone: '2구역' },
    },
  },
};

export const Empty: Story = {
  args: {
    slot: { slotNo: 4, status: SlotStatus.EMPTY },
  },
};

export const RecognitionFailed: Story = {
  args: {
    slot: { slotNo: 11, status: SlotStatus.RECOGNITION_FAILED },
  },
};

export const Selected: Story = {
  args: {
    ...Occupied.args,
    active: true,
  },
};
