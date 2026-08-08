import { useEffect } from 'react';

import { useZoneStore } from './zoneStore';

import { useListShelfZones } from '@/shared/api/generated/maps/maps';
import { useToastStore } from '@/shared/ui/toast/toastStore';

/**
 * 책장 구역 목록 동기화 훅 (MAP-02).
 *
 * 구역이 그림 위 어디인지는 번들 평면도(zones.ts)가 정하므로, 서버 응답에서 가져오는 것은
 * **구역 코드에 대응하는 id**뿐이다. 이 id가 있어야 이동 명령(NAV-01)을 보낼 수 있다.
 * 코드가 어긋나면 그 구역만 지정 불가 상태로 남기고 사유를 알린다 —
 * 서버 구역과 평면도가 다른 방을 가리키는 상황을 조용히 넘기면 사서가 틀린 자리를 누른다.
 */
export function useShelfZones(mapId: number | null): void {
  const applyServerZones = useZoneStore((state) => state.applyServerZones);
  // 지도를 못 불러와도 화면 전체가 죽지 않도록 던지지 않는다 (useCartMapEvents와 같은 방침)
  const { data, isError } = useListShelfZones(mapId ?? 0, {
    query: { enabled: mapId != null, throwOnError: false },
  });

  useEffect(() => {
    if (!data) {
      return;
    }
    const { missing, unplaced } = applyServerZones(data);
    if (missing.length > 0) {
      useToastStore
        .getState()
        .show(`서버에 없는 구역이 있어요(${missing.join('·')}). 그 구역은 지정할 수 없어요`);
    } else if (unplaced.length > 0) {
      // 평면도에 자리가 없는 서버 구역 — 지도에 그릴 수 없다는 사실만 조용히 알린다
      useToastStore.getState().show(`지도에 표시할 수 없는 구역이 있어요(${unplaced.join('·')})`);
    }
  }, [data, applyServerZones]);

  useEffect(() => {
    if (isError) {
      useToastStore.getState().show('구역 정보를 불러오지 못했어요. 목적지를 지정할 수 없어요');
    }
  }, [isError]);
}
