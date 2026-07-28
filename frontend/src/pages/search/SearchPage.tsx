import { useMemo, useState } from 'react';

import { BookOpen, Search } from 'lucide-react';

import { SlotDetailModal } from '@/features/slot-board/ui/SlotDetailModal';
import type { Slot } from '@/shared/api/generated/model';
import { useListSlots } from '@/shared/api/generated/slots/slots';
import { DEMO_CART_ID } from '@/shared/config/cart';
import { slotLabel } from '@/shared/utils/slotLabel';

import styles from './SearchPage.module.scss';

/** 도서 검색 — 카트에 실린 책을 제목/도서 ID로 찾는다. */
export function SearchPage() {
  const { data: slots } = useListSlots(DEMO_CART_ID);
  const [query, setQuery] = useState('');
  const [selected, setSelected] = useState<Slot | null>(null);

  const results = useMemo(() => {
    const keyword = query.trim().toLowerCase();
    return (slots ?? []).filter((slot) => {
      if (!slot.book) {
        return false;
      }
      if (!keyword) {
        return true;
      }
      return (
        slot.book.title.toLowerCase().includes(keyword) ||
        slot.book.callNumber.toLowerCase().includes(keyword) ||
        (slot.book.rfidTagId ?? '').toLowerCase().includes(keyword)
      );
    });
  }, [slots, query]);

  return (
    <>
      <p className={styles.overline}>FIND A BOOK</p>
      <h1 className={styles.pageTitle}>도서 검색</h1>
      <p className={styles.pageDesc}>제목·청구기호·RFID 태그로 바로 찾을 수 있어요.</p>
      <div className={styles.searchBox}>
        <Search size={20} className={styles.searchIcon} />
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="예: 불편한 편의점, 813.7"
          className={styles.input}
        />
      </div>
      <div className={styles.results}>
        {results.length > 0 ? (
          results.map((slot) => (
            <button
              key={slot.slotNumber}
              className={styles.result}
              onClick={() => setSelected(slot)}
            >
              <span className={styles.bookIcon}>
                <BookOpen size={20} />
              </span>
              <div className={styles.bookInfo}>
                <p className={styles.bookTitle}>{slot.book?.title}</p>
                <p className={styles.bookMeta}>
                  {slot.book?.author} · {slot.book?.callNumber}
                </p>
              </div>
              <div className={styles.bookLocation}>
                <span className={styles.zoneBadge}>{slot.book?.zoneName}</span>
                <p className={styles.slotNo}>슬롯 {slotLabel(slot.slotNumber)}</p>
              </div>
            </button>
          ))
        ) : (
          <div className={styles.emptyResult}>찾으시는 책이 카트에 없어요.</div>
        )}
      </div>
      {selected && <SlotDetailModal slot={selected} onClose={() => setSelected(null)} />}
    </>
  );
}
