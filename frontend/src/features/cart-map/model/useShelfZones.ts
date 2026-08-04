import { useEffect } from 'react';

import { toMapZones } from './shelfZoneBoundary';
import { useZoneStore } from './zoneStore';

import { useListShelfZones } from '@/shared/api/generated/maps/maps';
import { useToastStore } from '@/shared/ui/toast/toastStore';

import type { MapInfo } from '@/shared/api/generated/model';

/**
 * 책장 구역 목록 동기화 훅 (MAP-02).
 * 서버 구역을 받아 지도 % 좌표로 바꾼 뒤 zoneStore에 넣는다.
 * 받기 전이나 실패했을 때는 데모 구역이 그대로 남으므로 지도는 계속 동작한다.
 */
export function useShelfZones(mapId: number | null, mapInfo: MapInfo | undefined): void {
  const setZones = useZoneStore((state) => state.setZones);
  // 지도를 못 불러와도 화면 전체가 죽지 않도록 던지지 않는다 (useCartMapEvents와 같은 방침)
  const { data, isError } = useListShelfZones(mapId ?? 0, {
    query: { enabled: mapId != null, throwOnError: false },
  });

  useEffect(() => {
    // 지도 메타(이미지 크기)가 있어야 픽셀→% 변환을 할 수 있다
    if (!data || !mapInfo) {
      return;
    }
    const zones = toMapZones(data, mapInfo);
    if (zones.length === 0) {
      // 응답은 왔는데 경계를 하나도 못 읽은 경우 — 데모 구역을 유지하고 알린다
      useToastStore.getState().show('구역 정보를 읽지 못했어요. 임시 구역으로 표시합니다');
      return;
    }
    setZones(zones);
  }, [data, mapInfo, setZones]);

  useEffect(() => {
    if (isError) {
      useToastStore.getState().show('구역 정보를 불러오지 못했어요. 임시 구역으로 표시합니다');
    }
  }, [isError]);
}
