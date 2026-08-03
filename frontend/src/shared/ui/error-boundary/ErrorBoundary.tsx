import { Component, type ErrorInfo, type ReactNode } from 'react';

import styles from './ErrorBoundary.module.scss';

interface Props {
  children: ReactNode;
}

interface State {
  error: Error | null;
}

/**
 * 전역 에러 바운더리 — 라우터 바깥(프로바이더·라우터 초기화)에서 터진
 * 렌더 에러까지 잡는 최후의 보루. React 18에서는 클래스 컴포넌트만 가능하다.
 */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('[ErrorBoundary]', error, info.componentStack);
  }

  render() {
    const { error } = this.state;

    if (!error) {
      return this.props.children;
    }
    return (
      <div className={styles.wrap}>
        <p className={styles.emoji}>🛒</p>
        <h1 className={styles.title}>카트가 잠시 멈췄어요</h1>
        <p className={styles.desc}>
          화면을 그리는 중 문제가 생겼어요.
          <br />
          새로고침하면 대부분 해결돼요.
        </p>
        <button className={styles.button} onClick={() => window.location.reload()}>
          새로고침
        </button>
      </div>
    );
  }
}
