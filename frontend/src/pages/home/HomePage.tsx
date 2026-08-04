import { ShoppingCart } from 'lucide-react';
import { useNavigate } from 'react-router';

import { useCartControlStore } from '@/features/cart-control/model/cartControlStore';
import { CartControlCard } from '@/features/cart-control/ui/CartControlCard';
import { useCartMapStore } from '@/features/cart-map/model/cartMapStore';
import { zoneLabel } from '@/features/cart-map/model/zones';
import { useZoneName, zoneIdOf } from '@/features/cart-map/model/zoneStore';
import { isSlotForZone } from '@/features/slot-board/model/slotTargeting';
import { TaskProgressCard } from '@/features/sorting-task/ui/TaskProgressCard';
import { useListSlots } from '@/shared/api/generated/slots/slots';
import { DEMO_CART_ID } from '@/shared/config/cart';

import styles from './HomePage.module.scss';

/**
 * 상단 배지의 문구·톤. 추종이 이동보다 우선한다 —
 * 사서를 따라가는 중이면 좌표가 움직이는지와 무관하게 추종으로 표시한다.
 */
const CART_BADGE = {
  following: { label: '카트가 따라오는 중', tone: styles.on },
  moving: { label: '카트가 이동 중이에요', tone: styles.moving },
  idle: { label: '카트가 잠시 멈췄어요', tone: styles.off },
} as const;

/** 홈 — 카트 현재 위치, 정리 현황, 제어를 한눈에 보는 대시보드. */
export function HomePage() {
  const navigate = useNavigate();
  const runState = useCartControlStore((state) => state.runState);
  // 지도 좌표는 홈에서 쓰지 않으므로, 좌표 갱신이 홈 전체 리렌더로 번지지 않게 필요한 값만 고른다
  const cartZone = useCartMapStore((state) => state.cartZone);
  const zoneName = useZoneName(cartZone);
  const isMoving = useCartMapStore((state) => state.isMoving);
  const cartStatus = useCartMapStore((state) => state.cartStatus);
  const { data: slots } = useListSlots(DEMO_CART_ID);

  const following = runState === 'FOLLOWING';
  // 이동 명령 세션(isMoving) 또는 위치 변화로 감지한 움직임(cartStatus)
  const cartActive = isMoving || cartStatus === 'MOVING';
  const badge = CART_BADGE[following ? 'following' : cartActive ? 'moving' : 'idle'];
  // 이동 중(구역 밖)이면 null — 구역 표시 대신 이동 중 문구를 쓴다
  const currentArea = cartZone === null ? null : zoneLabel(cartZone);
  // 구역 이름이 아니라 구역 id로 맞춘다 (slotTargeting 참고)
  const currentZoneId = cartZone === null ? null : zoneIdOf(cartZone);
  const areaBookCount = slots?.filter((slot) => isSlotForZone(slot, currentZoneId)).length ?? 0;

  return (
    <>
      <div className={styles.pageHeader}>
        <div>
          <p className={styles.overline}>CART COMMAND CENTER</p>
          <h1 className={styles.pageTitle}>카트와 함께, 쫄래쫄래</h1>
        </div>
        <div className={`${styles.followBadge} ${badge.tone}`}>
          <span className={styles.dot} />
          {badge.label}
        </div>
      </div>
      <div className={styles.grid}>
        <div className={styles.column}>
          <div className={styles.hero}>
            {/* 배경 장식 — 읽는 내용이 아니므로 스크린리더에서 숨긴다 */}
            <ShoppingCart className={styles.heroCart} strokeWidth={1.5} aria-hidden="true" />
            <p className={styles.heroLabel}>지금 가까운 곳</p>
            <div className={styles.heroTitleRow}>
              <h2 className={styles.heroTitle}>
                {cartZone === null ? (
                  isMoving ? (
                    '목적지로 이동 중'
                  ) : cartActive ? (
                    '카트가 움직이는 중'
                  ) : (
                    '출발 지점에서 대기 중'
                  )
                ) : (
                  <>
                    {currentArea}
                    <span className={styles.heroZoneName}>{zoneName}</span>
                  </>
                )}
              </h2>
              {!cartActive && cartZone !== null && (
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
