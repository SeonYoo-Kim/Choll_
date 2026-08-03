import { useEffect } from 'react';
import { isRouteErrorResponse, useNavigate, useRouteError } from 'react-router';

import styles from './RouteErrorFallback.module.scss';

interface Props {
  /** 페이지 성격에 맞는 이모지 — 없으면 카트 */
  emoji?: string;
  /** 페이지 성격에 맞는 안내 문구 — 없으면 일반 문구를 쓴다 */
  title?: string;
  description?: string;
  /**
   * catch-all 라우트(`path: '*'`)의 element로 쓸 때 지정한다.
   * 이 경우 던져진 에러가 없어 useRouteError()만으로는 404인지 알 수 없다.
   */
  notFound?: boolean;
}

/**
 * 라우트 단위 에러 폴백 — router의 errorElement로 쓴다.
 * 자식 라우트에 걸면 AppLayout(사이드바·하단탭)은 살아 있고 콘텐츠 영역만 대체된다.
 */
export function RouteErrorFallback({
  emoji = '🛒',
  title,
  description,
  notFound: notFoundProp = false,
}: Props) {
  const error = useRouteError();
  const navigate = useNavigate();

  // 화면에는 에러 원문을 노출하지 않으므로 원인 추적은 콘솔로만 남긴다.
  // (ErrorBoundary의 componentDidCatch와 같은 역할 — 사용자에게는 보이지 않는다)
  useEffect(() => {
    if (error) {
      console.error('[RouteError]', error);
    }
  }, [error]);

  // 라우터가 던진 응답 — 없는 주소(404)나 loader의 throw new Response
  const response = isRouteErrorResponse(error) ? error : null;
  const notFound = notFoundProp || response?.status === 404;

  // 없는 주소는 되돌릴 게 없으니 홈으로, 렌더 에러는 다시 그려보게 새로고침
  const view = notFound
    ? {
        emoji: '🔍',
        title: '없는 페이지예요',
        description: '주소를 다시 확인해 주세요.',
        actionLabel: '홈으로',
        onAction: () => navigate('/'),
      }
    : {
        emoji,
        title: response
          ? `문제가 생겼어요 (${response.status})`
          : title || '화면을 불러오지 못했어요',
        description: response?.statusText || description || '잠시 후 다시 시도해 주세요.',
        actionLabel: '다시 시도',
        onAction: () => window.location.reload(),
      };

  return (
    <div className={styles.wrap}>
      <p className={styles.emoji}>{view.emoji}</p>
      <h1 className={styles.title}>{view.title}</h1>
      <p className={styles.desc}>{view.description}</p>
      <button className={styles.button} onClick={view.onAction}>
        {view.actionLabel}
      </button>
    </div>
  );
}
