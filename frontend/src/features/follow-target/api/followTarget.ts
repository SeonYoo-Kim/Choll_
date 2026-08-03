import { useMutation } from '@tanstack/react-query';

import { http } from '@/shared/api/http';

import type { UseMutationOptions } from '@tanstack/react-query';

/**
 * 추종 대상 선택 API — 임시 수동 정의.
 *
 * POST /api/carts/{cartId}/follow/target — 사서가 영상에서 고른 track id를 카트에 하행한다.
 * BE Swagger(openapi.yaml 정본)에 아직 없어 orval 생성물이 없다 (followCommands.ts와 같은 패턴).
 * TODO: BE 반영 후 `pnpm api:gen`으로 재생성하면 selectFollowTarget 훅이 생기므로 이 파일을 지울 것.
 */

export interface SelectFollowTargetBody {
  /** TRACKS_UPDATED로 받은 Track.id */
  trackId: number;
}

/** 202 응답 본문 — status는 "카트로 명령을 보냈다"는 뜻이지 추종 성공을 보장하지 않는다 */
export interface SelectFollowTargetResponse {
  trackId: number;
  status: string;
}

const selectFollowTarget = (cartId: number, data: SelectFollowTargetBody) =>
  http<SelectFollowTargetResponse>({
    url: `/api/carts/${cartId}/follow/target`,
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    data,
  });

type SelectFollowTargetVariables = { cartId: number; data: SelectFollowTargetBody };

/** 추종 대상 선택 뮤테이션 — orval 생성 훅과 동일한 시그니처 */
export const useSelectFollowTarget = (options?: {
  mutation?: UseMutationOptions<SelectFollowTargetResponse, unknown, SelectFollowTargetVariables>;
}) =>
  useMutation({
    mutationFn: ({ cartId, data }: SelectFollowTargetVariables) => selectFollowTarget(cartId, data),
    ...options?.mutation,
  });
