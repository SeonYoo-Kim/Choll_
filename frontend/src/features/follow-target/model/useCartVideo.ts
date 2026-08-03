import { useEffect, useState } from 'react';

import { wsBaseUrl } from '@/shared/api/ws/wsBaseUrl';

import type { RefObject } from 'react';

/** 영상 채널 상태 — 화면에 연결 중/끊김 안내를 띄우기 위한 값 */
export type VideoStatus = 'connecting' | 'streaming' | 'disconnected';

const RETRY_DELAY_MS = 1_000;

/**
 * 카트 카메라 영상 수신 훅 — `/ws/carts/{cartId}/video`.
 *
 * 계약: 바이너리 메시지 1건 = JPEG 1프레임. Blob → object URL로 바꿔 img에 그린다.
 * 프레임마다 리렌더하면 10 FPS로 컴포넌트 전체가 다시 그려지므로,
 * state 대신 전달받은 img 엘리먼트의 src를 직접 갱신한다(상태값만 state).
 *
 * object URL은 revoke하지 않으면 프레임마다 메모리에 쌓인다 —
 * 새 프레임을 넣은 뒤 직전 URL을 해제하고, 언마운트 시 마지막 URL도 해제한다.
 */
export function useCartVideo(
  cartId: number,
  imgRef: RefObject<HTMLImageElement | null>,
): VideoStatus {
  const [status, setStatus] = useState<VideoStatus>('connecting');

  useEffect(() => {
    let socket: WebSocket | null = null;
    let retryTimer: ReturnType<typeof setTimeout> | null = null;
    let lastUrl: string | null = null;
    let closedByUnmount = false;

    const revokeLast = () => {
      if (lastUrl) {
        URL.revokeObjectURL(lastUrl);
        lastUrl = null;
      }
    };

    const connect = () => {
      const url = `${wsBaseUrl()}/ws/carts/${cartId}/video`;
      socket = new WebSocket(url);
      socket.binaryType = 'arraybuffer';

      socket.onopen = () => {
        console.info(`[CartVideo] 연결됨: ${url}`);
        setStatus('streaming');
      };

      socket.onmessage = (message: MessageEvent<ArrayBuffer>) => {
        const frameUrl = URL.createObjectURL(new Blob([message.data], { type: 'image/jpeg' }));
        if (imgRef.current) {
          imgRef.current.src = frameUrl;
        }
        // 직전 프레임 URL은 새 프레임을 넣은 뒤에 해제한다 (표시 중인 URL을 끊지 않도록)
        revokeLast();
        lastUrl = frameUrl;
      };

      socket.onclose = () => {
        if (closedByUnmount) return;
        console.info(`[CartVideo] 연결 끊김 — ${RETRY_DELAY_MS}ms 후 재연결 시도`);
        setStatus('disconnected');
        retryTimer = setTimeout(connect, RETRY_DELAY_MS);
      };
    };

    connect();

    return () => {
      closedByUnmount = true;
      if (retryTimer !== null) clearTimeout(retryTimer);
      socket?.close();
      revokeLast();
    };
  }, [cartId, imgRef]);

  return status;
}
