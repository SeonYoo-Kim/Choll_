import { WifiOff, X } from 'lucide-react';

import { useCartConnectionStore } from '../model/cartConnectionStore';

import styles from './CartOfflineModal.module.scss';

/**
 * 마지막 통신 시각을 "오후 9:12" 형태로 만든다.
 * BE가 타임존 없는 LocalDateTime(Asia/Seoul)을 주므로 브라우저 로컬 시각으로 해석된다 —
 * 사서와 서버가 같은 시간대라는 전제이며, 값이 이상하면 시각을 생략한다.
 */
function formatLastSeen(value: string | null): string | null {
  if (value === null) {
    return null;
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return null;
  }
  return date.toLocaleTimeString('ko-KR', { hour: 'numeric', minute: '2-digit' });
}

/**
 * 카트 연결 끊김 알림 팝업 (WS-FE-03).
 * AppLayout에 두어 어느 화면에서든 뜬다. 연결이 돌아오면 스스로 사라진다.
 */
export function CartOfflineModal() {
  const online = useCartConnectionStore((state) => state.online);
  const dismissed = useCartConnectionStore((state) => state.dismissed);
  const lastSeenAt = useCartConnectionStore((state) => state.lastSeenAt);
  const dismiss = useCartConnectionStore((state) => state.dismiss);

  if (online || dismissed) {
    return null;
  }

  const lastSeen = formatLastSeen(lastSeenAt);

  return (
    <div className={styles.backdrop}>
      <div className={styles.modal} role="alertdialog" aria-labelledby="cart-offline-title">
        <button className={styles.close} onClick={dismiss} aria-label="닫기">
          <X size={16} />
        </button>
        <div className={styles.icon}>
          <WifiOff size={24} />
        </div>
        <p className={styles.overline}>CONNECTION LOST</p>
        <h2 className={styles.title} id="cart-offline-title">
          카트와 연결이 끊겼어요
        </h2>
        <p className={styles.desc}>
          카트의 전원과 네트워크를 확인해주세요.
          <br />
          다시 연결되면 이 창은 저절로 닫힙니다.
          {lastSeen !== null && (
            <>
              <br />
              <strong>마지막 통신 {lastSeen}</strong>
            </>
          )}
        </p>
        <button className={styles.primary} onClick={dismiss}>
          확인
        </button>
      </div>
    </div>
  );
}
