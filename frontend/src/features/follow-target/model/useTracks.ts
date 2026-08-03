import { useEffect, useState } from 'react';

import { useCartSocket } from '@/shared/api/ws/useCartSocket';

import type { Track, TracksUpdatedPayload } from '@/shared/api/ws/cartSocket';

/** 영상 해상도 기본값 — 첫 TRACKS_UPDATED가 오기 전까지 쓰는 값 */
const DEFAULT_IMAGE_SIZE = { width: 640, height: 480 } as const;

export interface TracksState {
  tracks: Track[];
  /** 박스 좌표의 기준이 되는 원본 영상 크기 */
  imageWidth: number;
  imageHeight: number;
  /** TRACKS_UPDATED를 한 번이라도 받았는지 — "탐지 대기 중"과 "탐지된 사람 없음" 구분용 */
  received: boolean;
}

/**
 * AI 사람 탐지 박스 구독 훅 — 이벤트 채널(/ws/carts/{cartId})의 TRACKS_UPDATED.
 *
 * 영상과 달리 초당 수 건 수준이라 state로 둬도 리렌더 부담이 없다.
 * 구독은 이 훅을 쓰는 컴포넌트(추종 대상 선택 모달)가 열려 있는 동안만 유지된다.
 */
export function useTracks(): TracksState {
  const socket = useCartSocket();
  const [state, setState] = useState<TracksState>({
    tracks: [],
    imageWidth: DEFAULT_IMAGE_SIZE.width,
    imageHeight: DEFAULT_IMAGE_SIZE.height,
    received: false,
  });

  useEffect(
    () =>
      socket.on<TracksUpdatedPayload>('TRACKS_UPDATED', ({ payload }) => {
        setState({
          tracks: payload.tracks ?? [],
          // 0이 오면 박스 좌표 변환이 0으로 나눠지므로 기본값으로 되돌린다
          imageWidth: payload.image_width || DEFAULT_IMAGE_SIZE.width,
          imageHeight: payload.image_height || DEFAULT_IMAGE_SIZE.height,
          received: true,
        });
      }),
    [socket],
  );

  return state;
}
