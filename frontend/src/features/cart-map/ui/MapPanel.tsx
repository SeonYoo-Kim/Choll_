import { ShoppingCart } from 'lucide-react';
import { useRef } from 'react';

import { useStartNavigation } from '../api/moveCommands';
import { useCartMapStore } from '../model/cartMapStore';
import { FLOOR_PLAN_IMAGE, FLOOR_PLAN_SIZE } from '../model/floorPlanImage';
import { clientPointToDisplay, percentToDisplay } from '../model/mapTransform';
import { zoneLabel } from '../model/zones';
import { useZoneStore } from '../model/zoneStore';

import { useCartControlStore } from '@/features/cart-control/model/cartControlStore';
import { DEMO_CART_ID } from '@/shared/config/cart';
import { useToastStore } from '@/shared/ui/toast/toastStore';

import styles from './MapPanel.module.scss';

import type { CSSProperties, MouseEvent } from 'react';

/** 지도 영역의 가로세로 비율 — 평면도 원본 그대로 (crop 방지) */
const PLAN_ASPECT_RATIO = `${FLOOR_PLAN_SIZE.width} / ${FLOOR_PLAN_SIZE.height}`;

/** 도서관 평면도 패널 — 통로를 눌러 카트 목적지를 지정한다. */
export function MapPanel() {
  // 스토어를 통째로 구독하면 도착 모달 상태처럼 지도와 무관한 값이 바뀔 때도 다시 그린다.
  // 위치 이벤트가 초당 여러 번 오는 환경을 대비해 필요한 값만 각각 고른다.
  const cartZone = useCartMapStore((state) => state.cartZone);
  const cartPosition = useCartMapStore((state) => state.cartPosition);
  const cartYaw = useCartMapStore((state) => state.cartYaw);
  const positionIntervalMs = useCartMapStore((state) => state.positionIntervalMs);
  const isMoving = useCartMapStore((state) => state.isMoving);
  const cartStatus = useCartMapStore((state) => state.cartStatus);
  const startMove = useCartMapStore((state) => state.startMove);
  // 구역의 위치·이름은 평면도가 정하고 id만 서버에서 온다 (zoneStore 참조)
  const zones = useZoneStore((state) => state.zones);
  const mapInfo = useCartMapStore((state) => state.mapInfo);
  const mapUnavailable = useCartMapStore((state) => state.mapUnavailable);
  // 누른 지점을 지도 픽셀로 되돌리려면 그림이 화면에서 차지한 영역이 필요하다.
  // 바깥 .canvas가 아니라 그림 자체를 재는 이유: .canvas에는 1px 테두리가 있어 그 사각형이
  // 그림보다 2px 크다. 구역 버튼의 % 좌표는 테두리 안쪽(패딩 박스)을 기준으로 잡히므로,
  // 클릭 좌표도 같은 박스에서 재야 버튼 위치와 어긋나지 않는다.
  const mapImageRef = useRef<HTMLImageElement>(null);
  const runState = useCartControlStore((state) => state.runState);
  const notify = useToastStore((state) => state.show);

  // 추종 중에 목적지를 지정하면 카트가 "사서를 따라가라"와 "여기로 가라"를 동시에 받는다.
  // 어느 쪽이 이기는지 EM과 정해진 바가 없어, 먼저 추종을 멈추도록 잠근다.
  const following = runState === 'FOLLOWING' || runState === 'PAUSED';

  const { mutate: startNavigation, isPending } = useStartNavigation({
    mutation: {
      onSuccess: (_, { data }) => {
        startMove();
        const zoneIndex = zones.findIndex((zone) => zone.id === data.zoneId);
        notify(
          `${zoneIndex === -1 ? '해당 구역' : zoneLabel(zoneIndex)}으로 카트가 이동을 시작해요`,
        );
      },
      onError: () => {
        notify('이동 명령을 보내지 못했어요. 잠시 후 다시 시도해주세요');
      },
    },
  });

  // 지도 메타(MAP-01)가 없으면 화면 좌표를 BE 지도 픽셀로 되돌릴 수 없다.
  // 평면도 그림은 번들돼 있어 그릴 수 있지만, 카트 위치도 목적지도 좌표 없이는 뜻이 없으므로
  // 에러 화면으로 넘긴다 (라우트 errorElement가 "지도를 불러오지 못했어요"를 띄운다).
  if (mapUnavailable) {
    throw new Error('지도 정보(MAP-01)를 불러오지 못했습니다');
  }

  // 아직 지도 정보를 받는 중 — 카트·구역을 얹을 좌표 기준이 없으니 자리만 잡아 둔다
  if (mapInfo === null) {
    return (
      <div className={styles.panel}>
        <div className={styles.canvas} style={{ aspectRatio: PLAN_ASPECT_RATIO }}>
          <p className={styles.loading}>지도를 불러오는 중이에요…</p>
        </div>
      </div>
    );
  }

  /**
   * 누른 지점을 BE 지도 픽셀 좌표로 바꾼다 — 구역 한가운데가 아니라 사서가 찍은 자리로 보내기 위함.
   * 키보드로 버튼을 누르면 좌표가 없으므로(detail 0) null을 준다.
   */
  const clickedPoint = (event: MouseEvent<HTMLElement>) => {
    if (event.detail === 0 || mapImageRef.current === null) {
      return null;
    }
    return clientPointToDisplay(
      { x: event.clientX, y: event.clientY },
      mapImageRef.current.getBoundingClientRect(),
      mapInfo,
    );
  };

  const handleZoneClick = (zoneIndex: number, event: MouseEvent<HTMLButtonElement>) => {
    // 같은 클릭을 지도 전체 핸들러가 한 번 더 처리하지 않게 한다
    event.stopPropagation();
    if (zoneIndex === cartZone) {
      notify(`${zoneLabel(zoneIndex)}에 이미 카트가 있어요`);
      return;
    }
    const zone = zones[zoneIndex];
    if (zone === undefined) {
      return;
    }
    // 서버 구역 목록에 이 코드가 없으면 실을 id가 없다 — 임시 id를 보내면 엉뚱한 구역으로 간다
    if (zone.id === null) {
      notify(`${zoneLabel(zoneIndex)}의 구역 정보를 서버에서 받지 못해 이동할 수 없어요`);
      return;
    }
    // 마우스로 누르면 그 지점, 키보드로 누르면 구역 중심을 목적지로 삼는다
    const point = clickedPoint(event) ?? percentToDisplay(zone.center, mapInfo);
    startNavigation({
      cartId: DEMO_CART_ID,
      data: { zoneId: zone.id, x: Math.round(point.x), y: Math.round(point.y) },
    });
  };

  // 구역 버튼이 stopPropagation으로 자기 클릭을 가져가므로, 여기까지 온 클릭은 통로 밖이다.
  // 서가·테이블 위는 카트가 들어갈 수 없고 BE도 zoneId 없는 목적지를 받지 않는다.
  const handleOutsideClick = () => {
    notify('카트가 갈 수 있는 통로를 눌러주세요');
  };

  return (
    <div className={styles.panel}>
      {/* 패널 제목은 제거 — MapPage의 h1("도서관 지도")과 중복이라 지도만 남긴다 */}
      {/* 비율을 평면도 원본에 맞춘다 — 어긋나면 cover 크롭 때문에 클릭 지점이 실제와 달라진다 */}
      <div
        className={styles.canvas}
        style={{ aspectRatio: PLAN_ASPECT_RATIO }}
        onClick={handleOutsideClick}
      >
        <img ref={mapImageRef} src={FLOOR_PLAN_IMAGE} alt="" className={styles.mapImage} />
        {zones.map((zone, i) => (
          <button
            key={zone.code}
            disabled={cartStatus !== 'IDLE' || following || isPending}
            onClick={(event) => handleZoneClick(i, event)}
            aria-label={`${zoneLabel(i)} ${zone.name}로 카트 이동`}
            className={`${styles.zone} ${i === cartZone ? styles.zoneActive : ''}`}
            style={{
              left: `${zone.rect.left}%`,
              top: `${zone.rect.top}%`,
              width: `${zone.rect.width}%`,
              height: `${zone.rect.height}%`,
            }}
          />
        ))}
        <div
          aria-label="카트 위치"
          className={`${styles.cart} ${isMoving ? styles.cartMoving : ''}`}
          // 다음 좌표까지 이동 시간을 위치 이벤트 간격에 맞춘다 — 짧게 잡으면 움직이다 멈추기를
          // 반복하고, 길게 잡으면 실제 카트보다 늦게 따라간다
          style={
            {
              left: `${cartPosition.x}%`,
              top: `${cartPosition.y}%`,
              '--cart-move-duration': `${positionIntervalMs}ms`,
            } as CSSProperties
          }
        >
          {/*
            원과 꼬리를 path 하나로 그려 이음매 없이 붙인다. 이 도형만 진행 방향으로 돌리고,
            아이콘은 회전 밖에 둬서 카트가 어느 쪽으로 가도 똑바로 서 있게 한다.
            (도형째 돌리면서 아이콘까지 같이 돌면 왼쪽으로 갈 때 카트가 뒤집힌다)
          */}
          <svg
            className={styles.marker}
            viewBox="0 0 48 48"
            style={{ transform: `rotate(${cartYaw}rad)` }}
            aria-hidden="true"
          >
            <defs>
              <linearGradient id="cartMarkerFill" x1="0.2" y1="0" x2="0.8" y2="1">
                <stop offset="0" stopColor="#7ccfc3" />
                <stop offset="1" stopColor="#4ba59a" />
              </linearGradient>
            </defs>
            {/* 반지름 15 원의 오른쪽을 열고(±25°) 꼭짓점(46,24)까지 이어 붙인 물방울 모양 */}
            <path
              d="M37.59 17.66 A15 15 0 1 0 37.59 30.34 L46 24 Z"
              fill="url(#cartMarkerFill)"
              stroke="#fff"
              strokeWidth="3"
              strokeLinejoin="round"
            />
          </svg>
          {/* 이모지 대신 lucide 아이콘 — 앱의 다른 아이콘과 톤이 맞고 색을 마커에 맞출 수 있다 */}
          <ShoppingCart className={styles.icon} size={16} strokeWidth={2.5} aria-hidden="true" />
        </div>
      </div>
    </div>
  );
}
