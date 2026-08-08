import { describe, expect, it } from 'vitest';

import { clientPointToDisplay, displayToPercent, percentToDisplay } from './mapTransform';

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

describe('clientPointToDisplay', () => {
  // 지도가 화면에 500x400으로 그려진 상황 (실제 이미지는 1000x800이라 정확히 2배)
  const bounds = { left: 100, top: 50, width: 500, height: 400 };

  it('화면에 그려진 크기와 무관하게 지도 픽셀로 환산한다', () => {
    // 지도 영역의 정중앙을 눌렀다 → 이미지 중앙 (500, 400)
    expect(clientPointToDisplay({ x: 350, y: 250 }, bounds, mapInfo)).toEqual({ x: 500, y: 400 });
  });

  it('좌상단 모서리는 (0,0)이다', () => {
    expect(clientPointToDisplay({ x: 100, y: 50 }, bounds, mapInfo)).toEqual({ x: 0, y: 0 });
  });

  it('우하단 모서리는 이미지 크기와 같다', () => {
    expect(clientPointToDisplay({ x: 600, y: 450 }, bounds, mapInfo)).toEqual({
      x: 1000,
      y: 800,
    });
  });

  it('정수 픽셀로 반올림해서 준다', () => {
    const point = clientPointToDisplay({ x: 233, y: 177 }, bounds, mapInfo);
    expect(Number.isInteger(point?.x)).toBe(true);
    expect(Number.isInteger(point?.y)).toBe(true);
  });

  it('지도 밖을 누르면 null — 좌표 없이 보내 BE가 구역 중심을 쓰게 한다', () => {
    expect(clientPointToDisplay({ x: 99, y: 250 }, bounds, mapInfo)).toBeNull();
    expect(clientPointToDisplay({ x: 350, y: 451 }, bounds, mapInfo)).toBeNull();
  });

  it('지도 영역 크기를 모르면(0) null', () => {
    expect(
      clientPointToDisplay({ x: 0, y: 0 }, { left: 0, top: 0, width: 0, height: 0 }, mapInfo),
    ).toBeNull();
  });
});
