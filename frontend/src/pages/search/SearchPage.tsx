import { useMemo, useRef, useState } from 'react';

import { BookOpen, Search, X } from 'lucide-react';

import { useBookSearchStore } from '@/features/book-search/model/bookSearchStore';
import { SlotDetailModal } from '@/features/slot-board/ui/SlotDetailModal';
import type { Slot } from '@/shared/api/generated/model';
import { useListSlots } from '@/shared/api/generated/slots/slots';
import { DEMO_CART_ID } from '@/shared/config/cart';
import { slotLabel } from '@/shared/utils/slotLabel';

import styles from './SearchPage.module.scss';

/** 도서 검색 — 카트에 실린 책을 제목/도서 ID로 찾는다. */
export function SearchPage() {
  const { data: slots } = useListSlots(DEMO_CART_ID);
  // 검색어는 전역 스토어에 둔다 — 탭 이동·뒤로가기로 이 페이지가 언마운트돼도 유지된다
  const query = useBookSearchStore((state) => state.query);
  const setQuery = useBookSearchStore((state) => state.setQuery);
  const clearQuery = useBookSearchStore((state) => state.clearQuery);
  const [selected, setSelected] = useState<Slot | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // 검색어를 아직 안 쳤으면 "없어요"는 거짓말이다 — 안 찾아본 것과 찾았는데 없는 것은 다르다
  const searching = query.trim() !== '';

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
      <p className={styles.pageDesc}>제목·청구기호로 바로 찾을 수 있어요.</p>
      <div className={styles.searchBox}>
        <Search size={20} className={styles.searchIcon} />
        <input
          ref={inputRef}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="예: 불편한 편의점, 813.7"
          className={styles.input}
        />
        {/* 입력이 있을 때만 노출 — 빈 검색창에 지우기 버튼이 떠 있으면 혼란스럽다 */}
        {query !== '' && (
          <button
            type="button"
            className={styles.clear}
            aria-label="검색어 지우기"
            onClick={() => {
              clearQuery();
              inputRef.current?.focus(); // 지운 뒤 바로 다시 입력할 수 있게
            }}
          >
            <X size={16} />
          </button>
        )}
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
          searching && <div className={styles.emptyResult}>찾으시는 책이 카트에 없어요.</div>
        )}
      </div>
      {selected && <SlotDetailModal slot={selected} onClose={() => setSelected(null)} />}
    </>
  );
}
