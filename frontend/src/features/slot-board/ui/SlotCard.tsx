import { Card, Tag, Typography } from 'antd';

import type { Slot } from '@/shared/api/generated/model';
import { SlotStatus } from '@/shared/api/generated/model';

import styles from './SlotCard.module.scss';

const STATUS_LABEL: Record<string, string> = {
  [SlotStatus.EMPTY]: '비어 있음',
  [SlotStatus.OCCUPIED]: '책 있음',
  [SlotStatus.RECOGNITION_FAILED]: '인식 실패',
};

const STATUS_TAG_COLOR: Record<string, string> = {
  [SlotStatus.EMPTY]: 'default',
  [SlotStatus.OCCUPIED]: 'green',
  [SlotStatus.RECOGNITION_FAILED]: 'red',
};

interface SlotCardProps {
  slot: Slot;
}

/** 슬롯 상태 보드의 개별 슬롯 카드. 상태별 색상 스트라이프 + 책 정보를 표시한다. */
export function SlotCard({ slot }: SlotCardProps) {
  const statusClass =
    slot.status === SlotStatus.OCCUPIED
      ? styles.occupied
      : slot.status === SlotStatus.RECOGNITION_FAILED
        ? styles.failed
        : styles.empty;

  return (
    <Card size="small" className={`${styles.card} ${statusClass}`}>
      <div className={styles.header}>
        <Typography.Text strong>슬롯 {slot.slotNo}</Typography.Text>
        <Tag color={STATUS_TAG_COLOR[slot.status]}>{STATUS_LABEL[slot.status] ?? slot.status}</Tag>
      </div>
      {slot.book ? (
        <div className={styles.book}>
          <Typography.Text ellipsis>{slot.book.title}</Typography.Text>
          <Typography.Text type="secondary">
            {slot.book.zone} · {slot.book.bookId}
          </Typography.Text>
        </div>
      ) : (
        <Typography.Text type="secondary">—</Typography.Text>
      )}
    </Card>
  );
}
