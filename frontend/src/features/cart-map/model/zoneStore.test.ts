import { afterEach, describe, expect, it } from 'vitest';

import {
  DEMO_ZONES,
  useZoneStore,
  zoneIdOf,
  zoneIndexOf,
  zoneIndexOfPoint,
  zoneNameOf,
} from './zoneStore';

import type { MapZone } from './shelfZoneBoundary';

/** 서버가 준 것처럼 id가 1-base가 아닌 구역 목록 */
const serverZones: MapZone[] = [
  {
    id: 41,
    code: 'Z1',
    name: '왼쪽 상단 존',
    rect: { left: 0, top: 0, width: 40, height: 20 },
    center: { x: 20, y: 10 },
  },
  {
    id: 57,
    code: 'Z2',
    name: '왼쪽 하단 존',
    rect: { left: 0, top: 60, width: 40, height: 20 },
    center: { x: 20, y: 70 },
  },
];

afterEach(() => {
  useZoneStore.getState().resetZones();
});

describe('zoneStore', () => {
  it('서버 구역을 받기 전에는 데모 구역을 쓴다', () => {
    expect(useZoneStore.getState().zones).toEqual(DEMO_ZONES);
    expect(useZoneStore.getState().isFromServer).toBe(false);
  });

  it('서버 구역으로 교체하면 그 목록을 쓴다', () => {
    useZoneStore.getState().setZones(serverZones);
    expect(useZoneStore.getState().isFromServer).toBe(true);
    expect(zoneNameOf(0)).toBe('왼쪽 상단 존');
  });

  it('서버 id가 1-base가 아니어도 인덱스와 서로 변환된다', () => {
    useZoneStore.getState().setZones(serverZones);
    expect(zoneIdOf(0)).toBe(41);
    expect(zoneIdOf(1)).toBe(57);
    expect(zoneIndexOf(41)).toBe(0);
    expect(zoneIndexOf(57)).toBe(1);
  });

  it('목록에 없는 id나 범위 밖 인덱스는 null', () => {
    useZoneStore.getState().setZones(serverZones);
    expect(zoneIndexOf(1)).toBeNull();
    expect(zoneIdOf(5)).toBeNull();
    expect(zoneNameOf(5)).toBe('');
  });

  it('좌표가 속한 구역을 찾고, 구역 밖이면 null', () => {
    useZoneStore.getState().setZones(serverZones);
    expect(zoneIndexOfPoint({ x: 20, y: 10 })).toBe(0);
    expect(zoneIndexOfPoint({ x: 20, y: 70 })).toBe(1);
    // 두 구역 사이 통로
    expect(zoneIndexOfPoint({ x: 20, y: 40 })).toBeNull();
  });
});
