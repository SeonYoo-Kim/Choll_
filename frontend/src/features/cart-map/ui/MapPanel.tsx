import { ShoppingCart } from 'lucide-react';

import { useStartNavigation } from '../api/moveCommands';
import { useCartMapStore } from '../model/cartMapStore';
import { ZONE_NAMES, ZONE_RECTS, zoneIdOf, zoneLabel } from '../model/zones';

import mapImage from '@/assets/map.png';
import { useCartControlStore } from '@/features/cart-control/model/cartControlStore';
import { DEMO_CART_ID } from '@/shared/config/cart';
import { useToastStore } from '@/shared/ui/toast/toastStore';

import styles from './MapPanel.module.scss';

import type { CSSProperties } from 'react';

/** SLAM 지도 패널 — 평면도 위 구역을 눌러 카트 목적지를 지정한다. */
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
  const runState = useCartControlStore((state) => state.runState);
  const notify = useToastStore((state) => state.show);

  // 추종 중에 목적지를 지정하면 카트가 "사서를 따라가라"와 "여기로 가라"를 동시에 받는다.
  // 어느 쪽이 이기는지 EM과 정해진 바가 없어, 먼저 추종을 멈추도록 잠근다.
  const following = runState === 'FOLLOWING' || runState === 'PAUSED';

  const { mutate: startNavigation, isPending } = useStartNavigation({
    mutation: {
      onSuccess: (_, { data }) => {
        startMove();
        notify(`${data.zoneId}구역으로 카트가 이동을 시작해요`);
      },
      onError: () => {
        notify('이동 명령을 보내지 못했어요. 잠시 후 다시 시도해주세요');
      },
    },
  });

  const handleZoneClick = (zoneIndex: number) => {
    if (zoneIndex === cartZone) {
      notify(`${zoneLabel(zoneIndex)}에 이미 카트가 있어요`);
      return;
    }
    startNavigation({ cartId: DEMO_CART_ID, data: { zoneId: zoneIdOf(zoneIndex) } });
  };

  return (
    <div className={styles.panel}>
      {/* 패널 제목은 제거 — MapPage의 h1("도서관 지도")과 중복이라 지도만 남긴다 */}
      <div className={styles.canvas}>
        <img src={mapImage} alt="" className={styles.mapImage} />
        {ZONE_RECTS.map((rect, i) => (
          <button
            key={ZONE_NAMES[i]}
            disabled={cartStatus !== 'IDLE' || following || isPending}
            onClick={() => handleZoneClick(i)}
            aria-label={`${zoneLabel(i)} ${ZONE_NAMES[i]}로 카트 이동`}
            className={`${styles.zone} ${i === cartZone ? styles.zoneActive : ''}`}
            style={{
              left: `${rect.left}%`,
              top: `${rect.top}%`,
              width: `${rect.width}%`,
              height: `${rect.height}%`,
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
