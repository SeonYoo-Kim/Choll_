import { describe, expect, it } from 'vitest';

import { ZONE_BOOKSHELVES, ZONE_NAMES, zoneIndexOfBookshelf } from './zones';

describe('zoneIndexOfBookshelf', () => {
  it('책장 번호를 평면도 배치대로 담당 구역에 매핑한다', () => {
    expect(zoneIndexOfBookshelf('000')).toBe(0); // Z1
    expect(zoneIndexOfBookshelf('100')).toBe(1); // Z2
    expect(zoneIndexOfBookshelf('200')).toBe(1); // Z2
    expect(zoneIndexOfBookshelf('300')).toBe(2); // Z3
    expect(zoneIndexOfBookshelf('400')).toBe(2); // Z3
    expect(zoneIndexOfBookshelf('500')).toBe(3); // Z4
    expect(zoneIndexOfBookshelf('600')).toBe(4); // Z5
    expect(zoneIndexOfBookshelf('700')).toBe(5); // Z6
    expect(zoneIndexOfBookshelf('800')).toBe(5); // Z6
    expect(zoneIndexOfBookshelf('900')).toBe(6); // Z7
  });

  it('목록에 없는 책장 번호는 null을 반환한다', () => {
    expect(zoneIndexOfBookshelf('123')).toBeNull();
    expect(zoneIndexOfBookshelf('')).toBeNull();
  });

  it('구역 수와 책장 매핑 수가 일치하고 000~900이 모두 배정돼 있다', () => {
    expect(ZONE_BOOKSHELVES).toHaveLength(ZONE_NAMES.length);
    const all = ZONE_BOOKSHELVES.flat();
    expect([...all].sort()).toEqual(
      Array.from({ length: 10 }, (_, i) => `${i}00`.padStart(3, '0')).sort(),
    );
  });
});
