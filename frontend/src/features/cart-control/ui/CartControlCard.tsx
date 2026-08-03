import { useRef, useState } from 'react';

import { CircleStop, Compass, Pause, Play } from 'lucide-react';

import { usePauseFollow, useStartFollow } from '../api/followCommands';
import { useCartControlStore } from '../model/cartControlStore';
import { useStopCart } from '../model/useStopCart';

import { FollowTargetModal } from '@/features/follow-target/ui/FollowTargetModal';
import { DEMO_CART_ID } from '@/shared/config/cart';
import { useToastStore } from '@/shared/ui/toast/toastStore';

import styles from './CartControlCard.module.scss';

/** 홈 화면의 카트 제어 카드 — 추종 시작/일시정지/종료. */
export function CartControlCard() {
  const { runState, applyFollowStatus } = useCartControlStore();
  const notify = useToastStore((state) => state.show);
  const following = runState === 'FOLLOWING';
  const paused = runState === 'PAUSED';

  const [targetModalOpen, setTargetModalOpen] = useState(false);
  // 방금 고른 track id — 추종 시작 응답이 왔을 때 안내 문구에 쓴다.
  // state가 아니라 ref인 이유: 이 값이 바뀐다고 다시 그릴 것이 없다.
  const selectedTrackIdRef = useRef<number | null>(null);

  const startFollow = useStartFollow({
    mutation: {
      onSuccess: () => {
        applyFollowStatus('STARTED');
        const trackId = selectedTrackIdRef.current;
        selectedTrackIdRef.current = null;
        notify(
          trackId !== null
            ? `${trackId}번 사람을 따라가요`
            : paused
              ? '카트가 다시 따라와요'
              : '추종을 시작했어요',
        );
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
  // 지도 화면의 '이동 중지'와 같은 동작 — 추종·목적지 이동을 가리지 않고 전부 멈춘다
  const stopCart = useStopCart(DEMO_CART_ID);
  const pending = startFollow.isPending || pauseFollow.isPending || stopCart.isPending;

  /**
   * 추종 중 → 일시정지, 일시정지 → 바로 재개, 정지 → 추종 대상 선택부터.
   * 재개할 때 대상을 다시 고르게 하지 않는 이유: 잠시 멈춘 것뿐이라 대상은 그대로다.
   */
  const handleFollowClick = () => {
    if (following) {
      pauseFollow.mutate({ cartId: DEMO_CART_ID });
    } else if (paused) {
      startFollow.mutate({ cartId: DEMO_CART_ID });
    } else {
      setTargetModalOpen(true);
    }
  };

  // 대상 선택(202) 성공 → 모달을 닫고 이어서 추종을 시작한다
  const handleTargetSelected = (trackId: number) => {
    selectedTrackIdRef.current = trackId;
    setTargetModalOpen(false);
    startFollow.mutate({ cartId: DEMO_CART_ID });
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
          onClick={stopCart.stop}
          disabled={!stopCart.canStop || pending}
          className={`${styles.control} ${styles.stop}`}
        >
          <CircleStop size={24} />
          <span>이동 취소</span>
        </button>
      </div>
      {targetModalOpen && (
        <FollowTargetModal
          cartId={DEMO_CART_ID}
          onClose={() => setTargetModalOpen(false)}
          onSelected={handleTargetSelected}
        />
      )}
    </div>
  );
}
