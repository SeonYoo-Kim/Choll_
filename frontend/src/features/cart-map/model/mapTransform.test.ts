import { describe, expect, it } from 'vitest';

import { displayToPercent, percentToDisplay } from './mapTransform';

import type { MapInfo } from '@/shared/api/generated/model';

const mapInfo: MapInfo = {
  id: 1,
  name: 'test',
  imageUrl: '/map.png',
  resolution: 0.05,
  originX: 0,
  originY: 0,
  imageWidth: 1000,
  imageHeight: 800,
};

describe('displayToPercent', () => {
  it('이미지 좌상단(0,0)은 (0%, 0%)로 변환된다', () => {
    expect(displayToPercent({ x: 0, y: 0 }, mapInfo)).toEqual({ x: 0, y: 0 });
  });

  it('이미지 우하단(1000,800)은 (100%, 100%)로 변환된다', () => {
    expect(displayToPercent({ x: 1000, y: 800 }, mapInfo)).toEqual({ x: 100, y: 100 });
  });

  it('이미지 중앙은 (50%, 50%)로 변환된다', () => {
    expect(displayToPercent({ x: 500, y: 400 }, mapInfo)).toEqual({ x: 50, y: 50 });
  });
});

describe('percentToDisplay', () => {
  it('displayToPercent와 왕복 변환하면 원래 좌표로 돌아온다', () => {
    const original = { x: 42.5, y: 61.2 };
    const roundTrip = displayToPercent(percentToDisplay(original, mapInfo), mapInfo);
    expect(roundTrip.x).toBeCloseTo(original.x, 6);
    expect(roundTrip.y).toBeCloseTo(original.y, 6);
  });
});
