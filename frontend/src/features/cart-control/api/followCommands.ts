import { useMutation } from '@tanstack/react-query';

import { http } from '@/shared/api/http';

import type { UseMutationOptions } from '@tanstack/react-query';

/**
 * 사서 추종(follow) 명령 API — 임시 수동 정의.
 *
 * 추종 시작(POST /follow) · 일시정지(POST /follow/pause) · 종료(DELETE /follow).
 * BE Swagger(openapi.yaml 정본)에 아직 없어 orval 생성 클라이언트가 존재하지 않는다
 * (NAV moveCommands.ts와 같은 패턴). 호출 시그니처는 orval 생성 훅과 동일하게 맞춰 두었다.
 * TODO: BE 구현 후 `pnpm api:gen` 재생성 시 이 파일을 지우고 생성 훅으로 교체할 것.
 * TODO: 경로·메서드(특히 일시정지)는 BE와 확정 필요.
 */

const startFollow = (cartId: number) =>
  http<void>({ url: `/api/carts/${cartId}/follow`, method: 'POST' });

const pauseFollow = (cartId: number) =>
  http<void>({ url: `/api/carts/${cartId}/follow/pause`, method: 'POST' });

const stopFollow = (cartId: number) =>
  http<void>({ url: `/api/carts/${cartId}/follow`, method: 'DELETE' });

/** 추종 시작(또는 일시정지 후 재개) 뮤테이션 — orval 생성 훅과 동일한 시그니처 */
export const useStartFollow = (options?: {
  mutation?: UseMutationOptions<void, unknown, { cartId: number }>;
}) =>
  useMutation({
    mutationFn: ({ cartId }: { cartId: number }) => startFollow(cartId),
    ...options?.mutation,
  });

/** 추종 일시정지 뮤테이션 — orval 생성 훅과 동일한 시그니처 */
export const usePauseFollow = (options?: {
  mutation?: UseMutationOptions<void, unknown, { cartId: number }>;
}) =>
  useMutation({
    mutationFn: ({ cartId }: { cartId: number }) => pauseFollow(cartId),
    ...options?.mutation,
  });

/** 추종 종료 뮤테이션 — orval 생성 훅과 동일한 시그니처 */
export const useStopFollow = (options?: {
  mutation?: UseMutationOptions<void, unknown, { cartId: number }>;
}) =>
  useMutation({
    mutationFn: ({ cartId }: { cartId: number }) => stopFollow(cartId),
    ...options?.mutation,
  });
