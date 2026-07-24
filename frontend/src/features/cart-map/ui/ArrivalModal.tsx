import { Flag, X } from 'lucide-react';
import { useNavigate } from 'react-router';

import { useCartMapStore } from '../model/cartMapStore';
import { zoneLabel } from '../model/zones';

import type { Slot } from '@/shared/api/generated/model';
import { slotLabel } from '@/shared/lib/slotLabel';
import { useToastStore } from '@/shared/ui/toast/toastStore';

import styles from './ArrivalModal.module.scss';

interface ArrivalModalProps {
  /** 전체 슬롯 목록 — 도착 구역에 꽂을 책을 골라낸다 */
  slots: Slot[];
}

/** 구역 도착 시 표시되는 알림 모달. 해당 구역에 꽂을 책 슬롯을 보여준다. */
export function ArrivalModal({ slots }: ArrivalModalProps) {
  const { arrivalZone, dismissArrival } = useCartMapStore();
  const notify = useToastStore((state) => state.show);
  const navigate = useNavigate();

  if (arrivalZone === null) {
    return null;
  }

  const currentArea = zoneLabel(arrivalZone);
  const arrivalSlots = slots.filter((slot) => slot.book?.zone === currentArea);

  return (
    <div className={styles.backdrop}>
      <div className={styles.modal}>
        <button className={styles.close} onClick={dismissArrival} aria-label="닫기">
          <X size={16} />
        </button>
        <div className={styles.flag}>
          <Flag size={24} />
        </div>
        <p className={styles.overline}>ARRIVAL NOTICE</p>
        <h2 className={styles.title}>{currentArea}에 도착했어요!</h2>
        <p className={styles.desc}>
          이 구역에 꽂아야 할 책이 <strong>{arrivalSlots.length}권</strong> 있습니다.
          <br />
          빛나는 슬롯을 꺼내 서가에 꽂아주세요.
        </p>
        <div className={styles.slotGrid}>
          {arrivalSlots.map((slot) => (
            <div key={slot.slotNo} className={styles.slot}>
              <span className={styles.slotId}>SLOT {slotLabel(slot.slotNo)}</span>
              <p className={styles.slotTitle}>{slot.book?.title}</p>
              <span className={styles.ping} />
            </div>
          ))}
        </div>
        <div className={styles.actions}>
          <button
            className={styles.primary}
            onClick={() => {
              dismissArrival();
              navigate('/slots');
            }}
          >
            슬롯으로 확인하기
          </button>
          <button
            className={styles.secondary}
            onClick={() => {
              dismissArrival();
              notify(`${currentArea} 정리가 완료됐어요! 멋져요 🎉`);
            }}
          >
            이 구역 작업 끝
          </button>
        </div>
      </div>
    </div>
  );
}
