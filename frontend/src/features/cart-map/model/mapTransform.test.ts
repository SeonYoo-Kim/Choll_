import { describe, expect, it } from 'vitest';

import { toMapPercent, toSlamPosition } from './mapTransform';

import type { MapInfo } from '@/shared/api/generated/model';

const mapInfo: MapInfo = {
  id: 1,
  name: 'test',
  imageUrl: '/map.png',
  resolution: 0.05, // 1000px × 0.05 = 50m, 800px × 0.05 = 40m
  originX: -10,
  originY: -5,
  imageWidth: 1000,
  imageHeight: 800,
};

describe('toMapPercent', () => {
  it('SLAM 원점은 이미지 좌하단(x=0%, y=100%)으로 변환된다', () => {
    expect(toMapPercent({ x: -10, y: -5 }, mapInfo)).toEqual({ x: 0, y: 100 });
  });

  it('지도 중앙 좌표는 (50%, 50%)로 변환된다', () => {
    expect(toMapPercent({ x: 15, y: 15 }, mapInfo)).toEqual({ x: 50, y: 50 });
  });

  it('y축은 반전된다 (SLAM y 증가 = 이미지 위쪽)', () => {
    const top = toMapPercent({ x: 0, y: 35 }, mapInfo);
    const bottom = toMapPercent({ x: 0, y: -5 }, mapInfo);
    expect(top.y).toBeLessThan(bottom.y);
  });
});

describe('toSlamPosition', () => {
  it('toMapPercent와 왕복 변환하면 원래 좌표로 돌아온다', () => {
    const original = { x: 42.5, y: 61.2 };
    const roundTrip = toMapPercent(toSlamPosition(original, mapInfo), mapInfo);
    expect(roundTrip.x).toBeCloseTo(original.x, 6);
    expect(roundTrip.y).toBeCloseTo(original.y, 6);
  });
});
