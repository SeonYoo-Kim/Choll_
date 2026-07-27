import { Check, X } from 'lucide-react';

import type { Slot } from '@/shared/api/generated/model';
import { SlotStatus } from '@/shared/api/generated/model';
import { slotLabel } from '@/shared/lib/slotLabel';
import { useToastStore } from '@/shared/ui/toast/toastStore';

import styles from './SlotDetailModal.module.scss';

interface SlotDetailModalProps {
  slot: Slot;
  onClose: () => void;
}

/** 슬롯 클릭 시 표시되는 상세 모달 — 책 정보와 RFID 상태, 재인식 요청. */
export function SlotDetailModal({ slot, onClose }: SlotDetailModalProps) {
  const notify = useToastStore((state) => state.show);
  const isError = slot.status === SlotStatus.RECOGNITION_FAILED;

  return (
    <div className={styles.backdrop}>
      <div className={styles.modal}>
        <div className={styles.header}>
          <div>
            <span className={styles.slotId}>SLOT {slotLabel(slot.slotNumber)}</span>
            <h3 className={styles.title}>{slot.book?.title ?? '비어 있는 슬롯'}</h3>
          </div>
          <button className={styles.close} onClick={onClose} aria-label="닫기">
            <X size={16} />
          </button>
        </div>
        <div className={styles.info}>
          <p className={styles.row}>
            <span>저자</span>
            <strong>{slot.book?.author ?? '—'}</strong>
          </p>
          <p className={styles.row}>
            <span>목적 구역</span>
            <strong className={styles.zoneValue}>{slot.book?.zoneName ?? '—'}</strong>
          </p>
          <p className={styles.row}>
            <span>RFID 상태</span>
            <strong className={isError ? styles.errorValue : styles.zoneValue}>
              {isError ? '인식 실패' : '정상 인식'}
            </strong>
          </p>
        </div>
        <div className={styles.actions}>
          <button
            className={styles.primary}
            onClick={() => {
              notify('슬롯 비움 상태를 확인했어요');
              onClose();
            }}
          >
            <Check size={16} className={styles.checkIcon} />
            비움 확인됨
          </button>
          {isError && (
            <button className={styles.danger} onClick={() => notify('RFID 재인식을 요청했어요')}>
              재인식 요청
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
