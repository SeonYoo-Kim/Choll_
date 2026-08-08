import { beforeEach, describe, expect, it } from 'vitest';

import { useCartControlStore } from './cartControlStore';

describe('cartControlStore', () => {
  beforeEach(() => {
    useCartControlStore.setState({ runState: 'STOPPED' });
  });

  it('초기 상태는 정지다', () => {
    expect(useCartControlStore.getState().runState).toBe('STOPPED');
  });

  it('setRunState로 운행 상태를 갱신한다', () => {
    useCartControlStore.getState().setRunState('FOLLOWING');
    expect(useCartControlStore.getState().runState).toBe('FOLLOWING');
  });

  it('applyFollowStatus는 추종 상태를 운행 상태로 매핑한다', () => {
    const { applyFollowStatus } = useCartControlStore.getState();

    applyFollowStatus('STARTED');
    expect(useCartControlStore.getState().runState).toBe('FOLLOWING');

    applyFollowStatus('PAUSED');
    expect(useCartControlStore.getState().runState).toBe('PAUSED');

    applyFollowStatus('STOPPED');
    expect(useCartControlStore.getState().runState).toBe('STOPPED');
  });
});
