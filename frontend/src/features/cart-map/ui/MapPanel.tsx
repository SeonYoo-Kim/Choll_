import { useStartNavigation } from '../api/moveCommands';
import { useCartMapStore } from '../model/cartMapStore';
import { ZONE_NAMES, ZONE_RECTS, zoneIdOf, zoneLabel } from '../model/zones';

import mapImage from '@/assets/map.png';
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
  const notify = useToastStore((state) => state.show);

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
            disabled={cartStatus !== 'IDLE' || isPending}
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
              transform: `translate(-50%, -50%) rotate(${cartYaw}rad)`,
              '--cart-move-duration': `${positionIntervalMs}ms`,
            } as CSSProperties
          }
        >
          🛒
        </div>
      </div>
    </div>
  );
}
