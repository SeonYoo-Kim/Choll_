import { beforeEach, describe, expect, it } from 'vitest';

import { useCartMapStore } from './cartMapStore';
import { ZONE_POSITIONS } from './zones';

beforeEach(() => {
  useCartMapStore.setState({
    cartZone: 2,
    cartPosition: ZONE_POSITIONS[2],
    isMoving: false,
    arrivalZone: null,
  });
});

describe('cartMapStore', () => {
  it('startMove는 isMoving을 켠다', () => {
    useCartMapStore.getState().startMove();
    expect(useCartMapStore.getState().isMoving).toBe(true);
  });

  it('applyPosition은 좌표를 갱신하고, 구역이 바뀌면 새 구역 인덱스를 반환한다', () => {
    const entered = useCartMapStore.getState().applyPosition({ x: 10, y: 20 }, 5);
    expect(entered).toBe(4);
    expect(useCartMapStore.getState().cartPosition).toEqual({ x: 10, y: 20 });
    expect(useCartMapStore.getState().cartZone).toBe(4);
  });

  it('applyPosition은 같은 구역 안 이동이면 null을 반환한다', () => {
    const entered = useCartMapStore.getState().applyPosition({ x: 10, y: 20 }, 3);
    expect(entered).toBeNull();
    expect(useCartMapStore.getState().cartZone).toBe(2);
  });

  it('applyPosition에 zoneId null(통로)이면 구역도 null이 된다', () => {
    const entered = useCartMapStore.getState().applyPosition({ x: 10, y: 47 }, null);
    expect(entered).toBeNull();
    expect(useCartMapStore.getState().cartZone).toBeNull();
  });

  it('applyArrival은 이동을 끝내고 도착 모달 구역을 연다', () => {
    useCartMapStore.getState().startMove();
    useCartMapStore.getState().applyArrival(1);
    const state = useCartMapStore.getState();
    expect(state.isMoving).toBe(false);
    expect(state.arrivalZone).toBe(0);
    expect(state.cartZone).toBe(0);
  });

  it('syncFromCart는 전달된 필드만 갱신한다', () => {
    useCartMapStore.getState().syncFromCart({ zoneId: 4, isMoving: true });
    const state = useCartMapStore.getState();
    expect(state.cartZone).toBe(3);
    expect(state.isMoving).toBe(true);
    expect(state.cartPosition).toEqual(ZONE_POSITIONS[2]);
  });

  it('dismissArrival은 도착 모달을 닫는다', () => {
    useCartMapStore.getState().applyArrival(1);
    useCartMapStore.getState().dismissArrival();
    expect(useCartMapStore.getState().arrivalZone).toBeNull();
  });
});
