import { useQueryClient } from '@tanstack/react-query';
import { Flag, X } from 'lucide-react';
import { useState } from 'react';
import { useNavigate } from 'react-router';

import { useCartMapStore } from '../model/cartMapStore';
import { zoneLabel } from '../model/zones';

import { SlotStatus } from '@/shared/api/generated/model';
import type { Slot } from '@/shared/api/generated/model';
import { getListSlotsQueryKey } from '@/shared/api/generated/slots/slots';
import { DEMO_CART_ID } from '@/shared/config/cart';
import { slotLabel } from '@/shared/utils/slotLabel';
import { useToastStore } from '@/shared/ui/toast/toastStore';

import styles from './ArrivalModal.module.scss';

interface ArrivalModalProps {
  /** 전체 슬롯 목록 — 도착 구역에 꽂을 책을 골라낸다 */
  slots: Slot[];
}

/**
 * 구역 도착 알림 모달의 껍데기.
 * 내용은 구역별로 key를 주어 마운트하므로, 구역이 바뀌면 안쪽 상태(도착 시점 권수)가 새로 잡힌다.
 */
export function ArrivalModal({ slots }: ArrivalModalProps) {
  const arrivalZone = useCartMapStore((state) => state.arrivalZone);

  if (arrivalZone === null) {
    return null;
  }
  return <ArrivalNotice key={arrivalZone} zone={arrivalZone} slots={slots} />;
}

/** 도착한 구역에 꽂을 책 슬롯을 보여준다. 책을 다 꺼내면 완료 문구로 바뀐다. */
function ArrivalNotice({ zone, slots }: { zone: number; slots: Slot[] }) {
  const dismissArrival = useCartMapStore((state) => state.dismissArrival);
  const notify = useToastStore((state) => state.show);
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const currentArea = zoneLabel(zone);
  // slots는 WS SLOT_UPDATED로 실시간 갱신되는 쿼리 캐시에서 온다 —
  // RFID로 책을 꺼낼 때마다 이 목록에서도 카드가 한 장씩 사라진다
  const arrivalSlots = slots.filter((slot) => slot.book?.zoneName === currentArea);

  // 도착 시점(= 이 컴포넌트 마운트 시점)의 권수. 처음부터 꽂을 책이 없던 구역에서는
  // 완료 문구를 띄우지 않기 위해 필요하다
  const [countOnArrival] = useState(arrivalSlots.length);
  const allShelved = countOnArrival > 0 && arrivalSlots.length === 0;

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
          {allShelved ? (
            <strong>책 정리가 완료되었습니다.</strong>
          ) : (
            <>
              이 구역에 꽂아야 할 책이 <strong>{arrivalSlots.length}권</strong> 있습니다.
              <br />
              빛나는 슬롯에서 책을 꺼내 서가에 꽂아주세요.
            </>
          )}
        </p>
        {arrivalSlots.length > 0 && (
          <div className={styles.slotGrid}>
            {arrivalSlots.map((slot) => (
              <div key={slot.slotNumber} className={styles.slot}>
                <span className={styles.slotId}>{slotLabel(slot.slotNumber)}</span>
                <p className={styles.slotTitle}>{slot.book?.title}</p>
                {slot.book?.bookshelfNumber && (
                  <span className={styles.slotShelf}>{slot.book.bookshelfNumber}</span>
                )}
                <span className={styles.ping} />
              </div>
            ))}
          </div>
        )}
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
              // 이 구역에 꽂을 책을 모두 서가에 옮긴 것으로 처리 — 해당 슬롯을 비운다.
              // TODO: 구역 완료를 BE에 알릴지 명세 확정 필요 — 현재는 슬롯 캐시 갱신(데모)
              queryClient.setQueryData<Slot[]>(getListSlotsQueryKey(DEMO_CART_ID), (prev) =>
                prev?.map((slot) =>
                  slot.book?.zoneName === currentArea
                    ? { ...slot, status: SlotStatus.EMPTY, isTarget: false, book: undefined }
                    : slot,
                ),
              );
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
