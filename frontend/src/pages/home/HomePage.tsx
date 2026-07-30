import { useNavigate } from 'react-router';

import { useCartControlStore } from '@/features/cart-control/model/cartControlStore';
import { CartControlCard } from '@/features/cart-control/ui/CartControlCard';
import { useCartMapStore } from '@/features/cart-map/model/cartMapStore';
import { ZONE_NAMES, zoneLabel } from '@/features/cart-map/model/zones';
import { TaskProgressCard } from '@/features/sorting-task/ui/TaskProgressCard';
import { useListSlots } from '@/shared/api/generated/slots/slots';
import { DEMO_CART_ID } from '@/shared/config/cart';

import styles from './HomePage.module.scss';

/** 홈 — 카트 현재 위치, 정리 현황, 제어를 한눈에 보는 대시보드. */
export function HomePage() {
  const navigate = useNavigate();
  const runState = useCartControlStore((state) => state.runState);
  const { cartZone, isMoving } = useCartMapStore();
  const { data: slots } = useListSlots(DEMO_CART_ID);

  const following = runState === 'FOLLOWING';
  // 이동 중(구역 밖)이면 null — 구역 표시 대신 이동 중 문구를 쓴다
  const currentArea = cartZone === null ? null : zoneLabel(cartZone);
  const areaBookCount =
    currentArea === null
      ? 0
      : (slots?.filter((slot) => slot.book?.zoneName === currentArea).length ?? 0);

  return (
    <>
      <div className={styles.pageHeader}>
        <div>
          <p className={styles.overline}>CART COMMAND CENTER</p>
          <h1 className={styles.pageTitle}>카트와 함께, 쫄래쫄래</h1>
        </div>
        <div className={`${styles.followBadge} ${following ? styles.on : styles.off}`}>
          <span className={styles.dot} />
          {following ? '카트가 따라오는 중' : '카트가 잠시 멈췄어요'}
        </div>
      </div>
      <div className={styles.grid}>
        <div className={styles.column}>
          <div className={styles.hero}>
            <div className={styles.heroRing} />
            <div className={styles.heroCart}>🛒</div>
            <p className={styles.heroLabel}>지금 가까운 곳</p>
            <div className={styles.heroTitleRow}>
              <h2 className={styles.heroTitle}>
                {cartZone === null ? (
                  isMoving ? (
                    '목적지로 이동 중'
                  ) : (
                    '출발 지점에서 대기 중'
                  )
                ) : (
                  <>
                    {currentArea}
                    <span className={styles.heroZoneName}>{ZONE_NAMES[cartZone]}</span>
                  </>
                )}
              </h2>
              {!isMoving && cartZone !== null && (
                <span className={styles.arrivedBadge}>도착!</span>
              )}
            </div>
            <p className={styles.heroDesc}>
              {cartZone === null ? (
                '지도에서 구역을 지정하면 카트가 출발해요.'
              ) : (
                <>
                  이 구역에 꽂아야 할 책이 <strong>{areaBookCount}권</strong> 있어요.
                </>
              )}
            </p>
            <button className={styles.heroButton} onClick={() => navigate('/map')}>
              지도에서 카트 이동하기
            </button>
          </div>
          <div className={styles.cards}>
            <TaskProgressCard cartId={DEMO_CART_ID} />
            <CartControlCard />
          </div>
        </div>
      </div>
    </>
  );
}
