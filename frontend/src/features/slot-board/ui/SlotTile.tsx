import type { Slot } from '@/shared/api/generated/model';
import { SlotStatus } from '@/shared/api/generated/model';
import { slotLabel } from '@/shared/utils/slotLabel';

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
  const title = isError ? 'RFID 인식 불가' : (slot.book?.title ?? '비어 있는 슬롯');
  // 에러 타일은 부제 없이 표시 (빈 문자열로 두어 타일 높이 구조는 유지)
  const subtitle = isError ? '' : (slot.book?.author ?? '다음 책을 꽂아주세요');

  return (
    <button
      onClick={onClick}
      className={`${styles.tile} ${STATUS_CLASS[slot.status] ?? styles.empty} ${active ? styles.active : ''}`}
    >
      <span className={styles.id}>{slotLabel(slot.slotNumber)}</span>
      <p className={styles.title}>{title}</p>
      <p className={styles.subtitle}>{subtitle}</p>
      {slot.book?.zoneName && <span className={styles.zone}>{slot.book.zoneName}</span>}
    </button>
  );
}
