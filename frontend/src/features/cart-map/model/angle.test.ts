import { describe, expect, it } from 'vitest';

import { normalizeAngle, unwrapAngle } from './angle';

const PI = Math.PI;

describe('normalizeAngle', () => {
  it('범위 안의 각도는 그대로 둔다', () => {
    expect(normalizeAngle(0)).toBeCloseTo(0);
    expect(normalizeAngle(1.5)).toBeCloseTo(1.5);
    expect(normalizeAngle(-1.5)).toBeCloseTo(-1.5);
  });

  it('한 바퀴를 넘는 각도를 -π..π로 접는다', () => {
    expect(normalizeAngle(2 * PI)).toBeCloseTo(0);
    expect(normalizeAngle(3 * PI)).toBeCloseTo(-PI);
    expect(normalizeAngle(-2.5 * PI)).toBeCloseTo(-0.5 * PI);
  });
});

describe('unwrapAngle', () => {
  it('π 부근을 지날 때 한 바퀴가 아니라 짧은 쪽으로 돈다', () => {
    // 3.1 → -3.1은 실제로 0.08rad만 움직인 것이다
    const next = unwrapAngle(3.1, -3.1);
    expect(next - 3.1).toBeCloseTo(2 * PI - 6.2, 5);
    expect(Math.abs(next - 3.1)).toBeLessThan(0.1);
  });

  it('반대 방향으로 지날 때도 짧은 쪽으로 돈다', () => {
    const next = unwrapAngle(-3.1, 3.1);
    expect(Math.abs(next - -3.1)).toBeLessThan(0.1);
    expect(next).toBeLessThan(-3.1);
  });

  it('여러 번 넘어가도 누적되어 이어진다 — 같은 방향으로 계속 돌면 값이 계속 커진다', () => {
    let yaw = 0;
    // -π..π로 접혀 들어오는 값을 순서대로 먹인다 (한 바퀴 반시계)
    for (const incoming of [1.5, 3.0, -2.0, -0.5, 1.0]) {
      yaw = unwrapAngle(yaw, incoming);
    }
    // 한 바퀴(2π) 돌았으므로 접힌 값 1.0이 아니라 1.0 + 2π 근처여야 한다
    expect(yaw).toBeCloseTo(1.0 + 2 * PI, 5);
  });

  it('변화가 없으면 값을 유지한다', () => {
    expect(unwrapAngle(1.23, 1.23)).toBeCloseTo(1.23);
  });
});
