import { useMemo, useState } from 'react';

import { useCartMapStore } from '@/features/cart-map/model/cartMapStore';
import { zoneLabel } from '@/features/cart-map/model/zones';
import { SlotDetailModal } from '@/features/slot-board/ui/SlotDetailModal';
import { SlotTile } from '@/features/slot-board/ui/SlotTile';
import type { Slot } from '@/shared/api/generated/model';
import { SlotStatus } from '@/shared/api/generated/model';
import { useListSlots } from '@/shared/api/generated/slots/slots';
import { DEMO_CART_ID } from '@/shared/config/cart';

import styles from './SlotsPage.module.scss';

type SlotFilter = 'all' | 'book' | 'empty' | 'error' | 'currentArea';

/** 슬롯 관리 — 30개 슬롯 보드 + 상태 필터 + 슬롯 상세. */
export function SlotsPage() {
  const { data: slots } = useListSlots(DEMO_CART_ID);
  const cartZone = useCartMapStore((state) => state.cartZone);
  const [filter, setFilter] = useState<SlotFilter>('all');
  const [selected, setSelected] = useState<Slot | null>(null);

  const allSlots = useMemo(() => slots ?? [], [slots]);
  const currentArea = zoneLabel(cartZone);

  const counts = useMemo(
    () => ({
      all: allSlots.length,
      book: allSlots.filter((s) => s.status === SlotStatus.OCCUPIED).length,
      empty: allSlots.filter((s) => s.status === SlotStatus.EMPTY).length,
      error: allSlots.filter((s) => s.status === SlotStatus.RECOGNITION_FAILED).length,
    }),
    [allSlots],
  );

  const filteredSlots = useMemo(() => {
    switch (filter) {
      case 'book':
        return allSlots.filter((s) => s.status === SlotStatus.OCCUPIED);
      case 'empty':
        return allSlots.filter((s) => s.status === SlotStatus.EMPTY);
      case 'error':
        return allSlots.filter((s) => s.status === SlotStatus.RECOGNITION_FAILED);
      case 'currentArea':
        return allSlots.filter((s) => s.book?.zone === currentArea);
      default:
        return allSlots;
    }
  }, [allSlots, filter, currentArea]);

  const filters: { id: SlotFilter; label: string }[] = [
    { id: 'all', label: `전체 ${counts.all}` },
    { id: 'book', label: `책 있음 ${counts.book}` },
    { id: 'empty', label: `비어 있음 ${counts.empty}` },
    { id: 'error', label: `인식 실패 ${counts.error}` },
    { id: 'currentArea', label: currentArea },
  ];

  return (
    <>
      <div className={styles.pageHeader}>
        <p className={styles.overline}>CART INVENTORY</p>
        <h1 className={styles.pageTitle}>슬롯 관리</h1>
        <p className={styles.pageDesc}>책이 어디에 있는지, 한눈에 찾아보세요.</p>
      </div>
      <div className={styles.filters}>
        {filters.map((f) => (
          <button
            key={f.id}
            onClick={() => setFilter(f.id)}
            aria-pressed={filter === f.id}
            className={`${styles.filterChip} ${filter === f.id ? styles.filterActive : ''}`}
          >
            {f.label}
          </button>
        ))}
      </div>
      <p className={styles.count}>{filteredSlots.length}개 슬롯을 보고 있어요.</p>
      <div className={styles.board}>
        {filteredSlots.map((slot) => (
          <SlotTile
            key={slot.slotNo}
            slot={slot}
            active={selected?.slotNo === slot.slotNo}
            onClick={() => setSelected(slot)}
          />
        ))}
      </div>
      {selected && <SlotDetailModal slot={selected} onClose={() => setSelected(null)} />}
    </>
  );
}
