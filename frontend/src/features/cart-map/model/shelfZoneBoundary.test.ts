import { describe, expect, it } from 'vitest';

import { boundingRectPercent, parseBoundaryPoints, toMapZones } from './shelfZoneBoundary';

import type { MapInfo, ShelfZone } from '@/shared/api/generated/model';

/** 계산을 눈으로 검산할 수 있게 1000x500 지도를 쓴다 (100px = 가로 10%, 세로 20%) */
const mapInfo: MapInfo = {
  id: 1,
  name: '테스트 지도',
  imageUrl: '/map.png',
  resolution: 0.05,
  originX: 0,
  originY: 0,
  imageWidth: 1000,
  imageHeight: 500,
};

const zone = (id: number, code: string, boundaryData: string): ShelfZone => ({
  id,
  mapId: 1,
  code,
  name: `${code} 구역`,
  boundaryData,
});

/** 좌상단 (100,100) ~ 우하단 (300,200) 사각형 */
const RECT_BOUNDARY = '[[100,100],[300,100],[300,200],[100,200]]';

describe('parseBoundaryPoints', () => {
  it('꼭짓점 목록 JSON을 좌표 배열로 읽는다', () => {
    expect(parseBoundaryPoints(RECT_BOUNDARY)).toEqual([
      { x: 100, y: 100 },
      { x: 300, y: 100 },
      { x: 300, y: 200 },
      { x: 100, y: 200 },
    ]);
  });

  it('JSON이 아니면 null', () => {
    expect(parseBoundaryPoints('구역1')).toBeNull();
    expect(parseBoundaryPoints('')).toBeNull();
  });

  it('꼭짓점이 3개 미만이면 도형이 아니므로 null', () => {
    expect(parseBoundaryPoints('[[0,0],[10,10]]')).toBeNull();
    expect(parseBoundaryPoints('[]')).toBeNull();
  });

  it('좌표가 숫자가 아니거나 짝이 안 맞으면 null', () => {
    expect(parseBoundaryPoints('[[0,0],[10,"x"],[20,20]]')).toBeNull();
    expect(parseBoundaryPoints('[[0,0],[10],[20,20]]')).toBeNull();
    expect(parseBoundaryPoints('[0,10,20]')).toBeNull();
  });
});

describe('boundingRectPercent', () => {
  it('폴리곤을 감싸는 사각형을 % 좌표로 준다', () => {
    const points = parseBoundaryPoints(RECT_BOUNDARY);
    expect(points).not.toBeNull();
    expect(boundingRectPercent(points!, mapInfo)).toEqual({
      left: 10,
      top: 20,
      width: 20,
      height: 20,
    });
  });

  it('사각형이 아닌 폴리곤도 가장 바깥 꼭짓점을 기준으로 감싼다', () => {
    const points = parseBoundaryPoints('[[100,100],[300,100],[200,300]]');
    expect(boundingRectPercent(points!, mapInfo)).toEqual({
      left: 10,
      top: 20,
      width: 20,
      height: 40,
    });
  });
});

describe('toMapZones', () => {
  it('서버 응답을 화면용 구역으로 바꾸고 중심 좌표를 채운다', () => {
    const [result] = toMapZones([zone(7, 'Z1', RECT_BOUNDARY)], mapInfo);
    expect(result).toEqual({
      id: 7,
      code: 'Z1',
      name: 'Z1 구역',
      rect: { left: 10, top: 20, width: 20, height: 20 },
      center: { x: 20, y: 30 },
    });
  });

  it('서버 응답 순서와 상관없이 구역 코드 순으로 정렬한다', () => {
    const zones = toMapZones(
      [zone(3, 'Z3', RECT_BOUNDARY), zone(1, 'Z1', RECT_BOUNDARY), zone(2, 'Z2', RECT_BOUNDARY)],
      mapInfo,
    );
    expect(zones.map((z) => z.code)).toEqual(['Z1', 'Z2', 'Z3']);
  });

  it('경계가 깨진 구역은 건너뛰고 나머지는 살린다', () => {
    const zones = toMapZones([zone(1, 'Z1', RECT_BOUNDARY), zone(2, 'Z2', '깨진 값')], mapInfo);
    expect(zones.map((z) => z.code)).toEqual(['Z1']);
  });

  it('지도 이미지 크기가 없으면 % 변환이 불가능하므로 빈 목록', () => {
    expect(toMapZones([zone(1, 'Z1', RECT_BOUNDARY)], { ...mapInfo, imageWidth: 0 })).toEqual([]);
  });
});
