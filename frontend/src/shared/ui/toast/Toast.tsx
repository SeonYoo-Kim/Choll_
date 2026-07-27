import { useToastStore } from './toastStore';

import styles from './Toast.module.scss';

/** 화면 하단 중앙의 토스트 메시지. AppLayout에서 한 번만 렌더링한다. */
export function Toast() {
  const message = useToastStore((state) => state.message);

  if (!message) {
    return null;
  }
  return <div className={styles.toast}>{message}</div>;
}
