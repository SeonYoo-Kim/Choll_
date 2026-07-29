import { ws } from 'msw';

import { percentToDisplay } from '@/features/cart-map/model/mapTransform';
import {
  CORRIDOR_Y,
  START_POSITION,
  ZONE_POSITIONS,
  zoneIndexOf,
} from '@/features/cart-map/model/zones';
import { CartDetailStatus } from '@/shared/api/generated/model';

import type { MapPercent } from '@/features/cart-map/model/mapTransform';
import type { CartDetail, MapInfo } from '@/shared/api/generated/model';
import type { CartWsEvent, FollowStatus, NavigationStatus } from '@/shared/api/ws/cartSocket';

/**
 * 개발용 카트 이동 시뮬레이터 (가짜 BE).
 * REST NAV-01(이동 시작) 모킹 핸들러가 startCartMove를 호출하면, 실제 BE처럼
 * WS로 CART_POSITION_UPDATE(WS-FE-01)·CURRENT_ZONE_UPDATED(WS-FE-05)·
 * NAVIGATION_STATUS_UPDATED(WS-FE-06)를 브로드캐스트한다.
 * 구역 좌표는 FE 지도 픽스처(zones.ts)를 재사용해 화면과 항상 일치시킨다.
 */

/** 지도 메타 픽스처 — 시뮬레이터가 %↔표시 좌표(px) 변환에 쓰는 기준값 */
export const mapInfoFixture: MapInfo = {
  id: 1,
  name: '우리 도서관 1층',
  imageUrl: '/map.png',
  resolution: 0.05,
  originX: 0,
  originY: 0,
  imageWidth: 1174,
  imageHeight: 631,
};

// 주의: 'ws://*/...'처럼 호스트가 와일드카드인 절대 URL 패턴은 브라우저의 URL 해석 과정에서
// 매칭이 깨진다(msw 2.15 기준). '*'로 시작하는 패턴은 해석을 건너뛰므로 안전하다.
const cartWsLink = ws.link('*/ws/carts/*');

/** WS 연결 인터셉트 핸들러 — 등록만 해도 실서버 연결 시도(무한 재시도)를 막는다 */
export const cartWsHandler = cartWsLink.addEventListener('connection', () => {});

const STEP_MS = 340;

/** 현재 구역 인덱스 (null = 출발 지점 대기 — 이동·추종으로 움직이기 전 초기 상태) */
let currentZoneIndex: number | null = null;
let isMoving = false;
let navigationCounter = 0;
let moveTimers: ReturnType<typeof setTimeout>[] = [];

function broadcast(event: CartWsEvent): void {
  cartWsLink.broadcast(JSON.stringify(event));
}

function broadcastPosition(percent: MapPercent): void {
  const { x, y } = percentToDisplay(percent, mapInfoFixture);
  broadcast({
    type: 'CART_POSITION_UPDATE',
    payload: { mapId: mapInfoFixture.id, x, y, valid: true },
  });
}

function broadcastZone(previousZoneId: number | null, currentZoneId: number | null): void {
  broadcast({ type: 'CURRENT_ZONE_UPDATED', payload: { previousZoneId, currentZoneId } });
}

function broadcastNavigation(status: NavigationStatus, destinationZoneId?: number): void {
  broadcast({
    type: 'NAVIGATION_STATUS_UPDATED',
    payload: { navigationId: navigationCounter, status, destinationZoneId },
  });
}

/** NAV-01 목적지 이동 시작 — 구역 이탈 → 통로 경유 → 목적지 진입 → 도착 순서로 브로드캐스트 */
export function startCartMove(zoneId: number): void {
  const destinationIndex = zoneIndexOf(zoneId);
  if (destinationIndex === null || isMoving || destinationIndex === currentZoneIndex) {
    return;
  }
  isMoving = true;
  navigationCounter += 1;
  const departureZoneId = currentZoneIndex === null ? null : currentZoneIndex + 1;
  const start = currentZoneIndex === null ? START_POSITION : ZONE_POSITIONS[currentZoneIndex];
  const destination = ZONE_POSITIONS[destinationIndex];

  broadcastNavigation('ACCEPTED', zoneId);
  const waypoints: MapPercent[] = [
    { x: start.x, y: CORRIDOR_Y },
    { x: destination.x, y: CORRIDOR_Y },
    destination,
  ];
  moveTimers.push(
    setTimeout(() => {
      broadcastNavigation('STARTED', zoneId);
      broadcastZone(departureZoneId, null); // 출발 구역 이탈 → 통로
      broadcastPosition(waypoints[0]);
    }, 30),
    setTimeout(() => broadcastPosition(waypoints[1]), STEP_MS + 30),
    setTimeout(() => {
      broadcastZone(null, zoneId); // 목적지 구역 진입
      broadcastPosition(waypoints[2]);
    }, STEP_MS * 2 + 30),
    setTimeout(
      () => {
        currentZoneIndex = destinationIndex;
        isMoving = false;
        moveTimers = [];
        broadcastNavigation('ARRIVED', zoneId);
      },
      STEP_MS * 3 + 60,
    ),
  );
}

/** 추종 상태 (추종 명령 모킹용) */
let followStatus: FollowStatus = 'STOPPED';

function broadcastFollow(status: FollowStatus): void {
  followStatus = status;
  broadcast({ type: 'FOLLOW_STATUS_UPDATED', payload: { status } });
}

/** 추종 시작(또는 재개) — 실제 BE처럼 WS FOLLOW_STATUS_UPDATED(WS-FE-07)를 브로드캐스트 */
export function startCartFollow(): void {
  broadcastFollow('STARTED');
}

/** 추종 일시정지 — 추종 중일 때만 유효 */
export function pauseCartFollow(): void {
  if (followStatus === 'STARTED') {
    broadcastFollow('PAUSED');
  }
}

/** 추종 종료 */
export function stopCartFollow(): void {
  if (followStatus !== 'STOPPED') {
    broadcastFollow('STOPPED');
  }
}

/** NAV-02 목적지 이동 취소 — 예약된 브로드캐스트를 모두 취소하고 CANCELLED를 알린다 */
export function stopCartMove(): void {
  moveTimers.forEach(clearTimeout);
  moveTimers = [];
  if (isMoving) {
    isMoving = false;
    broadcastNavigation('CANCELLED');
  }
}

/** 시뮬레이터 상태를 반영한 카트 상세 픽스처 (CART-01 getCart 모킹 응답) */
export function cartDetailFixture(cartId: number): CartDetail {
  return {
    id: cartId,
    name: '쫄래쫄래 1호',
    status: isMoving
      ? CartDetailStatus.MOVING
      : followStatus === 'STARTED'
        ? CartDetailStatus.FOLLOWING
        : CartDetailStatus.IDLE,
    online: true,
    mapId: mapInfoFixture.id,
    currentZoneId: isMoving || currentZoneIndex === null ? null : currentZoneIndex + 1,
    currentZoneName: isMoving || currentZoneIndex === null ? null : `${currentZoneIndex + 1}구역`,
    position: percentToDisplay(
      currentZoneIndex === null ? START_POSITION : ZONE_POSITIONS[currentZoneIndex],
      mapInfoFixture,
    ),
    lastSeenAt: new Date().toISOString(),
  };
}
