import { describe, expect, it } from 'vitest';

import {
  CORRIDOR_Y,
  MAP_LANDMARKS,
  START_POSITION,
  ZONE_BOOKSHELVES,
  ZONE_CODES,
  ZONE_NAMES,
  ZONE_RECTS,
  zoneIndexOfBookshelf,
  zoneLabel,
} from './zones';

describe('zoneIndexOfBookshelf', () => {
  it('책장 번호를 평면도 배치대로 담당 구역에 매핑한다', () => {
    // 평면도는 좌→우로 KDC가 내려간다 (Z3 앞 800 / Z2 앞 200·100 / Z1 앞 000)
    expect(zoneIndexOfBookshelf('000')).toBe(0); // Z1
    expect(zoneIndexOfBookshelf('100')).toBe(1); // Z2
    expect(zoneIndexOfBookshelf('200')).toBe(1); // Z2
    expect(zoneIndexOfBookshelf('300')).toBe(1); // Z2
    expect(zoneIndexOfBookshelf('400')).toBe(1); // Z2
    expect(zoneIndexOfBookshelf('500')).toBe(2); // Z3
    expect(zoneIndexOfBookshelf('800')).toBe(2); // Z3
    expect(zoneIndexOfBookshelf('900')).toBe(2); // Z3
  });

  it('목록에 없는 책장 번호는 null을 반환한다', () => {
    expect(zoneIndexOfBookshelf('123')).toBeNull();
    expect(zoneIndexOfBookshelf('')).toBeNull();
  });

  it('000~900이 모두 한 구역에만 배정돼 있다', () => {
    expect(ZONE_BOOKSHELVES).toHaveLength(ZONE_CODES.length);
    const all = ZONE_BOOKSHELVES.flat();
    expect([...all].sort()).toEqual(
      Array.from({ length: 10 }, (_, i) => `${i}00`.padStart(3, '0')).sort(),
    );
  });
});

describe('zoneLabel', () => {
  it('구역 인덱스를 코드 번호와 같은 순서로 표시한다', () => {
    ZONE_CODES.forEach((code, index) => {
      expect(zoneLabel(index)).toBe(`${code.replace('Z', '')}구역`);
    });
  });
});

describe('평면도 좌표', () => {
  it('구역 수와 이름·코드 수가 맞는다', () => {
    expect(ZONE_RECTS).toHaveLength(ZONE_CODES.length);
    expect(ZONE_NAMES).toHaveLength(ZONE_CODES.length);
  });

  it('모든 구역이 그림 안에 있다 (% 좌표)', () => {
    ZONE_RECTS.forEach((rect) => {
      expect(rect.left).toBeGreaterThanOrEqual(0);
      expect(rect.top).toBeGreaterThanOrEqual(0);
      expect(rect.left + rect.width).toBeLessThanOrEqual(100);
      expect(rect.top + rect.height).toBeLessThanOrEqual(100);
    });
  });

  it('구역끼리 겹치지 않는다 — 겹치면 클릭 지점이 어느 구역인지 갈린다', () => {
    ZONE_RECTS.forEach((a, i) => {
      ZONE_RECTS.slice(i + 1).forEach((b) => {
        const overlapX = a.left < b.left + b.width && b.left < a.left + a.width;
        const overlapY = a.top < b.top + b.height && b.top < a.top + a.height;
        expect(overlapX && overlapY).toBe(false);
      });
    });
  });

  it('통로와 대기 지점은 구역 밖(구역 위쪽 여백)에 있다', () => {
    const topmostZone = Math.min(...ZONE_RECTS.map((rect) => rect.top));
    expect(CORRIDOR_Y).toBeLessThan(topmostZone);
    expect(START_POSITION.y).toBeLessThan(topmostZone);
  });
});

describe('MAP_LANDMARKS', () => {
  const containsPoint = (rect: (typeof ZONE_RECTS)[number], point: { x: number; y: number }) =>
    point.x >= rect.left &&
    point.x <= rect.left + rect.width &&
    point.y >= rect.top &&
    point.y <= rect.top + rect.height;

  /**
   * 정차점은 장애물(서가·테이블) 밖의 바닥이어야 한다 — 장애물 위면 실물 카트가 서지 못하고
   * Nav2가 goal을 거부한다. 자유 좌표 이동이라 구역 밖 흰 바닥은 허용된다(사서 테이블 정차점).
   * 좌표를 옮기다 장애물 위로 올라가면 여기서 잡는다.
   */
  it('정차점이 그림 안이고 어떤 장애물 위도 아니다', () => {
    MAP_LANDMARKS.forEach((landmark) => {
      expect(landmark.stop.x).toBeGreaterThanOrEqual(0);
      expect(landmark.stop.x).toBeLessThanOrEqual(100);
      expect(landmark.stop.y).toBeGreaterThanOrEqual(0);
      expect(landmark.stop.y).toBeLessThanOrEqual(100);
      MAP_LANDMARKS.forEach((obstacle) => {
        expect(
          containsPoint(obstacle.rect, landmark.stop),
          `${landmark.name}의 정차점이 ${obstacle.name} 위에 있습니다`,
        ).toBe(false);
      });
    });
  });

  it('서가 정차점은 그 서가가 보는 통로(구역) 안에 있다', () => {
    MAP_LANDMARKS.filter((landmark) => landmark.arrival === 'zone').forEach((landmark) => {
      const inside = ZONE_RECTS.some((rect) => containsPoint(rect, landmark.stop));
      expect(inside, `${landmark.name}의 정차점이 통로 밖입니다`).toBe(true);
    });
  });

  it('클릭 영역이 그림 안에 있고 구역과 겹치지 않는다', () => {
    MAP_LANDMARKS.forEach(({ name, rect }) => {
      expect(rect.left).toBeGreaterThanOrEqual(0);
      expect(rect.top).toBeGreaterThanOrEqual(0);
      expect(rect.left + rect.width).toBeLessThanOrEqual(100);
      expect(rect.top + rect.height).toBeLessThanOrEqual(100);
      ZONE_RECTS.forEach((zone) => {
        const overlapX = rect.left < zone.left + zone.width && zone.left < rect.left + rect.width;
        const overlapY = rect.top < zone.top + zone.height && zone.top < rect.top + rect.height;
        expect(overlapX && overlapY, `${name} 클릭 영역이 구역과 겹칩니다`).toBe(false);
      });
    });
  });
});
