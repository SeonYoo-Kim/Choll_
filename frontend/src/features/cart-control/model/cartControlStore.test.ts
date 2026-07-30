import { beforeEach, describe, expect, it } from 'vitest';

import { useCartControlStore } from './cartControlStore';

describe('cartControlStore', () => {
  beforeEach(() => {
    useCartControlStore.setState({ runState: 'STOPPED', connected: false });
  });

  it('초기 상태는 정지 + 미연결이다', () => {
    const { runState, connected } = useCartControlStore.getState();
    expect(runState).toBe('STOPPED');
    expect(connected).toBe(false);
  });

  it('setRunState로 운행 상태를 갱신한다', () => {
    useCartControlStore.getState().setRunState('FOLLOWING');
    expect(useCartControlStore.getState().runState).toBe('FOLLOWING');
  });

  it('setConnected로 WS 연결 상태를 갱신한다', () => {
    useCartControlStore.getState().setConnected(true);
    expect(useCartControlStore.getState().connected).toBe(true);
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
