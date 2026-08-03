import { useQueryClient } from '@tanstack/react-query';
import { Check, X } from 'lucide-react';

import type { Slot } from '@/shared/api/generated/model';
import { SlotStatus } from '@/shared/api/generated/model';
import { getListSlotsQueryKey } from '@/shared/api/generated/slots/slots';
import { DEMO_CART_ID } from '@/shared/config/cart';
import { slotLabel } from '@/shared/utils/slotLabel';
import { useToastStore } from '@/shared/ui/toast/toastStore';

import styles from './SlotDetailModal.module.scss';

interface SlotDetailModalProps {
  slot: Slot;
  onClose: () => void;
}

/** 슬롯 클릭 시 표시되는 상세 모달 — 책 정보와 RFID 상태, 재인식 요청. */
export function SlotDetailModal({ slot, onClose }: SlotDetailModalProps) {
  const notify = useToastStore((state) => state.show);
  const queryClient = useQueryClient();
  const isError = slot.status === SlotStatus.RECOGNITION_FAILED;

  // 이 슬롯을 비움 처리 — 책을 서가에 옮긴 것으로 본다.
  // TODO: 비움 확인을 BE에 알릴지 명세 확정 필요 — 현재는 슬롯 캐시 갱신(데모)
  const confirmEmptied = () => {
    queryClient.setQueryData<Slot[]>(getListSlotsQueryKey(DEMO_CART_ID), (prev) =>
      prev?.map((item) =>
        item.slotNumber === slot.slotNumber
          ? { ...item, status: SlotStatus.EMPTY, isTarget: false, book: undefined }
          : item,
      ),
    );
    notify('슬롯을 비움으로 표시했어요');
    onClose();
  };

  return (
    <div
      className={styles.backdrop}
      // 모달 밖(배경)을 눌렀을 때만 닫는다 — 모달 내부 클릭은 버블링돼 올라와도
      // target이 currentTarget(배경)과 달라서 무시된다
      onClick={(event) => {
        if (event.target === event.currentTarget) {
          onClose();
        }
      }}
    >
      <div className={styles.modal}>
        <div className={styles.header}>
          <div>
            <span className={styles.slotId}>{slotLabel(slot.slotNumber)}</span>
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
          <button className={styles.primary} onClick={confirmEmptied}>
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
