import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { useCartMapStore } from './cartMapStore';
import { ZONE_CODES, ZONE_POSITIONS } from './zones';
import { useZoneStore } from './zoneStore';

import type { ShelfZone } from '@/shared/api/generated/model';

/** 서버 구역 응답 흉내 — 구역 id는 1·2·3, 코드 순서는 평면도와 같다 */
const serverZones: ShelfZone[] = ZONE_CODES.map((code, index) => ({
  id: index + 1,
  mapId: 2,
  code,
  name: `${code} 서버 이름`,
  boundaryData: '[[0,0],[10,0],[10,10],[0,10]]',
}));

/** 어느 구역에도 속하지 않는 지점 — 구역 위쪽 여백(사서 테이블 아래 통로) */
const OUTSIDE_ZONES = { x: 50, y: 10 };

beforeEach(() => {
  // 구역에 서버 id가 채워져 있어야 zoneId↔인덱스 변환이 동작한다
  useZoneStore.getState().applyServerZones(serverZones);
  useCartMapStore.setState({
    cartZone: 2,
    cartPosition: ZONE_POSITIONS[2],
    cartYaw: 0,
    positionIntervalMs: 1_000,
    lastPositionAt: null,
    cartStatus: 'IDLE',
    navStatus: null,
    isMoving: false,
    arrivalZone: null,
  });
});

afterEach(() => {
  vi.useRealTimers();
  useZoneStore.getState().resetZones();
});

describe('cartMapStore', () => {
  it('startMove는 이동 중 상태로 만든다', () => {
    useCartMapStore.getState().startMove();
    const state = useCartMapStore.getState();
    expect(state.isMoving).toBe(true);
    expect(state.cartStatus).toBe('MOVING');
    expect(state.navStatus).toBe('ACCEPTED');
  });

  it('applyPosition은 좌표·방향각을 갱신하고 좌표로 현재 구역을 판정한다', () => {
    // Z3(인덱스 2)에 있던 카트가 Z1(인덱스 0) 안으로 들어온 상황
    useCartMapStore.getState().applyPosition(ZONE_POSITIONS[0], 1.57);
    const state = useCartMapStore.getState();
    expect(state.cartPosition).toEqual(ZONE_POSITIONS[0]);
    // cartYaw는 짧은 쪽으로 누적한 값이라 부동소수 오차가 섞인다 (angle.ts 참조)
    expect(state.cartYaw).toBeCloseTo(1.57);
    expect(state.cartZone).toBe(0);
  });

  it('applyPosition은 구역 밖 좌표(통로)면 구역을 null로 만든다', () => {
    useCartMapStore.getState().applyPosition(OUTSIDE_ZONES, 0);
    expect(useCartMapStore.getState().cartZone).toBeNull();
  });

  it('applyPosition은 좌표가 움직이면 대기 상태를 이동 중으로 올린다', () => {
    const moved = useCartMapStore.getState().applyPosition(ZONE_POSITIONS[0], 0);
    expect(moved).toBe(true);
    expect(useCartMapStore.getState().cartStatus).toBe('MOVING');
  });

  it('applyPosition은 같은 좌표(정지)면 상태를 올리지 않는다', () => {
    const moved = useCartMapStore.getState().applyPosition(ZONE_POSITIONS[2], 0);
    expect(moved).toBe(false);
    expect(useCartMapStore.getState().cartStatus).toBe('IDLE');
  });

  it('applyPosition은 yaw가 π를 넘어가도 짧은 쪽으로 누적한다', () => {
    useCartMapStore.setState({ cartYaw: 3.1 });

    // BE는 -π..π로 접어서 준다 — 실제로는 0.08rad만 움직인 상황
    useCartMapStore.getState().applyPosition(ZONE_POSITIONS[0], -3.1);

    const yaw = useCartMapStore.getState().cartYaw;
    expect(Math.abs(yaw - 3.1)).toBeLessThan(0.1);
  });

  it('applyPosition은 yaw가 없으면 이전 방향을 유지한다', () => {
    useCartMapStore.setState({ cartYaw: 1.2 });

    // 모킹·구버전 BE가 yaw를 빼고 보내는 경우 (그대로 넣으면 rotate(NaNrad)로 회전이 죽는다)
    useCartMapStore.getState().applyPosition(ZONE_POSITIONS[0], undefined as unknown as number);

    expect(useCartMapStore.getState().cartYaw).toBe(1.2);
  });

  it('applyPosition은 값이 그대로면 좌표 참조를 유지한다 (정지 중 리렌더 방지)', () => {
    const before = useCartMapStore.getState().cartPosition;

    // 값은 같고 객체만 새로 만들어 보낸다 — 멈춰 있는 카트가 주기마다 같은 좌표를 보내는 상황
    useCartMapStore.getState().applyPosition({ ...before }, 0);

    expect(useCartMapStore.getState().cartPosition).toBe(before);
  });

  it('applyPosition은 연속 이벤트 간격을 애니메이션 길이로 반영한다', () => {
    vi.useFakeTimers();
    vi.setSystemTime(0);
    useCartMapStore.getState().applyPosition({ x: 78, y: 30 }, 0);
    vi.setSystemTime(300);

    useCartMapStore.getState().applyPosition({ x: 78, y: 34 }, 0);

    // 기본값 1000ms에서 실제 간격(300ms) 쪽으로 당겨진다
    const interval = useCartMapStore.getState().positionIntervalMs;
    expect(interval).toBeLessThan(1_000);
    expect(interval).toBeGreaterThanOrEqual(150);
  });

  it('applyPosition은 오래 멈췄다 다시 움직인 공백을 주기로 착각하지 않는다', () => {
    vi.useFakeTimers();
    vi.setSystemTime(0);
    useCartMapStore.getState().applyPosition({ x: 78, y: 30 }, 0);
    vi.setSystemTime(300);
    useCartMapStore.getState().applyPosition({ x: 78, y: 34 }, 0);
    const beforeIdle = useCartMapStore.getState().positionIntervalMs;

    // 30초 정지 후 재출발 — 이 공백이 섞이면 다음 구간이 느려터지게 보인다
    vi.setSystemTime(30_300);
    useCartMapStore.getState().applyPosition({ x: 78, y: 38 }, 0);

    expect(useCartMapStore.getState().positionIntervalMs).toBe(beforeIdle);
  });

  it('applyPosition은 추종 중 상태를 이동 중으로 덮지 않는다', () => {
    useCartMapStore.setState({ cartStatus: 'FOLLOWING' });
    useCartMapStore.getState().applyPosition(ZONE_POSITIONS[0], 0);
    expect(useCartMapStore.getState().cartStatus).toBe('FOLLOWING');
  });

  it('markStationary는 위치 파생 이동 중 상태만 대기로 되돌린다', () => {
    useCartMapStore.getState().applyPosition(ZONE_POSITIONS[0], 0);
    useCartMapStore.getState().markStationary();
    expect(useCartMapStore.getState().cartStatus).toBe('IDLE');

    // 이동 명령 세션 중(isMoving)에는 건드리지 않는다
    useCartMapStore.getState().startMove();
    useCartMapStore.getState().markStationary();
    expect(useCartMapStore.getState().cartStatus).toBe('MOVING');
  });

  it('applyZone은 서버 구역 id를 인덱스로 바꿔 담는다', () => {
    useCartMapStore.getState().applyZone(1);
    expect(useCartMapStore.getState().cartZone).toBe(0);
  });

  it('applyZone에 목록에 없는 id가 오면 구역이 null이 된다', () => {
    useCartMapStore.getState().applyZone(999);
    expect(useCartMapStore.getState().cartZone).toBeNull();
  });

  it('applyZone에 null(구역 이탈)이면 구역이 null이 된다', () => {
    useCartMapStore.getState().applyZone(null);
    expect(useCartMapStore.getState().cartZone).toBeNull();
  });

  it('applyNavigation(STARTED)은 이동 중으로 표시한다', () => {
    useCartMapStore.getState().applyNavigation('STARTED', 1);
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
    expect(state.navStatus).toBe('CANCELLED');
    expect(state.arrivalZone).toBeNull();
  });

  it('applyNavigation(FAILED)은 이동을 멈추고 실패 상태를 기록한다', () => {
    useCartMapStore.getState().applyNavigation('STARTED', 1);
    useCartMapStore.getState().applyNavigation('FAILED');
    const state = useCartMapStore.getState();
    expect(state.isMoving).toBe(false);
    expect(state.cartStatus).toBe('IDLE');
    expect(state.navStatus).toBe('FAILED');
  });

  it('syncFromCart는 전달된 필드만 갱신하고 status로 isMoving을 유도한다', () => {
    useCartMapStore.getState().syncFromCart({ zoneId: 2, status: 'FOLLOWING' });
    const state = useCartMapStore.getState();
    expect(state.cartZone).toBe(1);
    expect(state.cartStatus).toBe('FOLLOWING');
    expect(state.isMoving).toBe(false);
    expect(state.cartPosition).toEqual(ZONE_POSITIONS[2]);
  });

  it('abortMove(워치독)는 이동 상태를 대기로 리셋한다', () => {
    useCartMapStore.getState().startMove();
    useCartMapStore.getState().abortMove();
    const state = useCartMapStore.getState();
    expect(state.isMoving).toBe(false);
    expect(state.cartStatus).toBe('IDLE');
    expect(state.navStatus).toBeNull();
  });

  it('dismissArrival은 도착 모달을 닫는다', () => {
    useCartMapStore.getState().applyNavigation('ARRIVED', 1);
    useCartMapStore.getState().dismissArrival();
    expect(useCartMapStore.getState().arrivalZone).toBeNull();
  });
});
