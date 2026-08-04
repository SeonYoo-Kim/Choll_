import { beforeEach, describe, expect, it } from 'vitest';

import { useCartConnectionStore } from './cartConnectionStore';

beforeEach(() => {
  useCartConnectionStore.setState({ online: true, lastSeenAt: null, dismissed: false });
});

describe('cartConnectionStore', () => {
  it('확인 전에는 연결된 것으로 본다 — 진입 직후 팝업이 번쩍이지 않게', () => {
    expect(useCartConnectionStore.getState().online).toBe(true);
  });

  it('끊기면 online이 false가 되고 마지막 통신 시각을 남긴다', () => {
    const recovered = useCartConnectionStore
      .getState()
      .applyConnection(false, '2026-08-03T21:12:33');

    expect(useCartConnectionStore.getState().online).toBe(false);
    expect(useCartConnectionStore.getState().lastSeenAt).toBe('2026-08-03T21:12:33');
    // 끊긴 것은 복구가 아니다
    expect(recovered).toBe(false);
  });

  it('끊겼다가 다시 붙을 때만 복구로 알린다', () => {
    useCartConnectionStore.getState().applyConnection(false, null);
    expect(useCartConnectionStore.getState().applyConnection(true, null)).toBe(true);
  });

  it('붙어 있는 상태에서 온 online 이벤트는 복구가 아니다', () => {
    expect(useCartConnectionStore.getState().applyConnection(true, null)).toBe(false);
  });

  it('닫은 팝업은 같은 끊김 동안 다시 뜨지 않는다', () => {
    useCartConnectionStore.getState().applyConnection(false, null);
    useCartConnectionStore.getState().dismiss();
    expect(useCartConnectionStore.getState().dismissed).toBe(true);

    // 끊긴 상태로 같은 값이 또 와도 닫은 상태를 유지한다
    useCartConnectionStore.getState().applyConnection(false, null);
    expect(useCartConnectionStore.getState().dismissed).toBe(true);
  });

  it('복구 뒤 다시 끊기면 팝업이 새로 뜬다', () => {
    useCartConnectionStore.getState().applyConnection(false, null);
    useCartConnectionStore.getState().dismiss();

    useCartConnectionStore.getState().applyConnection(true, null);
    useCartConnectionStore.getState().applyConnection(false, null);

    expect(useCartConnectionStore.getState().dismissed).toBe(false);
  });

  it('시각을 안 주면 이전 값을 유지한다', () => {
    useCartConnectionStore.getState().applyConnection(false, '2026-08-03T21:12:33');
    useCartConnectionStore.getState().applyConnection(true);
    expect(useCartConnectionStore.getState().lastSeenAt).toBe('2026-08-03T21:12:33');
  });
});
