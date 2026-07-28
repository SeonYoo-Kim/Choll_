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

  it('applyPosition은 좌표만 갱신한다', () => {
    useCartMapStore.getState().applyPosition({ x: 10, y: 20 });
    expect(useCartMapStore.getState().cartPosition).toEqual({ x: 10, y: 20 });
    expect(useCartMapStore.getState().cartZone).toBe(2);
  });

  it('applyZone은 새 구역 진입 시 그 인덱스를 반환한다', () => {
    const entered = useCartMapStore.getState().applyZone(5);
    expect(entered).toBe(4);
    expect(useCartMapStore.getState().cartZone).toBe(4);
  });

  it('applyZone은 같은 구역이면 null을 반환한다', () => {
    const entered = useCartMapStore.getState().applyZone(3);
    expect(entered).toBeNull();
    expect(useCartMapStore.getState().cartZone).toBe(2);
  });

  it('applyZone에 null(구역 이탈)이면 구역이 null이 되고 반환도 null이다', () => {
    const entered = useCartMapStore.getState().applyZone(null);
    expect(entered).toBeNull();
    expect(useCartMapStore.getState().cartZone).toBeNull();
  });

  it('applyNavigation(STARTED)은 이동 중으로 표시한다', () => {
    useCartMapStore.getState().applyNavigation('STARTED', 5);
    expect(useCartMapStore.getState().isMoving).toBe(true);
  });

  it('applyNavigation(ARRIVED)은 이동을 끝내고 목적지 구역으로 도착 모달을 연다', () => {
    useCartMapStore.getState().applyNavigation('STARTED', 1);
    useCartMapStore.getState().applyNavigation('ARRIVED', 1);
    const state = useCartMapStore.getState();
    expect(state.isMoving).toBe(false);
    expect(state.arrivalZone).toBe(0);
    expect(state.cartZone).toBe(0);
  });

  it('applyNavigation(CANCELLED)은 이동만 멈추고 모달은 열지 않는다', () => {
    useCartMapStore.getState().applyNavigation('STARTED', 1);
    useCartMapStore.getState().applyNavigation('CANCELLED');
    const state = useCartMapStore.getState();
    expect(state.isMoving).toBe(false);
    expect(state.arrivalZone).toBeNull();
  });

  it('syncFromCart는 전달된 필드만 갱신한다', () => {
    useCartMapStore.getState().syncFromCart({ zoneId: 4, isMoving: true });
    const state = useCartMapStore.getState();
    expect(state.cartZone).toBe(3);
    expect(state.isMoving).toBe(true);
    expect(state.cartPosition).toEqual(ZONE_POSITIONS[2]);
  });

  it('dismissArrival은 도착 모달을 닫는다', () => {
    useCartMapStore.getState().applyNavigation('ARRIVED', 1);
    useCartMapStore.getState().dismissArrival();
    expect(useCartMapStore.getState().arrivalZone).toBeNull();
  });
});
