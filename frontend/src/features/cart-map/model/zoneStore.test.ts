import { afterEach, describe, expect, it } from 'vitest';

import { ZONE_CODES } from './zones';
import {
  PLAN_ZONES,
  nearestZoneIndex,
  useZoneStore,
  zoneIdOf,
  zoneIndexOf,
  zoneIndexOfPoint,
  zoneNameOf,
} from './zoneStore';

import type { ShelfZone } from '@/shared/api/generated/model';

/** 서버 구역 응답 — id는 DB가 정하므로 1-base가 아니고, 순서·이름도 평면도와 다를 수 있다 */
const serverZone = (id: number, code: string): ShelfZone => ({
  id,
  mapId: 2,
  code,
  name: `${code} 서버 이름`,
  boundaryData: '[[0,0],[10,0],[10,10],[0,10]]',
});

afterEach(() => {
  useZoneStore.getState().resetZones();
});

describe('zoneStore', () => {
  it('서버 구역을 받기 전에는 평면도 구역을 쓰고 id가 비어 있다', () => {
    expect(useZoneStore.getState().zones).toEqual(PLAN_ZONES);
    expect(useZoneStore.getState().isFromServer).toBe(false);
    expect(zoneIdOf(0)).toBeNull();
  });

  it('코드가 같은 서버 구역의 id를 채운다', () => {
    const result = useZoneStore
      .getState()
      .applyServerZones([serverZone(57, 'Z2'), serverZone(41, 'Z1'), serverZone(63, 'Z3')]);

    expect(useZoneStore.getState().isFromServer).toBe(true);
    expect(zoneIdOf(0)).toBe(41);
    expect(zoneIdOf(1)).toBe(57);
    expect(zoneIndexOf(41)).toBe(0);
    expect(zoneIndexOf(57)).toBe(1);
    expect(result).toEqual({ missing: [], unplaced: [] });
  });

  it('위치·이름은 평면도 값을 유지한다 — 서버 좌표는 다른 그림 기준이다', () => {
    useZoneStore.getState().applyServerZones(ZONE_CODES.map((code, i) => serverZone(i + 10, code)));

    expect(useZoneStore.getState().zones.map((zone) => zone.rect)).toEqual(
      PLAN_ZONES.map((zone) => zone.rect),
    );
    expect(zoneNameOf(0)).toBe(PLAN_ZONES[0].name);
  });

  it('평면도에 있는 코드가 서버에 없으면 id를 비운 채 알린다', () => {
    const result = useZoneStore.getState().applyServerZones([serverZone(41, 'Z1')]);

    expect(result.missing).toEqual(['Z2', 'Z3']);
    expect(zoneIdOf(0)).toBe(41);
    expect(zoneIdOf(1)).toBeNull();
  });

  it('평면도에 자리가 없는 서버 구역은 그리지 않고 알린다', () => {
    const result = useZoneStore
      .getState()
      .applyServerZones([
        ...ZONE_CODES.map((code, i) => serverZone(i + 1, code)),
        serverZone(9, 'Z7'),
      ]);

    expect(result.unplaced).toEqual(['Z7']);
    expect(useZoneStore.getState().zones).toHaveLength(PLAN_ZONES.length);
  });

  it('목록에 없는 id나 범위 밖 인덱스는 null', () => {
    useZoneStore.getState().applyServerZones([serverZone(41, 'Z1')]);
    expect(zoneIndexOf(999)).toBeNull();
    expect(zoneIdOf(5)).toBeNull();
    expect(zoneNameOf(5)).toBe('');
  });

  it('좌표가 속한 구역을 찾고, 통로 밖이면 null', () => {
    // 평면도 구역 중심은 반드시 그 구역 안에 있다
    PLAN_ZONES.forEach((zone, index) => {
      expect(zoneIndexOfPoint(zone.center)).toBe(index);
    });
    // 서가·테이블이 있는 위쪽 여백은 어느 구역에도 속하지 않는다
    expect(zoneIndexOfPoint({ x: 50, y: 5 })).toBeNull();
  });

  describe('nearestZoneIndex', () => {
    it('구역 안의 점은 그 구역을 준다', () => {
      PLAN_ZONES.forEach((zone, index) => {
        expect(nearestZoneIndex(zone.center)).toBe(index);
      });
    });

    it('구역 사이 서가 위의 점은 더 가까운 쪽 구역을 준다', () => {
      // 3구역(x 4.1~21.0)과 2구역(x 37.0~54.1) 사이 — 왼쪽에 붙은 점
      expect(nearestZoneIndex({ x: 25, y: 50 })).toBe(2);
      // 같은 틈에서 오른쪽에 붙은 점
      expect(nearestZoneIndex({ x: 34, y: 50 })).toBe(1);
    });

    it('구역 위쪽 테이블 영역은 바로 아래 구역을 준다', () => {
      // 1구역(x 70.1~86.2) 바로 위 — 가로로는 구역 안이라 세로 거리만 남는다
      expect(nearestZoneIndex({ x: 78, y: 5 })).toBe(0);
    });

    it('구역 목록이 비면 null', () => {
      useZoneStore.setState({ zones: [] });
      expect(nearestZoneIndex({ x: 50, y: 50 })).toBeNull();
    });
  });
});
