import { describe, expect, it } from 'vitest';

import { isTargetCommandSent } from './followTarget';

describe('isTargetCommandSent', () => {
  it('SENT면 카트로 명령이 나간 것으로 본다', () => {
    expect(isTargetCommandSent({ trackId: 3, status: 'SENT' })).toBe(true);
  });

  it('대소문자가 달라도 같은 값으로 본다', () => {
    expect(isTargetCommandSent({ trackId: 3, status: 'sent' })).toBe(true);
  });

  it('모르는 상태값이면 실패로 본다 — 여기서 막아야 추종 시작까지 넘어가지 않는다', () => {
    expect(isTargetCommandSent({ trackId: 3, status: 'REJECTED' })).toBe(false);
    expect(isTargetCommandSent({ trackId: 3, status: 'FAILED' })).toBe(false);
  });

  it('본문이 없으면 판단할 근거가 없으므로 성공으로 본다', () => {
    expect(isTargetCommandSent(undefined)).toBe(true);
    expect(isTargetCommandSent({ trackId: 3, status: '' })).toBe(true);
  });
});
