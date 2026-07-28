import { useMutation } from '@tanstack/react-query';

import { http } from '@/shared/api/http';

import type { UseMutationOptions } from '@tanstack/react-query';

/**
 * 목적지 이동(navigation) 명령 API — 임시 수동 정의.
 *
 * 노션 API 명세 기준: NAV-01 이동 시작(POST /navigation), NAV-02 이동 취소(DELETE /navigation).
 * BE Swagger(openapi.yaml 정본)에 아직 없어 orval 생성 클라이언트가 존재하지 않는다.
 * 호출 시그니처는 orval 생성 훅과 동일하게 맞춰 두었다.
 * TODO: BE 구현 후 `pnpm api:gen` 재생성 시 이 파일을 지우고 생성 훅으로 교체할 것.
 * TODO: NAV-01 요청 body 필드명(zoneId)은 BE와 확정 필요.
 */

export interface StartNavigationBody {
  /** 목적지 구역 shelf_zone.id */
  zoneId: number;
}

const startNavigation = (cartId: number, data: StartNavigationBody) =>
  http<void>({ url: `/api/carts/${cartId}/navigation`, method: 'POST', data });

const cancelNavigation = (cartId: number) =>
  http<void>({ url: `/api/carts/${cartId}/navigation`, method: 'DELETE' });

/** NAV-01 목적지 이동 시작 뮤테이션 — orval 생성 훅과 동일한 시그니처 */
export const useStartNavigation = (options?: {
  mutation?: UseMutationOptions<void, unknown, { cartId: number; data: StartNavigationBody }>;
}) =>
  useMutation({
    mutationFn: ({ cartId, data }: { cartId: number; data: StartNavigationBody }) =>
      startNavigation(cartId, data),
    ...options?.mutation,
  });

/** NAV-02 목적지 이동 취소 뮤테이션 — orval 생성 훅과 동일한 시그니처 */
export const useCancelNavigation = (options?: {
  mutation?: UseMutationOptions<void, unknown, { cartId: number }>;
}) =>
  useMutation({
    mutationFn: ({ cartId }: { cartId: number }) => cancelNavigation(cartId),
    ...options?.mutation,
  });
