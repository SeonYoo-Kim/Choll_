import type { Slot } from '@/shared/api/generated/model';
import { SlotStatus } from '@/shared/api/generated/model';
import { slotLabel } from '@/shared/lib/slotLabel';

import styles from './SlotTile.module.scss';

const STATUS_CLASS: Record<string, string> = {
  [SlotStatus.OCCUPIED]: styles.book,
  [SlotStatus.EMPTY]: styles.empty,
  [SlotStatus.RECOGNITION_FAILED]: styles.error,
};

interface SlotTileProps {
  slot: Slot;
  active?: boolean;
  onClick?: () => void;
}

/** 슬롯 보드의 개별 슬롯 타일. 상태별 톤 + 책 정보(제목·저자·구역)를 표시한다. */
export function SlotTile({ slot, active = false, onClick }: SlotTileProps) {
  const isError = slot.status === SlotStatus.RECOGNITION_FAILED;
  const title = isError ? 'RFID를 읽을 수 없어요' : (slot.book?.title ?? '비어 있는 슬롯');
  const subtitle = isError
    ? '태그 상태를 확인해 주세요'
    : (slot.book?.author ?? '다음 책을 꽂아주세요');

  return (
    <button
      onClick={onClick}
      className={`${styles.tile} ${STATUS_CLASS[slot.status] ?? styles.empty} ${active ? styles.active : ''}`}
    >
      <span className={styles.id}>{slotLabel(slot.slotNo)}</span>
      <p className={styles.title}>{title}</p>
      <p className={styles.subtitle}>{subtitle}</p>
      {slot.book?.zone && <span className={styles.zone}>{slot.book.zone}</span>}
    </button>
  );
}
