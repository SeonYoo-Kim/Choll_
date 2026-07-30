import { useContext } from 'react';

import { CartSocketContext } from './cartSocketContext';

import type { CartSocket } from './cartSocket';

/** 전역 CartSocket 인스턴스. CartSocketProvider 아래에서만 사용할 수 있다. */
export function useCartSocket(): CartSocket {
  const socket = useContext(CartSocketContext);
  if (!socket) {
    throw new Error('useCartSocket은 CartSocketProvider 안에서만 사용할 수 있어요');
  }
  return socket;
}
