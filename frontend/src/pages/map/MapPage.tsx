import { CircleStop } from 'lucide-react';

import { useCancelNavigation } from '@/features/cart-map/api/moveCommands';
import { useCartMapStore } from '@/features/cart-map/model/cartMapStore';
import { ZONE_NAMES, zoneLabel } from '@/features/cart-map/model/zones';
import { ArrivalModal } from '@/features/cart-map/ui/ArrivalModal';
import { MapPanel } from '@/features/cart-map/ui/MapPanel';
import { useListSlots } from '@/shared/api/generated/slots/slots';
import { DEMO_CART_ID } from '@/shared/config/cart';
import { useToastStore } from '@/shared/ui/toast/toastStore';

import styles from './MapPage.module.scss';

import type { NavigationStatus } from '@/shared/api/ws/cartSocket';

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
  const { cartZone, isMoving, cartStatus, navStatus } = useCartMapStore();
  const { data: slots } = useListSlots(DEMO_CART_ID);
  const notify = useToastStore((state) => state.show);
  // 이동 명령 세션(isMoving) 또는 위치 변화로 감지한 움직임(cartStatus)
  const cartActive = isMoving || cartStatus === 'MOVING';

  // NAV-02 이동 취소 — 취소 완료(CANCELLED) 반영은 WS NAVIGATION_STATUS_UPDATED 수신으로 일어난다
  const cancelNavigation = useCancelNavigation({
    mutation: {
      onSuccess: () => notify('카트를 멈추라고 전달했어요'),
      onError: () => notify('이동 중지에 실패했어요'),
    },
  });

  return (
    <>
      <div className={styles.pageHeader}>
        <div>
          <p className={styles.overline}>LIVE CART LOCATION</p>
          <h1 className={styles.pageTitle}>도서관 지도</h1>
          <p className={styles.pageDesc}>구역을 선택해 카트의 다음 목적지를 정해보세요.</p>
        </div>
        <div className={`${styles.statusBadge} ${cartActive ? styles.moving : styles.idle}`}>
          <span className={styles.dot} />
          {cartActive ? '카트 이동 중' : '카트 정지'}
        </div>
      </div>
      <div className={styles.mapArea}>
        <MapPanel />
        <div className={styles.statCards}>
          <div className={styles.statCard}>
            <p>현재 위치</p>
            <strong className={styles.statPrimary}>
              {cartZone === null ? (
                cartActive ? (
                  '이동 통로'
                ) : (
                  '출발 지점'
                )
              ) : (
                <>
                  {zoneLabel(cartZone)}
                  <span className={styles.zoneName}>{ZONE_NAMES[cartZone]}</span>
                </>
              )}
            </strong>
          </div>
          <div className={styles.statCard}>
            <p>이동 안내</p>
            <strong>
              {navStatus !== null
                ? NAV_STATUS_LABELS[navStatus]
                : cartStatus === 'MOVING'
                  ? '카트가 움직이는 중'
                  : '서가 선택 가능'}
            </strong>
          </div>
          <button
            className={styles.stopButton}
            onClick={() => cancelNavigation.mutate({ cartId: DEMO_CART_ID })}
            disabled={!isMoving || cancelNavigation.isPending}
          >
            <CircleStop size={16} />
            이동 중지
          </button>
        </div>
      </div>
      <ArrivalModal slots={slots ?? []} />
    </>
  );
}
