import { ws } from 'msw';

import mapImage from '@/assets/map.png';
import { percentToDisplay } from '@/features/cart-map/model/mapTransform';
import {
  CORRIDOR_Y,
  START_POSITION,
  ZONE_POSITIONS,
  ZONE_RECTS,
} from '@/features/cart-map/model/zones';
import { DEMO_ZONES, zoneIndexOf } from '@/features/cart-map/model/zoneStore';
import { CartDetailStatus } from '@/shared/api/generated/model';

import type { DisplayPosition, MapPercent } from '@/features/cart-map/model/mapTransform';
import type { CartDetail, MapInfo, ShelfZone } from '@/shared/api/generated/model';
import type {
  CartPositionUpdatePayload,
  CartWsEvent,
  FollowStatus,
  NavigationStatus,
  TracksUpdatedPayload,
} from '@/shared/api/ws/cartSocket';

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
  // 실제 BE는 서버에 올라간 SLAM 지도 주소를 준다. 모킹에서는 번들된 평면도를 그대로 가리켜
  // "서버 지도를 그리는" 정상 경로를 개발 중에도 확인할 수 있게 한다
  imageUrl: mapImage,
  resolution: 0.05,
  originX: 0,
  originY: 0,
  imageWidth: 1174,
  imageHeight: 631,
};

/**
 * 책장 구역 픽스처(MAP-02) — 실제 BE와 같은 모양으로 준다.
 * 경계는 지도 이미지 픽셀 폴리곤의 JSON 문자열이고, 값은 데모 구역(ZONE_RECTS)에서 만든다.
 * 이렇게 해두면 모킹으로 개발해도 서버 응답을 파싱하는 경로를 그대로 지나간다.
 */
export const shelfZonesFixture: ShelfZone[] = ZONE_RECTS.map((rect, index) => {
  const topLeft = percentToDisplay({ x: rect.left, y: rect.top }, mapInfoFixture);
  const bottomRight = percentToDisplay(
    { x: rect.left + rect.width, y: rect.top + rect.height },
    mapInfoFixture,
  );
  // 실제 BE의 시드 데이터가 정수 픽셀이라 반올림해 맞춘다
  const corner = (point: DisplayPosition) => [Math.round(point.x), Math.round(point.y)];
  return {
    id: DEMO_ZONES[index].id,
    mapId: mapInfoFixture.id,
    code: DEMO_ZONES[index].code,
    name: DEMO_ZONES[index].name,
    boundaryData: JSON.stringify([
      corner(topLeft),
      corner({ x: bottomRight.x, y: topLeft.y }),
      corner(bottomRight),
      corner({ x: topLeft.x, y: bottomRight.y }),
    ]),
  };
});

// 주의: 'ws://*/...'처럼 호스트가 와일드카드인 절대 URL 패턴은 브라우저의 URL 해석 과정에서
// 매칭이 깨진다(msw 2.15 기준). '*'로 시작하는 패턴은 해석을 건너뛰므로 안전하다.
// 끝을 '*'가 아니라 ':cartId'로 둔 이유: '*'는 뒤 경로까지 삼켜서 영상 채널
// (/ws/carts/1/video)까지 이 핸들러가 가로채고, JSON 이벤트가 영상 소켓으로 흘러간다.
const cartWsLink = ws.link('*/ws/carts/:cartId');

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

/** 카트 연결 상태 (WS-FE-03). 실제 BE는 하트비트로 판정하지만 모킹에서는 수동으로 바꾼다 */
let isOnline = true;

/**
 * 카트 연결 끊김/복구를 흉내 낸다 — 실제 BE처럼 **상태가 바뀔 때만** 이벤트를 보낸다.
 * 개발 중 `window.__setCartOnline(false)`로 팝업을 확인할 수 있다 (browser.ts에서 노출).
 */
export function setCartOnline(online: boolean): void {
  if (isOnline === online) {
    return;
  }
  isOnline = online;
  broadcast({
    type: 'CART_CONNECTION_UPDATED',
    payload: { online, lastSeenAt: new Date().toISOString() },
  });
}

/** 직전 브로드캐스트 좌표·방향 — 다음 좌표와의 차이로 진행 방향(yaw)을 만든다 */
let lastBroadcastPercent: MapPercent | null = null;
let lastBroadcastYaw = 0;

function broadcastPosition(percent: MapPercent): void {
  const { x, y } = percentToDisplay(percent, mapInfoFixture);
  if (lastBroadcastPercent !== null) {
    const dx = percent.x - lastBroadcastPercent.x;
    const dy = percent.y - lastBroadcastPercent.y;
    // 제자리면 이전 방향을 유지한다 (atan2(0,0)=0이라 카트가 갑자기 오른쪽을 본다)
    if (Math.hypot(dx, dy) > 0.01) {
      // 실제 BE의 yaw는 SLAM 지도 프레임 기준이지만, 모킹에서는 진행 방향으로 대신한다
      lastBroadcastYaw = Math.atan2(dy, dx);
    }
  }
  lastBroadcastPercent = percent;
  // 페이로드 타입을 명시해 필드 누락을 컴파일 단계에서 잡는다
  // (broadcast의 payload가 unknown이라 예전에는 yaw가 빠진 채로 지나갔다)
  const payload: CartPositionUpdatePayload = {
    mapId: mapInfoFixture.id,
    x,
    y,
    yaw: lastBroadcastYaw,
    valid: true,
  };
  broadcast({ type: 'CART_POSITION_UPDATE', payload });
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
    setTimeout(
      () => {
        broadcastZone(null, zoneId); // 목적지 구역 진입
        broadcastPosition(waypoints[2]);
      },
      STEP_MS * 2 + 30,
    ),
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

/**
 * AI 사람 탐지 박스 브로드캐스트 — 영상 시뮬레이터(videoSimulator)가 프레임을 그릴 때마다
 * 같은 좌표로 호출한다. 박스는 영상 채널이 아니라 이 이벤트 채널로 내려간다(BE 계약).
 */
export function broadcastTracks(payload: TracksUpdatedPayload): void {
  broadcast({ type: 'TRACKS_UPDATED', payload });
}

/** 추종 상태 (추종 명령 모킹용) */
let followStatus: FollowStatus = 'STOPPED';

function broadcastFollow(status: FollowStatus): void {
  followStatus = status;
  broadcast({ type: 'FOLLOW_STATUS_UPDATED', payload: { status } });
}

/** 추종 중 위치 발행 주기 — 실제 BE의 1Hz에 맞춘다 */
const FOLLOW_STEP_MS = 1_000;
/** 한 걸음에 움직이는 거리 (% 좌표) — 사서 걸음 속도 흉내 */
const FOLLOW_STEP_PERCENT = 5;

let followTimer: ReturnType<typeof setInterval> | null = null;
let followPosition: MapPercent = START_POSITION;
let followWaypointIndex = 0;

/** 사서가 통로를 따라 구역을 하나씩 둘러보는 경로 */
function followRoute(): MapPercent[] {
  return ZONE_POSITIONS.flatMap((zone) => [
    { x: zone.x, y: CORRIDOR_Y },
    zone,
    { x: zone.x, y: CORRIDOR_Y },
  ]);
}

/** 다음 웨이포인트 쪽으로 한 걸음 옮기고 위치를 발행한다 */
function walkFollowStep(): void {
  const route = followRoute();
  const target = route[followWaypointIndex % route.length];
  const dx = target.x - followPosition.x;
  const dy = target.y - followPosition.y;
  const distance = Math.hypot(dx, dy);

  if (distance <= FOLLOW_STEP_PERCENT) {
    followPosition = target;
    followWaypointIndex = (followWaypointIndex + 1) % route.length;
  } else {
    followPosition = {
      x: followPosition.x + (dx / distance) * FOLLOW_STEP_PERCENT,
      y: followPosition.y + (dy / distance) * FOLLOW_STEP_PERCENT,
    };
  }
  broadcastPosition(followPosition);
}

function stopFollowWalk(): void {
  if (followTimer !== null) {
    clearInterval(followTimer);
    followTimer = null;
  }
}

/**
 * 추종 시작(또는 재개) — 실제 BE처럼 WS FOLLOW_STATUS_UPDATED(WS-FE-07)를 브로드캐스트하고,
 * 사서를 따라가는 동안 위치(WS-FE-01)를 계속 발행해 지도가 실시간으로 움직이게 한다.
 */
export function startCartFollow(): void {
  broadcastFollow('STARTED');
  stopFollowWalk();
  followTimer = setInterval(walkFollowStep, FOLLOW_STEP_MS);
}

/** 추종 일시정지 — 추종 중일 때만 유효. 카트가 멈추므로 위치 발행도 멈춘다 */
export function pauseCartFollow(): void {
  if (followStatus === 'STARTED') {
    broadcastFollow('PAUSED');
    stopFollowWalk();
  }
}

/** 추종 종료 */
export function stopCartFollow(): void {
  stopFollowWalk();
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

/**
 * 시뮬레이터 기준 카트의 현재 구역 id — 이동 중이거나 구역 밖이면 null.
 * 실제 BE가 카트 위치로 구역을 판정하는 것에 대응한다 (슬롯 isTarget 계산에도 쓰인다).
 */
export function currentCartZoneId(): number | null {
  return isMoving || currentZoneIndex === null ? null : currentZoneIndex + 1;
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
    online: isOnline,
    mapId: mapInfoFixture.id,
    currentZoneId: currentCartZoneId(),
    currentZoneName: isMoving || currentZoneIndex === null ? null : `${currentZoneIndex + 1}구역`,
    position: percentToDisplay(
      currentZoneIndex === null ? START_POSITION : ZONE_POSITIONS[currentZoneIndex],
      mapInfoFixture,
    ),
    lastSeenAt: new Date().toISOString(),
  };
}
