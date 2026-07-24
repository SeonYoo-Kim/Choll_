import { useGetTaskProgress } from '@/shared/api/generated/tasks/tasks';

import styles from './TaskProgressCard.module.scss';

interface TaskProgressCardProps {
  cartId: string;
}

/** 홈 화면의 카트 정리 현황 카드 — 진행률 도넛 + 남은/완료 권수. */
export function TaskProgressCard({ cartId }: TaskProgressCardProps) {
  const { data } = useGetTaskProgress(cartId);

  const total = data?.totalBooks ?? 0;
  const shelved = data?.shelvedBooks ?? 0;
  const remaining = data?.remainingBooks ?? 0;
  const percent = total > 0 ? Math.round((shelved / total) * 100) : 0;

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
