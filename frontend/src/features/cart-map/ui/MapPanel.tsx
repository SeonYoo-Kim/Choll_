import { useCartMapStore } from '../model/cartMapStore';
import { ZONE_NAMES, zoneLabel } from '../model/zones';

import { useToastStore } from '@/shared/ui/toast/toastStore';

import styles from './MapPanel.module.scss';

/** SLAM 지도 패널 — 구역 버튼을 눌러 카트 목적지를 지정한다. */
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
        <svg
          className={styles.corridor}
          viewBox="0 0 100 100"
          preserveAspectRatio="none"
          fill="none"
        >
          <path
            d="M13 29V53M38 29V53M62 29V53M87 29V53M13 53H87M13 53V77M38 53V77M62 53V77M87 53V77"
            stroke="currentColor"
            strokeWidth="4"
            strokeLinecap="round"
            strokeDasharray="2 3"
          />
        </svg>
        <div className={styles.zoneGrid}>
          {ZONE_NAMES.map((name, i) => (
            <button
              key={name}
              disabled={isMoving}
              onClick={() => moveCart(i, notify)}
              aria-label={`${zoneLabel(i)} ${name}로 카트 이동`}
              className={`${styles.zone} ${i === cartZone ? styles.zoneActive : ''}`}
            >
              <span className={styles.zoneNo}>{zoneLabel(i)}</span>
              {name}
            </button>
          ))}
        </div>
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
