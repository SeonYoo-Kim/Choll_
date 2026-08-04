import { create } from 'zustand';

import { ZONE_NAMES, ZONE_RECTS } from './zones';

import type { MapPercent } from './mapTransform';
import type { MapZone } from './shelfZoneBoundary';

/**
 * 서버 구역(MAP-02)을 받기 전까지 쓰는 데모 구역 — assets/map.png 평면도 기준 Z1~Z7.
 * id는 1-base로 두어 MSW 픽스처·초안 스펙과 맞춘다.
 */
export const DEMO_ZONES: readonly MapZone[] = ZONE_RECTS.map((rect, index) => ({
  id: index + 1,
  code: `Z${index + 1}`,
  name: ZONE_NAMES[index],
  rect,
  center: { x: rect.left + rect.width / 2, y: rect.top + rect.height / 2 },
}));

interface ZoneState {
  /** 현재 화면이 쓰는 구역 목록 (코드 오름차순). 서버 응답 전에는 데모 구역 */
  zones: readonly MapZone[];
  /** 서버 구역으로 교체됐는지 — false면 아직 데모 구역이라 실제 지도와 다를 수 있다 */
  isFromServer: boolean;
  /** MAP-02 응답 반영 (useShelfZones가 호출) */
  setZones: (zones: readonly MapZone[]) => void;
  /** 데모 구역으로 되돌린다 — 테스트 정리용 */
  resetZones: () => void;
}

/**
 * 지도 구역 목록 스토어.
 * 구역은 카트 위치 판정·목적지 지정·책장 매핑이 모두 참조하는 값이라
 * 화면 밖(cartMapStore, MSW)에서도 읽을 수 있도록 스토어에 둔다.
 */
export const useZoneStore = create<ZoneState>()((set) => ({
  zones: DEMO_ZONES,
  isFromServer: false,
  setZones: (zones) => set({ zones, isFromServer: true }),
  resetZones: () => set({ zones: DEMO_ZONES, isFromServer: false }),
}));

/** 화면에서 구역 이름만 구독한다 — 구역 목록이 바뀔 때만 다시 그린다 */
export function useZoneName(zoneIndex: number | null): string {
  return useZoneStore((state) => (zoneIndex === null ? '' : (state.zones[zoneIndex]?.name ?? '')));
}

/** 훅 밖(스토어·MSW)에서 현재 구역 목록을 읽는다 */
export function currentZones(): readonly MapZone[] {
  return useZoneStore.getState().zones;
}

/** 구역 인덱스(0-base) → 서버 shelf_zone.id. 범위 밖이면 null */
export function zoneIdOf(zoneIndex: number): number | null {
  return currentZones()[zoneIndex]?.id ?? null;
}

/** 서버 shelf_zone.id → 구역 인덱스(0-base). 목록에 없는 id는 null */
export function zoneIndexOf(zoneId: number): number | null {
  const index = currentZones().findIndex((zone) => zone.id === zoneId);
  return index === -1 ? null : index;
}

/** 지도 % 좌표가 속한 구역 인덱스(0-base). 어느 구역에도 없으면(통로·출발 지점 등) null */
export function zoneIndexOfPoint(point: MapPercent): number | null {
  const index = currentZones().findIndex(
    ({ rect }) =>
      point.x >= rect.left &&
      point.x <= rect.left + rect.width &&
      point.y >= rect.top &&
      point.y <= rect.top + rect.height,
  );
  return index === -1 ? null : index;
}

/** 구역 인덱스(0-base) → 구역 이름. 범위 밖이면 빈 문자열 */
export function zoneNameOf(zoneIndex: number): string {
  return currentZones()[zoneIndex]?.name ?? '';
}

/** 구역 인덱스(0-base) → 카트 정차 좌표(%). 범위 밖이면 null */
export function zoneCenterOf(zoneIndex: number): MapPercent | null {
  return currentZones()[zoneIndex]?.center ?? null;
}
