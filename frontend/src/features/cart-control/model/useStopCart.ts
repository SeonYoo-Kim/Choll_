import { useStopFollow } from '../api/followCommands';
import { useCartControlStore } from './cartControlStore';

import { useCancelNavigation } from '@/features/cart-map/api/moveCommands';
import { useCartMapStore } from '@/features/cart-map/model/cartMapStore';
import { useToastStore } from '@/shared/ui/toast/toastStore';

export interface StopCart {
  /** 카트가 하고 있는 일을 전부 멈춘다 */
  stop: () => void;
  /** 멈출 것이 있는지 — 버튼 활성화 조건 */
  canStop: boolean;
  isPending: boolean;
}

/**
 * 카트를 멈추는 공용 동작 — 사서 추종이든 목적지 이동이든 진행 중인 것을 모두 취소한다.
 *
 * 홈의 '이동 취소'와 지도의 '이동 중지'는 사서에게 같은 버튼이어야 하는데,
 * 두 화면이 각자 한쪽 명령만 보내고 있었다(홈=추종 종료, 지도=이동 취소).
 * 그래서 추종 중에는 지도에서 멈출 수 없고, 목적지 이동 중에는 홈에서 멈출 수 없었다.
 * 판단 기준과 명령을 여기 한곳에 모아 두 화면이 같은 것을 쓰게 한다.
 */
export function useStopCart(cartId: number): StopCart {
  const runState = useCartControlStore((state) => state.runState);
  const applyFollowStatus = useCartControlStore((state) => state.applyFollowStatus);
  const isNavigating = useCartMapStore((state) => state.isMoving);
  const notify = useToastStore((state) => state.show);

  // 일시정지도 추종 세션이 살아 있는 상태라 종료 대상이다
  const isFollowing = runState === 'FOLLOWING' || runState === 'PAUSED';

  const stopFollow = useStopFollow({
    mutation: {
      onSuccess: () => {
        applyFollowStatus('STOPPED');
        // 추종 중 들어온 위치 이벤트 때문에 올라가 있던 '이동 중' 표시를 바로 내린다.
        // 그냥 두면 정지 감지(3초)가 걸릴 때까지 지도에 '카트 이동 중'이 남고
        // 구역 버튼도 잠긴 채라, 멈추라고 눌렀는데 반응이 없어 보인다.
        useCartMapStore.getState().markStationary();
        notify('카트를 멈추라고 전달했어요');
      },
      onError: () => notify('추종 종료에 실패했어요'),
    },
  });

  // 취소 완료(CANCELLED) 반영은 WS NAVIGATION_STATUS_UPDATED 수신으로 일어난다
  const cancelNavigation = useCancelNavigation({
    mutation: {
      onSuccess: () => notify('카트를 멈추라고 전달했어요'),
      onError: () => notify('이동 중지에 실패했어요'),
    },
  });

  const canStop = isFollowing || isNavigating;

  return {
    canStop,
    isPending: stopFollow.isPending || cancelNavigation.isPending,
    stop: () => {
      // 추종과 목적지 이동이 동시에 걸려 있을 수 있어 각각 확인해 보낸다
      if (isFollowing) {
        stopFollow.mutate({ cartId });
      }
      if (isNavigating) {
        cancelNavigation.mutate({ cartId });
      }
    },
  };
}
