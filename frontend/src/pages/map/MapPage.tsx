import { useCartMapStore } from '@/features/cart-map/model/cartMapStore';
import { ZONE_NAMES, zoneLabel } from '@/features/cart-map/model/zones';
import { ArrivalModal } from '@/features/cart-map/ui/ArrivalModal';
import { MapPanel } from '@/features/cart-map/ui/MapPanel';
import { useListSlots } from '@/shared/api/generated/slots/slots';
import { DEMO_CART_ID } from '@/shared/config/cart';

import styles from './MapPage.module.scss';

/** 지도 — SLAM 지도 위 카트 위치 확인과 목적지 지정. */
export function MapPage() {
  const { cartZone, isMoving } = useCartMapStore();
  const { data: slots } = useListSlots(DEMO_CART_ID);

  return (
    <>
      <div className={styles.pageHeader}>
        <div>
          <p className={styles.overline}>LIVE CART LOCATION</p>
          <h1 className={styles.pageTitle}>도서관 지도</h1>
          <p className={styles.pageDesc}>서가를 눌러 카트의 다음 목적지를 정해보세요.</p>
        </div>
        <div className={`${styles.statusBadge} ${isMoving ? styles.moving : styles.idle}`}>
          <span className={styles.dot} />
          {isMoving ? '카트 이동 중' : '카트 위치 확인'}
        </div>
      </div>
      <div className={styles.mapArea}>
        <MapPanel />
        <div className={styles.statCards}>
          <div className={styles.statCard}>
            <p>현재 위치</p>
            <strong className={styles.statPrimary}>
              {zoneLabel(cartZone)} · {ZONE_NAMES[cartZone]}
            </strong>
          </div>
          <div className={styles.statCard}>
            <p>카트 상태</p>
            <strong>{isMoving ? '이동 중' : '도착 완료'}</strong>
          </div>
          <div className={styles.statCard}>
            <p>이동 안내</p>
            <strong>{isMoving ? '목적지로 이동 중' : '서가 선택 가능'}</strong>
          </div>
        </div>
      </div>
      <ArrivalModal slots={slots ?? []} />
    </>
  );
}
