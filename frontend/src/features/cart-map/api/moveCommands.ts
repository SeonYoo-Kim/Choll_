import { useMutation } from '@tanstack/react-query';

import { http } from '@/shared/api/http';

import type { UseMutationOptions } from '@tanstack/react-query';

/**
 * 카트 이동 명령 API — 임시 수동 정의.
 *
 * BE Swagger(openapi.yaml 정본)에 /commands/call·/commands/stop이 아직 없어
 * orval 생성 클라이언트가 존재하지 않는다. 노션 API 명세서 기준으로 손으로 정의하되,
 * 호출 시그니처는 orval 생성 훅과 동일하게 맞춰 두었다.
 * TODO: BE 구현 후 `pnpm api:gen` 재생성 시 이 파일을 지우고 생성 훅으로 교체할 것.
 */

export interface CallCartBody {
  /** shelf_zone.id */
  zoneId: number;
}

const callCart = (cartId: number, data: CallCartBody) =>
  http<void>({ url: `/api/carts/${cartId}/commands/call`, method: 'POST', data });

const stopCart = (cartId: number) =>
  http<void>({ url: `/api/carts/${cartId}/commands/stop`, method: 'POST' });

/** 카트 호출(목적지 구역으로 이동) 뮤테이션 — orval 생성 훅과 동일한 시그니처 */
export const useCallCart = (options?: {
  mutation?: UseMutationOptions<void, unknown, { cartId: number; data: CallCartBody }>;
}) =>
  useMutation({
    mutationFn: ({ cartId, data }: { cartId: number; data: CallCartBody }) => callCart(cartId, data),
    ...options?.mutation,
  });

/** 이동 취소(정지) 뮤테이션 — orval 생성 훅과 동일한 시그니처 */
export const useStopCart = (options?: {
  mutation?: UseMutationOptions<void, unknown, { cartId: number }>;
}) =>
  useMutation({
    mutationFn: ({ cartId }: { cartId: number }) => stopCart(cartId),
    ...options?.mutation,
  });
