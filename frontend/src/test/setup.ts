import '@testing-library/jest-dom/vitest';

import { cleanup } from '@testing-library/react';
import { afterEach } from 'vitest';

// vitest 설정에 globals가 없어 testing-library의 자동 cleanup이 등록되지 않는다.
// 직접 걸어두지 않으면 렌더된 DOM이 테스트 간에 쌓여 getByText가 중복으로 잡힌다.
afterEach(() => {
  cleanup();
});

// antd 일부 컴포넌트(Grid, useBreakpoint 등)가 사용하는 matchMedia는 jsdom에 없어서 스텁 처리
if (typeof window !== 'undefined' && !window.matchMedia) {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    value: (query: string): MediaQueryList =>
      ({
        matches: false,
        media: query,
        onchange: null,
        addListener: () => {},
        removeListener: () => {},
        addEventListener: () => {},
        removeEventListener: () => {},
        dispatchEvent: () => false,
      }) as unknown as MediaQueryList,
  });
}
