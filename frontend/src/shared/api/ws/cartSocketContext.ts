import { createContext } from 'react';

import type { CartSocket } from './cartSocket';

/** 전역 CartSocket 컨텍스트 — 값 주입은 CartSocketProvider, 소비는 useCartSocket */
export const CartSocketContext = createContext<CartSocket | null>(null);
