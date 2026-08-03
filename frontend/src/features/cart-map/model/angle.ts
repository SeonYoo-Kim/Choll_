const TWO_PI = Math.PI * 2;

/** 각도를 -π..π 범위로 접는다 */
export function normalizeAngle(radians: number): number {
  return ((((radians + Math.PI) % TWO_PI) + TWO_PI) % TWO_PI) - Math.PI;
}

/**
 * 이전 각도에서 목표 각도로 "짧은 쪽"으로 돌아간 연속 각도를 만든다.
 *
 * BE의 yaw는 -π..π로 접혀서 오기 때문에, 카트가 π 부근을 지나면 값이 3.1 → -3.1로 튄다.
 * 이 값을 그대로 CSS rotate에 넣으면 실제로는 0.08rad만 돈 것을 6.2rad 반대로 도는 애니메이션이
 * 된다(제자리에서 한 바퀴 도는 현상). 누적값으로 바꿔 두면 항상 짧은 쪽으로 돈다.
 */
export function unwrapAngle(previous: number, target: number): number {
  return previous + normalizeAngle(target - previous);
}
