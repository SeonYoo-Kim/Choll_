import { CircleStop } from 'lucide-react';

import { useCartControlStore } from '@/features/cart-control/model/cartControlStore';
import { useStopCart } from '@/features/cart-control/model/useStopCart';
import { useCartMapStore } from '@/features/cart-map/model/cartMapStore';
import { ZONE_NAMES, zoneLabel } from '@/features/cart-map/model/zones';
import { ArrivalModal } from '@/features/cart-map/ui/ArrivalModal';
import { MapPanel } from '@/features/cart-map/ui/MapPanel';
import { useListSlots } from '@/shared/api/generated/slots/slots';
import { DEMO_CART_ID } from '@/shared/config/cart';

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
  // 위치 좌표는 이 화면이 직접 쓰지 않는다 — 통째로 구독하면 좌표가 올 때마다 페이지 전체가 다시 그려진다
  const cartZone = useCartMapStore((state) => state.cartZone);
  const isMoving = useCartMapStore((state) => state.isMoving);
  const cartStatus = useCartMapStore((state) => state.cartStatus);
  const navStatus = useCartMapStore((state) => state.navStatus);
  const runState = useCartControlStore((state) => state.runState);
  const { data: slots } = useListSlots(DEMO_CART_ID);
  // 이동 명령 세션(isMoving) 또는 위치 변화로 감지한 움직임(cartStatus)
  const cartActive = isMoving || cartStatus === 'MOVING';
  const following = runState === 'FOLLOWING';
  const followPaused = runState === 'PAUSED';

  // 홈의 '이동 취소'와 같은 동작 — 추종·목적지 이동을 가리지 않고 멈춘다
  const stopCart = useStopCart(DEMO_CART_ID);

  // 홈 배지와 같은 우선순위 — 사서를 따라가는 중이면 좌표가 움직이는지와 무관하게 추종으로 표시한다
  const badge = following
    ? { label: '사서를 따라가는 중', tone: styles.following }
    : cartActive
      ? { label: '카트 이동 중', tone: styles.moving }
      : { label: '카트 정지', tone: styles.idle };

  const guide = following
    ? '사서를 따라가는 중'
    : followPaused
      ? '추종 일시정지'
      : navStatus !== null
        ? NAV_STATUS_LABELS[navStatus]
        : cartStatus === 'MOVING'
          ? '카트가 움직이는 중'
          : '서가 선택 가능';

  return (
    <>
      <div className={styles.pageHeader}>
        <div>
          <p className={styles.overline}>LIVE CART LOCATION</p>
          <h1 className={styles.pageTitle}>도서관 지도</h1>
          <p className={styles.pageDesc}>구역을 선택해 카트의 다음 목적지를 정해보세요.</p>
        </div>
        <div className={`${styles.statusBadge} ${badge.tone}`}>
          <span className={styles.dot} />
          {badge.label}
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
            <strong>{guide}</strong>
          </div>
          <button
            className={styles.stopButton}
            onClick={stopCart.stop}
            disabled={!stopCart.canStop || stopCart.isPending}
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
