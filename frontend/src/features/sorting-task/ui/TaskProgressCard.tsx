import { useGetTaskProgress } from '@/shared/api/generated/tasks/tasks';

import styles from './TaskProgressCard.module.scss';

interface TaskProgressCardProps {
  cartId: number;
}

/** 홈 화면의 카트 정리 현황 카드 — 진행률 도넛 + 남은/완료 권수. */
export function TaskProgressCard({ cartId }: TaskProgressCardProps) {
  // 이 카드만 실패해도 홈 전체가 에러 화면이 되지 않게 던지지 않는다 —
  // 히어로(카트 위치)와 카트 제어(정지 버튼)는 계속 쓸 수 있어야 한다.
  const { data, isError, refetch } = useGetTaskProgress(cartId, {
    query: { throwOnError: false },
  });

  const total = data?.totalBooks ?? 0;
  const shelved = data?.shelvedBooks ?? 0;
  const remaining = data?.remainingBooks ?? 0;
  const percent = total > 0 ? Math.round((shelved / total) * 100) : 0;

  // 0%·0권으로 조용히 거짓말하지 않고 실패를 명시한다
  if (isError) {
    return (
      <div className={styles.card}>
        <p className={styles.label}>카트 정리 현황</p>
        <div className={styles.errorBody}>
          <p className={styles.errorText}>정리 현황을 불러오지 못했어요</p>
          <button className={styles.retry} onClick={() => void refetch()}>
            다시 시도
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className={styles.card}>
      <p className={styles.label}>카트 정리 현황</p>
      <div className={styles.body}>
        <div
          className={styles.donut}
          style={{ background: `conic-gradient(#69c2b6 0 ${percent}%, #e9f0e7 ${percent}% 100%)` }}
        >
          <div className={styles.donutInner}>
            <strong>{percent}%</strong>
          </div>
        </div>
        <div className={styles.stats}>
          <p>
            <strong>{remaining}권</strong>
            <span>카트에 남음</span>
          </p>
          <p>
            <strong>{shelved}권</strong>
            <span>정리 완료</span>
          </p>
        </div>
      </div>
    </div>
  );
}
