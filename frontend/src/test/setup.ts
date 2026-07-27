import '@testing-library/jest-dom/vitest';

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
