import { useCartMapStore } from '../model/cartMapStore';
import { ZONE_NAMES, ZONE_RECTS, zoneLabel } from '../model/zones';

import mapImage from '@/assets/map.png';
import { useToastStore } from '@/shared/ui/toast/toastStore';

import styles from './MapPanel.module.scss';

/** SLAM 지도 패널 — 평면도 위 구역을 눌러 카트 목적지를 지정한다. */
export function MapPanel() {
  const { cartZone, cartPosition, isMoving, moveCart } = useCartMapStore();
  const notify = useToastStore((state) => state.show);

  return (
    <div className={styles.panel}>
      <div className={styles.header}>
        <p className={styles.overline}>LIBRARY MAP</p>
        <h3 className={styles.title}>우리 도서관 지도</h3>
      </div>
      <div className={styles.canvas}>
        <img src={mapImage} alt="" className={styles.mapImage} />
        {ZONE_RECTS.map((rect, i) => (
          <button
            key={ZONE_NAMES[i]}
            disabled={isMoving}
            onClick={() => moveCart(i, notify)}
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
          style={{ left: `${cartPosition.x}%`, top: `${cartPosition.y}%` }}
        >
          🛒
        </div>
      </div>
    </div>
  );
}
