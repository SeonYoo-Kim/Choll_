import { CircleStop, Compass, Pause, Play } from 'lucide-react';

import { usePauseFollow, useStartFollow, useStopFollow } from '../api/followCommands';
import { useCartControlStore } from '../model/cartControlStore';

import { DEMO_CART_ID } from '@/shared/config/cart';
import { useToastStore } from '@/shared/ui/toast/toastStore';

import styles from './CartControlCard.module.scss';

/** 홈 화면의 카트 제어 카드 — 추종 시작/일시정지/종료. */
export function CartControlCard() {
  const { runState, applyFollowStatus } = useCartControlStore();
  const notify = useToastStore((state) => state.show);
  const following = runState === 'FOLLOWING';
  const paused = runState === 'PAUSED';

  const startFollow = useStartFollow({
    mutation: {
      onSuccess: () => {
        applyFollowStatus('STARTED');
        notify(paused ? '카트가 다시 따라와요' : '추종을 시작했어요');
      },
      onError: () => notify('추종 시작에 실패했어요'),
    },
  });
  const pauseFollow = usePauseFollow({
    mutation: {
      onSuccess: () => {
        applyFollowStatus('PAUSED');
        notify('추종을 잠시 멈췄어요');
      },
      onError: () => notify('일시정지에 실패했어요'),
    },
  });
  const stopFollow = useStopFollow({
    mutation: {
      onSuccess: () => {
        applyFollowStatus('STOPPED');
        notify('추종을 종료했어요 — 카트가 제자리에 멈춰요');
      },
      onError: () => notify('추종 종료에 실패했어요'),
    },
  });
  const pending = startFollow.isPending || pauseFollow.isPending || stopFollow.isPending;

  // 추종 중 → 일시정지, 그 외(정지·일시정지) → 시작/재개
  const handleFollowClick = () => {
    if (following) {
      pauseFollow.mutate({ cartId: DEMO_CART_ID });
    } else {
      startFollow.mutate({ cartId: DEMO_CART_ID });
    }
  };

  return (
    <div className={styles.card}>
      <p className={styles.label}>카트 제어</p>
      <div className={styles.grid}>
        <button
          onClick={handleFollowClick}
          disabled={pending}
          className={`${styles.control} ${
            following ? styles.following : paused ? styles.paused : styles.idle
          }`}
        >
          {following ? (
            <Pause size={24} fill="currentColor" />
          ) : paused ? (
            <Play size={24} fill="currentColor" />
          ) : (
            <Compass size={24} />
          )}
          <span>{following ? '추종 중' : paused ? '일시정지' : '추종 시작'}</span>
        </button>
        <button
          onClick={() => stopFollow.mutate({ cartId: DEMO_CART_ID })}
          disabled={pending}
          className={`${styles.control} ${styles.stop}`}
        >
          <CircleStop size={24} />
          <span>이동 취소</span>
        </button>
      </div>
    </div>
  );
}
