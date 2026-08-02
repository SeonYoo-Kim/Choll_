import { create } from 'zustand';

interface BookSearchState {
  /** 도서 검색어 */
  query: string;
  setQuery: (query: string) => void;
  clearQuery: () => void;
}

/**
 * 도서 검색어 스토어.
 *
 * 페이지 로컬 state로 두면 다른 탭으로 이동하거나 뒤로가기 할 때 SearchPage가
 * 언마운트되면서 입력이 날아간다. 화면 밖(전역)에 둬서 세션 동안 유지한다.
 */
export const useBookSearchStore = create<BookSearchState>()((set) => ({
  query: '',
  setQuery: (query) => set({ query }),
  clearQuery: () => set({ query: '' }),
}));
