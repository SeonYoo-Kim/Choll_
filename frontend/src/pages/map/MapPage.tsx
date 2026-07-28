import { useCartMapStore } from '@/features/cart-map/model/cartMapStore';
import { useCartMapEvents } from '@/features/cart-map/model/useCartMapEvents';
import { ZONE_NAMES, zoneLabel } from '@/features/cart-map/model/zones';
import { ArrivalModal } from '@/features/cart-map/ui/ArrivalModal';
import { MapPanel } from '@/features/cart-map/ui/MapPanel';
import { useListSlots } from '@/shared/api/generated/slots/slots';
import { DEMO_CART_ID } from '@/shared/config/cart';

import styles from './MapPage.module.scss';

import type { CartDetailStatus } from '@/shared/api/generated/model';
import type { NavigationStatus } from '@/shared/api/ws/cartSocket';

/** CART-01 카트 동작 상태 표시 문구 */
const CART_STATUS_LABELS: Record<CartDetailStatus, string> = {
  IDLE: '대기 중',
  MOVING: '이동 중',
  FOLLOWING: '추종 중',
  ERROR: '오류 발생',
};

/** WS-FE-06 목적지 이동 상태 표시 문구 */
const NAV_STATUS_LABELS: Record<NavigationStatus, string> = {
  ACCEPTED: '이동 접수됨',
  STARTED: '목적지로 이동 중',
  STOPPED: '이동 정지됨',
  ARRIVED: '도착 완료',
  CANCELLED: '이동이 취소됐어요',
  FAILED: '이동에 실패했어요',
};

/** 지도 — SLAM 지도 위 카트 위치 확인과 목적지 지정. */
export function MapPage() {
  useCartMapEvents(DEMO_CART_ID);
  const { cartZone, isMoving, cartStatus, navStatus } = useCartMapStore();
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
              {cartZone === null ? '이동 통로' : `${zoneLabel(cartZone)} · ${ZONE_NAMES[cartZone]}`}
            </strong>
          </div>
          <div className={styles.statCard}>
            <p>카트 상태</p>
            <strong>{CART_STATUS_LABELS[cartStatus]}</strong>
          </div>
          <div className={styles.statCard}>
            <p>이동 안내</p>
            <strong>{navStatus === null ? '서가 선택 가능' : NAV_STATUS_LABELS[navStatus]}</strong>
          </div>
        </div>
      </div>
      <ArrivalModal slots={slots ?? []} />
    </>
  );
}
