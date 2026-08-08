import { create } from 'zustand';

import { ZONE_CODES, ZONE_NAMES, ZONE_RECTS } from './zones';

import type { MapPercent } from './mapTransform';
import type { ZoneRect } from './zones';
import type { ShelfZone } from '@/shared/api/generated/model';

/**
 * 화면에서 쓰는 구역 하나.
 *
 * 위치·이름은 번들 평면도(zones.ts)가 정하고, **id만 서버(MAP-02)에서 온다.**
 * 그림을 FE가 그리므로 "어디"는 FE가 알고, 이동 명령에 실을 DB id는 BE만 아는 값이다.
 */
export interface MapZone {
  /**
   * 서버 shelf_zone.id — 이동 명령(NAV-01)에 그대로 싣는다.
   * null이면 서버 구역 목록에 이 코드가 없어 **목적지로 지정할 수 없다**.
   */
  id: number | null;
  /** 구역 코드 (예: "Z1") — 서버 구역과 짝을 맞추는 키 */
  code: string;
  name: string;
  /** 평면도 위 클릭 영역 (%) */
  rect: ZoneRect;
  /** 구역 중심 (%) — 카트 정차 지점 */
  center: MapPercent;
}

/**
 * 번들 평면도가 정한 구역 목록. id는 아직 없다 —
 * MAP-02 응답이 오면 코드가 같은 서버 구역의 id로 채운다(applyServerZones).
 */
export const PLAN_ZONES: readonly MapZone[] = ZONE_RECTS.map((rect, index) => ({
  id: null,
  code: ZONE_CODES[index],
  name: ZONE_NAMES[index],
  rect,
  center: { x: rect.left + rect.width / 2, y: rect.top + rect.height / 2 },
}));

/** applyServerZones가 알려주는 짝 맞추기 결과 — 어긋난 코드를 화면이 알릴 수 있게 한다 */
export interface ZoneMatchResult {
  /** 평면도에는 있는데 서버 목록에 없는 코드 — 그 구역은 목적지로 지정할 수 없다 */
  missing: string[];
  /** 서버에는 있는데 평면도에 자리가 없는 코드 — 그림에 그려지지 않는다 */
  unplaced: string[];
}

interface ZoneState {
  /** 현재 화면이 쓰는 구역 목록 (코드 오름차순 = 평면도 순서) */
  zones: readonly MapZone[];
  /** 서버 id가 채워졌는지 — false면 아직 목적지를 지정할 수 없다 */
  isFromServer: boolean;
  /** MAP-02 응답 반영 — 코드가 같은 구역의 id를 채운다 (useShelfZones가 호출) */
  applyServerZones: (serverZones: readonly ShelfZone[]) => ZoneMatchResult;
  /** 평면도 구역으로 되돌린다 — 테스트 정리용 */
  resetZones: () => void;
}

/**
 * 지도 구역 목록 스토어.
 * 구역은 카트 위치 판정·목적지 지정·책장 매핑이 모두 참조하는 값이라
 * 화면 밖(cartMapStore, MSW)에서도 읽을 수 있도록 스토어에 둔다.
 */
export const useZoneStore = create<ZoneState>()((set) => ({
  zones: PLAN_ZONES,
  isFromServer: false,
  applyServerZones: (serverZones) => {
    const byCode = new Map(serverZones.map((zone) => [zone.code, zone]));
    const zones = PLAN_ZONES.map((zone) => {
      const server = byCode.get(zone.code);
      return server === undefined ? zone : { ...zone, id: server.id };
    });
    set({ zones, isFromServer: true });
    const planCodes = new Set(PLAN_ZONES.map((zone) => zone.code));
    return {
      missing: PLAN_ZONES.filter((zone) => !byCode.has(zone.code)).map((zone) => zone.code),
      unplaced: serverZones.filter((zone) => !planCodes.has(zone.code)).map((zone) => zone.code),
    };
  },
  resetZones: () => set({ zones: PLAN_ZONES, isFromServer: false }),
}));

/** 화면에서 구역 이름만 구독한다 — 구역 목록이 바뀔 때만 다시 그린다 */
export function useZoneName(zoneIndex: number | null): string {
  return useZoneStore((state) => (zoneIndex === null ? '' : (state.zones[zoneIndex]?.name ?? '')));
}

/** 훅 밖(스토어·MSW)에서 현재 구역 목록을 읽는다 */
export function currentZones(): readonly MapZone[] {
  return useZoneStore.getState().zones;
}

/** 구역 인덱스(0-base) → 서버 shelf_zone.id. 범위 밖이거나 서버 구역을 못 찾았으면 null */
export function zoneIdOf(zoneIndex: number): number | null {
  return currentZones()[zoneIndex]?.id ?? null;
}

/** 서버 shelf_zone.id → 구역 인덱스(0-base). 목록에 없는 id는 null */
export function zoneIndexOf(zoneId: number): number | null {
  const index = currentZones().findIndex((zone) => zone.id === zoneId);
  return index === -1 ? null : index;
}

/** 점에서 사각형까지의 거리 (% 단위). 사각형 안이면 0 */
function distanceToRect(point: MapPercent, rect: ZoneRect): number {
  const dx = Math.max(rect.left - point.x, 0, point.x - (rect.left + rect.width));
  const dy = Math.max(rect.top - point.y, 0, point.y - (rect.top + rect.height));
  return Math.hypot(dx, dy);
}

/**
 * 지도 % 좌표에서 가장 가까운 구역 인덱스(0-base). 구역 목록이 비었으면 null.
 *
 * 서가·테이블처럼 어느 구역에도 속하지 않는 지점을 눌렀을 때 쓴다. **목적지를 정하는 값이 아니다** —
 * 카트가 실제로 갈 자리는 함께 보내는 클릭 좌표로 BE가 정한다(이동 불가 지점이면 가장 가까운
 * 이동 가능 지점으로 스냅). 이 값은 NAV-01의 필수 필드 `zoneId`를 채우기 위한 것이다.
 * BE가 스냅한 지점이 여기서 고른 구역과 다를 수 있다.
 */
export function nearestZoneIndex(point: MapPercent): number | null {
  const zones = currentZones();
  if (zones.length === 0) {
    return null;
  }
  let nearest = 0;
  let shortest = Infinity;
  zones.forEach((zone, index) => {
    const distance = distanceToRect(point, zone.rect);
    if (distance < shortest) {
      shortest = distance;
      nearest = index;
    }
  });
  return nearest;
}

/** 지도 % 좌표가 속한 구역 인덱스(0-base). 어느 구역에도 없으면(통로·서가·테이블) null */
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
