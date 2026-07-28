import { ws } from 'msw';

import { toSlamPosition } from '@/features/cart-map/model/mapTransform';
import { CORRIDOR_Y, ZONE_POSITIONS, zoneIndexOf } from '@/features/cart-map/model/zones';
import { CartDetailStatus } from '@/shared/api/generated/model';

import type { MapPercent } from '@/features/cart-map/model/mapTransform';
import type { CartDetail, MapInfo } from '@/shared/api/generated/model';
import type { CartWsEvent } from '@/shared/api/ws/cartSocket';

/**
 * 개발용 카트 이동 시뮬레이터 (가짜 BE).
 * REST callCart 모킹 핸들러가 startCartMove를 호출하면, 실제 BE처럼
 * WS로 CART_POSITION_UPDATE(경유지)와 CART_ARRIVED(도착)를 브로드캐스트한다.
 * 구역 좌표는 FE 지도 픽스처(zones.ts)를 재사용해 화면과 항상 일치시킨다.
 */

/** 지도 메타 픽스처 — 시뮬레이터가 %↔SLAM(m) 변환에 쓰는 기준값 */
export const mapInfoFixture: MapInfo = {
  id: 1,
  name: '우리 도서관 1층',
  imageUrl: '/map.png',
  resolution: 0.05,
  originX: 0,
  originY: 0,
  imageWidth: 1000,
  imageHeight: 800,
};

// 주의: 'ws://*/...'처럼 호스트가 와일드카드인 절대 URL 패턴은 브라우저의 URL 해석 과정에서
// 매칭이 깨진다(msw 2.15 기준). '*'로 시작하는 패턴은 해석을 건너뛰므로 안전하다.
const cartWsLink = ws.link('*/ws/carts/*');

/** WS 연결 인터셉트 핸들러 — 등록만 해도 실서버 연결 시도(무한 재시도)를 막는다 */
export const cartWsHandler = cartWsLink.addEventListener('connection', () => {});

const STEP_MS = 340;

let currentZoneIndex = 2;
let isMoving = false;
let moveTimers: ReturnType<typeof setTimeout>[] = [];

function broadcast(event: CartWsEvent): void {
  cartWsLink.broadcast(JSON.stringify(event));
}

function broadcastPosition(percent: MapPercent, zoneId: number | null): void {
  broadcast({
    type: 'CART_POSITION_UPDATE',
    payload: { position: toSlamPosition(percent, mapInfoFixture), zoneId },
  });
}

/** 목적지 구역으로 이동 시작 — 구역 → 통로 → 목적지 순서로 경유지를 브로드캐스트 */
export function startCartMove(zoneId: number): void {
  const destinationIndex = zoneIndexOf(zoneId);
  if (destinationIndex === null || isMoving || destinationIndex === currentZoneIndex) {
    return;
  }
  isMoving = true;
  const start = ZONE_POSITIONS[currentZoneIndex];
  const destination = ZONE_POSITIONS[destinationIndex];
  const waypoints: { percent: MapPercent; zoneId: number | null }[] = [
    { percent: { x: start.x, y: CORRIDOR_Y }, zoneId: null },
    { percent: { x: destination.x, y: CORRIDOR_Y }, zoneId: null },
    { percent: destination, zoneId },
  ];
  waypoints.forEach((waypoint, i) => {
    moveTimers.push(
      setTimeout(() => broadcastPosition(waypoint.percent, waypoint.zoneId), STEP_MS * i + 30),
    );
  });
  moveTimers.push(
    setTimeout(
      () => {
        currentZoneIndex = destinationIndex;
        isMoving = false;
        moveTimers = [];
        broadcast({ type: 'CART_ARRIVED', payload: { zoneId, zoneName: `${zoneId}구역` } });
      },
      STEP_MS * 3 + 60,
    ),
  );
}

/** 이동 취소(정지) — 예약된 경유지 브로드캐스트를 모두 취소한다 */
export function stopCartMove(): void {
  moveTimers.forEach(clearTimeout);
  moveTimers = [];
  isMoving = false;
}

/** 시뮬레이터 상태를 반영한 카트 상세 픽스처 (getCart 모킹 응답) */
export function cartDetailFixture(cartId: number): CartDetail {
  return {
    id: cartId,
    name: '쫄래쫄래 1호',
    status: isMoving ? CartDetailStatus.MOVING : CartDetailStatus.IDLE,
    online: true,
    mapId: mapInfoFixture.id,
    currentZoneId: isMoving ? null : currentZoneIndex + 1,
    currentZoneName: isMoving ? null : `${currentZoneIndex + 1}구역`,
    position: toSlamPosition(ZONE_POSITIONS[currentZoneIndex], mapInfoFixture),
    lastSeenAt: new Date().toISOString(),
  };
}
