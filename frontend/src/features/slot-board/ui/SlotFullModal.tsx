import { PackageOpen, X } from 'lucide-react';
import { useState } from 'react';
import { useNavigate } from 'react-router';

import { isCartFull, physicalSlots } from '../model/slotCapacity';

import { SlotStatus } from '@/shared/api/generated/model';
import type { Slot } from '@/shared/api/generated/model';
import { useListSlots } from '@/shared/api/generated/slots/slots';
import { DEMO_CART_ID } from '@/shared/config/cart';
import { slotLabel } from '@/shared/utils/slotLabel';

import styles from './SlotFullModal.module.scss';

/**
 * 슬롯 만적 알림 팝업.
 *
 * AppLayout에 두어 어느 화면에서든 뜬다. 슬롯 목록은 WS SLOT_UPDATED로 실시간 갱신되는
 * 쿼리 캐시에서 오므로, RFID로 마지막 책이 얹히는 순간 저절로 열리고 한 권을 꺼내면 닫힌다.
 *
 * 전역 스토어(cartConnectionStore 같은)를 두지 않은 이유: "찼는지"는 슬롯 목록에서 그대로
 * 유도되는 값이라, 따로 보관하면 목록과 어긋날 여지만 생긴다.
 */
export function SlotFullModal() {
  const { data: slots } = useListSlots(DEMO_CART_ID);

  if (!isCartFull(slots ?? [])) {
    return null;
  }
  // 자리가 생기면 이 알림은 통째로 언마운트되고, 닫음 여부(안쪽 상태)도 함께 버려진다 —
  // 다시 꽉 차면 새로 마운트되어 알림이 살아난다 (ArrivalModal과 같은 방식)
  // 임계값(4칸) 기준이라 빈 슬롯이 남아 있을 수 있으니, 목록에는 책이 올라간 슬롯만 넘긴다
  return (
    <SlotFullNotice
      slots={physicalSlots(slots ?? []).filter((slot) => slot.status !== SlotStatus.EMPTY)}
    />
  );
}

/** 만적 임계값을 넘긴 동안 보여주는 정리 요청. 닫으면 그 만적이 풀릴 때까지 조용히 있는다. */
function SlotFullNotice({ slots }: { slots: Slot[] }) {
  const navigate = useNavigate();
  const [dismissed, setDismissed] = useState(false);

  if (dismissed) {
    return null;
  }

  return (
    <div className={styles.backdrop}>
      <div className={styles.modal} role="alertdialog" aria-labelledby="slot-full-title">
        <button className={styles.close} onClick={() => setDismissed(true)} aria-label="닫기">
          <X size={16} />
        </button>
        <div className={styles.icon}>
          <PackageOpen size={24} />
        </div>
        <p className={styles.overline}>CART FULL</p>
        <h2 className={styles.title} id="slot-full-title">
          카트가 가득 찼어요
        </h2>
        <p className={styles.desc}>
          슬롯 <strong>{slots.length}개</strong>에 책이 담겼습니다.
          <br />
          서가에 책을 꽂아 북카트를 정리해주세요.
        </p>
        <ul className={styles.slotList}>
          {slots.map((slot) => (
            <li key={slot.slotNumber} className={styles.slot}>
              <span className={styles.slotId}>{slotLabel(slot.slotNumber)}</span>
              <span className={styles.slotTitle}>
                {slot.book?.title ??
                  (slot.status === SlotStatus.RECOGNITION_FAILED ? '인식 실패' : '인식 중')}
              </span>
            </li>
          ))}
        </ul>
        <div className={styles.actions}>
          <button
            className={styles.primary}
            onClick={() => {
              setDismissed(true);
              navigate('/slots');
            }}
          >
            슬롯 확인하기
          </button>
          <button className={styles.secondary} onClick={() => setDismissed(true)}>
            확인
          </button>
        </div>
      </div>
    </div>
  );
}
