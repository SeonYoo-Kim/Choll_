import type { Meta, StoryObj } from '@storybook/react-vite';

import { SlotStatus } from '@/shared/api/generated/model';

import { SlotCard } from './SlotCard';

const meta = {
  title: 'features/slot-board/SlotCard',
  component: SlotCard,
} satisfies Meta<typeof SlotCard>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Occupied: Story = {
  args: {
    slot: {
      slotNo: 1,
      status: SlotStatus.OCCUPIED,
      book: { bookId: 'BK-0001', title: '어린 왕자', zone: 'A-1' },
    },
  },
};

export const Empty: Story = {
  args: {
    slot: { slotNo: 3, status: SlotStatus.EMPTY },
  },
};

export const RecognitionFailed: Story = {
  args: {
    slot: { slotNo: 4, status: SlotStatus.RECOGNITION_FAILED },
  },
};
