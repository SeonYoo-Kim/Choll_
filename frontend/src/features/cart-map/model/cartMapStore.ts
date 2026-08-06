import { create } from 'zustand';

import { unwrapAngle } from './angle';
import { START_POSITION } from './zones';
import { zoneIndexOf, zoneIndexOfPoint } from './zoneStore';

import type { MapPercent } from './mapTransform';
import type { CartDetailStatus, MapInfo } from '@/shared/api/generated/model';
import type { NavigationStatus } from '@/shared/api/ws/cartSocket';

/** 이동 중으로 취급하는 이동 상태 (접수·시작) */
const MOVING_STATUSES: readonly NavigationStatus[] = ['ACCEPTED', 'STARTED'];

/** 연속 위치 이벤트를 "움직임"으로 판정할 최소 이동 거리 (% 좌표 기준) */
const MOVE_EPSILON_PERCENT = 0.2;

/**
 * 위치 이벤트 간격 추정치 — 지도에서 카트를 다음 좌표까지 몇 ms에 걸쳐 옮길지에 쓴다.
 * 고정값으로 두면 발행 주기와 어긋나 "잠깐 미끄러지고 멈추기"를 반복하므로 실제 간격을 따라간다.
 */
const DEFAULT_POSITION_INTERVAL_MS = 1_000;
const MIN_POSITION_INTERVAL_MS = 150;
const MAX_POSITION_INTERVAL_MS = 2_000;
/** 간격 평활 계수 — 한 번 늦게 온 이벤트가 애니메이션 속도를 크게 흔들지 않게 한다 */
const INTERVAL_SMOOTHING = 0.3;
/** 간격을 이 단위로 반올림한다 — 매번 미세하게 달라져 불필요한 리렌더가 나는 것을 막는다 */
const INTERVAL_STEP_MS = 50;

function smoothInterval(previousMs: number, gapMs: number): number {
  // 한참 멈춰 있다가 다시 출발한 경우 — 그 공백까지 주기로 치면 다음 구간이
  // 몇 초에 걸쳐 느릿하게 움직인다. 이런 값은 섞지 않고 기존 추정치를 유지한다.
  if (gapMs > MAX_POSITION_INTERVAL_MS) {
    return previousMs;
  }
  const blended = previousMs * (1 - INTERVAL_SMOOTHING) + gapMs * INTERVAL_SMOOTHING;
  const clamped = Math.min(Math.max(blended, MIN_POSITION_INTERVAL_MS), MAX_POSITION_INTERVAL_MS);
  return Math.round(clamped / INTERVAL_STEP_MS) * INTERVAL_STEP_MS;
}

/** applyPosition이 위치에서 파생해 알려주는 결과 (진입 알림·정지 감지용) */
export interface PositionApplied {
  /** 직전 좌표에서 의미 있게 움직였는지 */
  moved: boolean;
  /** 새 구역에 진입했으면 그 인덱스(0-base), 아니면 null */
  enteredZone: number | null;
}

interface CartMapState {
  /** 카트가 있는 구역 인덱스 (0-base, 구역 밖이면 null) */
  cartZone: number | null;
  /** 지도 위 카트 좌표 (%) */
  cartPosition: MapPercent;
  /**
   * 지도 이미지 기준 카트 방향각 (라디안).
   * BE가 주는 -π..π 값을 그대로 담지 않고 짧은 쪽으로 누적한 연속값이다(angle.ts 참조).
   */
  cartYaw: number;
  /** 위치 이벤트 간격 추정치 (ms) — 지도에서 카트를 옮기는 애니메이션 길이로 쓴다 */
  positionIntervalMs: number;
  /** 마지막 위치 이벤트 수신 시각 (ms) — 간격 추정용 내부 값 */
  lastPositionAt: number | null;
  /** 카트 동작 상태 (CART-01 응답 CartStatus: IDLE·MOVING·FOLLOWING·ERROR) */
  cartStatus: CartDetailStatus;
  /** 마지막으로 수신한 목적지 이동 상태 (WS-FE-06, 이동 명령 전이면 null) */
  navStatus: NavigationStatus | null;
  /** cartStatus가 MOVING인지의 편의 플래그 */
  isMoving: boolean;
  /** 도착 알림 모달에 표시할 구역 인덱스 (null이면 닫힘) */
  arrivalZone: number | null;
  /**
   * 서버가 준 지도 정보 (MAP-01). 아직 못 받았으면 null.
   *
   * **좌표계의 기준**이다 — imageWidth·imageHeight로 화면의 % 좌표와 BE 지도 픽셀을 서로 바꾼다
   * (WS 카트 위치를 그림 위에 얹을 때, 클릭 지점을 NAV-01에 실어 보낼 때).
   * 응답의 `imageUrl`은 쓰지 않는다 — 바탕 그림은 번들 평면도다(floorPlanImage.ts 참조).
   */
  mapInfo: MapInfo | null;
  /**
   * 지도를 쓸 수 없는 상태 (MAP-01 조회 실패).
   * 좌표 기준이 없으면 카트 위치도 목적지도 뜻이 없으므로 화면은 에러로 넘긴다.
   */
  mapUnavailable: boolean;
  /** MAP-01 조회 결과 반영 — mapInfo가 undefined이고 isError도 false면 아직 불러오는 중이다 */
  applyMapInfo: (mapInfo: MapInfo | undefined, isError: boolean) => void;
  /** 이동 명령(NAV-01) 접수 성공 시 낙관적 표시 — WS 이벤트 도착 전 버튼 잠금용 */
  startMove: () => void;
  /**
   * WS CART_POSITION_UPDATE(WS-FE-01) 반영.
   * 좌표에서 현재 구역을 판정하고, 좌표가 움직이면 대기 상태를 이동 중으로 올린다
   * (BE 테스트 발행기처럼 위치만 오는 환경에서도 구역·상태가 실시간 갱신되도록).
   */
  applyPosition: (position: MapPercent, yaw: number) => PositionApplied;
  /** 위치 변화가 멎었을 때 호출 — 위치 파생 이동 중 상태를 대기로 되돌린다 */
  markStationary: () => void;
  /** WS CURRENT_ZONE_UPDATED(WS-FE-05) 반영. 새 구역에 진입했으면 그 인덱스를 반환(진입 알림용) */
  applyZone: (currentZoneId: number | null) => number | null;
  /** WS NAVIGATION_STATUS_UPDATED(WS-FE-06) 반영 — ARRIVED면 도착 모달을 연다 */
  applyNavigation: (status: NavigationStatus, destinationZoneId?: number) => void;
  /** 워치독 발동 시 이동 상태 강제 리셋 — 이후 REST 재조회(syncFromCart)로 실제 상태를 복구한다 */
  abortMove: () => void;
  /** REST 재조회(초기 진입·재연결) 결과로 상태 동기화 */
  syncFromCart: (params: {
    position?: MapPercent;
    zoneId?: number | null;
    status?: CartDetailStatus;
  }) => void;
  dismissArrival: () => void;
}

/**
 * 지도 화면의 카트 위치/이동 상태 스토어.
 * 상태 변경은 REST 응답과 WS 이벤트(useCartMapEvents)로만 일어난다.
 * 개발 중 이동 시뮬레이션은 MSW 계층(shared/api/mocks/cartSimulator.ts)에 있다.
 */
export const useCartMapStore = create<CartMapState>()((set, get) => ({
  cartZone: null,
  cartPosition: START_POSITION,
  cartYaw: 0,
  positionIntervalMs: DEFAULT_POSITION_INTERVAL_MS,
  lastPositionAt: null,
  cartStatus: 'IDLE',
  navStatus: null,
  isMoving: false,
  arrivalZone: null,
  mapInfo: null,
  mapUnavailable: false,
  applyMapInfo: (mapInfo, isError) =>
    set({
      mapInfo: mapInfo ?? null,
      // 조회가 실패하면 좌표 기준이 없다. mapInfo가 undefined면 아직 응답 전이므로 실패로 보지 않는다
      mapUnavailable: isError,
    }),
  startMove: () => set({ isMoving: true, cartStatus: 'MOVING', navStatus: 'ACCEPTED' }),
  applyPosition: (position, yaw) => {
    const state = get();
    const now = Date.now();
    const positionIntervalMs =
      state.lastPositionAt === null
        ? state.positionIntervalMs
        : smoothInterval(state.positionIntervalMs, now - state.lastPositionAt);

    // yaw가 없거나 NaN이면(모킹·구버전 BE) 이전 방향을 유지한다 —
    // 그대로 넣으면 rotate(NaNrad)가 되어 회전이 통째로 무시된다
    const cartYaw = Number.isFinite(yaw) ? unwrapAngle(state.cartYaw, yaw) : state.cartYaw;
    const zone = zoneIndexOfPoint(position);

    // 카트가 멈춰 있으면 같은 좌표가 주기마다 계속 온다 — 바뀐 게 없으면 화면을 다시 그리지 않는다
    const unchanged =
      position.x === state.cartPosition.x &&
      position.y === state.cartPosition.y &&
      cartYaw === state.cartYaw &&
      zone === state.cartZone;
    if (unchanged) {
      set({ lastPositionAt: now, positionIntervalMs });
      return { moved: false, enteredZone: null };
    }

    const moved =
      Math.hypot(position.x - state.cartPosition.x, position.y - state.cartPosition.y) >
      MOVE_EPSILON_PERCENT;
    const enteredZone = zone !== null && zone !== state.cartZone ? zone : null;
    set({
      cartPosition: position,
      cartYaw,
      cartZone: zone,
      lastPositionAt: now,
      positionIntervalMs,
      // 추종(FOLLOWING) 등 다른 상태는 유지하고, 대기 중일 때만 이동 중으로 올린다
      ...(moved && !state.isMoving && state.cartStatus === 'IDLE' && { cartStatus: 'MOVING' }),
    });
    return { moved, enteredZone };
  },
  markStationary: () =>
    set((state) =>
      // 이동 명령 세션(isMoving)은 워치독·이동 이벤트가 관리하므로 건드리지 않는다
      state.cartStatus === 'MOVING' && !state.isMoving ? { cartStatus: 'IDLE' } : {},
    ),
  applyZone: (currentZoneId) => {
    const previousZone = get().cartZone;
    const zone = currentZoneId === null ? null : zoneIndexOf(currentZoneId);
    set({ cartZone: zone });
    return zone !== null && zone !== previousZone ? zone : null;
  },
  applyNavigation: (status, destinationZoneId) => {
    if (MOVING_STATUSES.includes(status)) {
      set({ navStatus: status, isMoving: true, cartStatus: 'MOVING' });
      return;
    }
    if (status === 'ARRIVED') {
      const zone =
        destinationZoneId === undefined ? get().cartZone : zoneIndexOf(destinationZoneId);
      set({
        navStatus: status,
        isMoving: false,
        cartStatus: 'IDLE',
        ...(zone !== null && { cartZone: zone, arrivalZone: zone }),
      });
      return;
    }
    // STOPPED · CANCELLED · FAILED — 이동만 끝나고 카트는 대기 상태로 돌아간다
    set({ navStatus: status, isMoving: false, cartStatus: 'IDLE' });
  },
  abortMove: () => set({ isMoving: false, cartStatus: 'IDLE', navStatus: null }),
  syncFromCart: ({ position, zoneId, status }) =>
    set((state) => ({
      cartPosition: position ?? state.cartPosition,
      cartZone:
        zoneId === undefined ? state.cartZone : zoneId === null ? null : zoneIndexOf(zoneId),
      cartStatus: status ?? state.cartStatus,
      isMoving: status === undefined ? state.isMoving : status === 'MOVING',
    })),
  dismissArrival: () => set({ arrivalZone: null }),
}));
