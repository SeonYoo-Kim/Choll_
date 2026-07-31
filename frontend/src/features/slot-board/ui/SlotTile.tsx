import type { Slot } from '@/shared/api/generated/model';
import { SlotStatus } from '@/shared/api/generated/model';
import { slotLabel } from '@/shared/utils/slotLabel';
import { memo } from 'react';

import styles from './SlotTile.module.scss';

const STATUS_CLASS: Record<string, string> = {
  [SlotStatus.OCCUPIED]: styles.book,
  [SlotStatus.EMPTY]: styles.empty,
  [SlotStatus.RECOGNITION_FAILED]: styles.error,
};

interface SlotTileProps {
  slot: Slot;
  active?: boolean;
  /** 타일 클릭 시 슬롯 번호를 알려준다 — 부모가 함수 하나를 모든 타일에 공유할 수 있게 */
  onSelect?: (slotNumber: number) => void;
}

/** 슬롯 보드의 개별 슬롯 타일. 상태별 톤 + 책 정보(제목·저자·구역)를 표시한다.
 *  memo: props가 그대로인 타일은 리렌더를 건너뛴다 — slot 참조 보존은 slotCache.replaceSlot이 담당. */
export const SlotTile = memo(function SlotTile({ slot, active = false, onSelect }: SlotTileProps) {
  const isError = slot.status === SlotStatus.RECOGNITION_FAILED;
  const title = isError ? 'RFID 인식 불가' : (slot.book?.title ?? '비어 있는 슬롯');
  // 부제는 책의 저자만 표시 (빈/에러 슬롯은 빈 문자열로 두어 타일 높이 구조는 유지)
  const subtitle = slot.book?.author ?? '';

  return (
    <button
      onClick={() => onSelect?.(slot.slotNumber)}
      className={`${styles.tile} ${STATUS_CLASS[slot.status] ?? styles.empty} ${active ? styles.active : ''}`}
    >
      <span className={styles.id}>{slotLabel(slot.slotNumber)}</span>
      <p className={styles.title}>{title}</p>
      <p className={styles.subtitle}>{subtitle}</p>
      {slot.book?.zoneName && (
        <span className={styles.zone}>
          {slot.book.zoneName}
          {slot.book.bookshelfNumber && ` · ${slot.book.bookshelfNumber}`}
        </span>
      )}
    </button>
  );
});
