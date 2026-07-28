import { CircleStop, Compass, Play } from 'lucide-react';

import { useCartControlStore } from '../model/cartControlStore';

import { useToastStore } from '@/shared/ui/toast/toastStore';

import styles from './CartControlCard.module.scss';

/** 홈 화면의 카트 제어 카드 — 추종 시작/정지, 이동 취소. */
export function CartControlCard() {
  const { runState, setRunState } = useCartControlStore();
  const notify = useToastStore((state) => state.show);
  const following = runState === 'FOLLOWING';

  return (
    <div className={styles.card}>
      <p className={styles.label}>카트 제어</p>
      <div className={styles.grid}>
        <button
          onClick={() => {
            setRunState(following ? 'STOPPED' : 'FOLLOWING');
            notify(following ? '추종을 잠시 멈췄어요' : '카트가 다시 따라와요');
          }}
          className={`${styles.control} ${following ? styles.following : styles.idle}`}
        >
          {following ? <Play size={24} fill="currentColor" /> : <Compass size={24} />}
          <span>{following ? '추종 중' : '추종 시작'}</span>
        </button>
        <button
          onClick={() => {
            setRunState('STOPPED');
            notify('카트가 제자리에서 멈췄어요');
          }}
          className={`${styles.control} ${styles.stop}`}
        >
          <CircleStop size={24} />
          <span>이동 취소</span>
        </button>
      </div>
    </div>
  );
}
