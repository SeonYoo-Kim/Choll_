import { useMemo, useState } from 'react';

import { useCartMapStore } from '@/features/cart-map/model/cartMapStore';
import { zoneLabel } from '@/features/cart-map/model/zones';
import { SlotDetailModal } from '@/features/slot-board/ui/SlotDetailModal';
import { SlotTile } from '@/features/slot-board/ui/SlotTile';
import { SlotStatus } from '@/shared/api/generated/model';
import { useListSlots } from '@/shared/api/generated/slots/slots';
import { DEMO_CART_ID } from '@/shared/config/cart';

import styles from './SlotsPage.module.scss';

type SlotFilter = 'all' | 'book' | 'empty' | 'error' | 'currentArea';

/** 슬롯 관리 — 12개 슬롯 보드 + 상태 필터 + 슬롯 상세. */
export function SlotsPage() {
  const { data: slots } = useListSlots(DEMO_CART_ID);
  const cartZone = useCartMapStore((state) => state.cartZone);
  const [filter, setFilter] = useState<SlotFilter>('all');
  const [selectedSlotNumber, setSelectedSlotNumber] = useState<number | null>(null);

  const allSlots = useMemo(() => slots ?? [], [slots]);
  // cartZone null = 통로·출발 지점(어느 구역도 아님). zoneLabel에 그냥 넘기면 "1구역"이 되어 거짓말을 한다
  // 선택 슬롯은 번호로만 기억하고 내용은 항상 최신 목록에서 찾는다 — WS 갱신이 모달에도 반영되게
  const selected = allSlots.find((s) => s.slotNumber === selectedSlotNumber) ?? null;
  const currentArea = cartZone === null ? null : zoneLabel(cartZone);
  // 구역을 벗어나면 현재 구역 필터가 성립하지 않으므로 전체로 간주한다
  const effectiveFilter: SlotFilter =
    filter === 'currentArea' && currentArea === null ? 'all' : filter;

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
    switch (effectiveFilter) {
      case 'book':
        return allSlots.filter((s) => s.status === SlotStatus.OCCUPIED);
      case 'empty':
        return allSlots.filter((s) => s.status === SlotStatus.EMPTY);
      case 'error':
        return allSlots.filter((s) => s.status === SlotStatus.RECOGNITION_FAILED);
      case 'currentArea':
        // currentArea가 null이면 zoneName이 없는 책들이 걸리므로 비교하지 않는다
        return currentArea === null
          ? allSlots
          : allSlots.filter((s) => s.book?.zoneName === currentArea);
      default:
        return allSlots;
    }
  }, [allSlots, effectiveFilter, currentArea]);

  const filters: { id: SlotFilter; label: string }[] = [
    { id: 'all', label: `전체 ${counts.all}` },
    { id: 'book', label: `책 있음 ${counts.book}` },
    { id: 'empty', label: `비어 있음 ${counts.empty}` },
    { id: 'error', label: `인식 실패 ${counts.error}` },
    // 구역 밖에서는 현재 구역 필터가 의미 없으므로 칩을 감춘다
    ...(currentArea === null ? [] : [{ id: 'currentArea' as const, label: currentArea }]),
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
            aria-pressed={effectiveFilter === f.id}
            className={`${styles.filterChip} ${effectiveFilter === f.id ? styles.filterActive : ''}`}
          >
            {f.label}
          </button>
        ))}
      </div>
      <div className={styles.board}>
        {filteredSlots.map((slot) => (
          <SlotTile
            key={slot.slotNumber}
            slot={slot}
            active={selectedSlotNumber === slot.slotNumber}
            onSelect={setSelectedSlotNumber}
          />
        ))}
      </div>
      {selected && <SlotDetailModal slot={selected} onClose={() => setSelectedSlotNumber(null)} />}
    </>
  );
}
