import { displayToPercent } from './mapTransform';

import type { DisplayPosition, MapPercent } from './mapTransform';
import type { ZoneRect } from './zones';
import type { MapInfo, ShelfZone } from '@/shared/api/generated/model';

/**
 * 화면에서 쓸 구역 하나 — MAP-02 응답(ShelfZone)을 지도 % 좌표까지 풀어놓은 형태.
 * 카트 위치(WS-FE-01)와 같은 좌표계를 쓰므로 displayToPercent로 함께 변환한다.
 */
export interface MapZone {
  /** 서버 shelf_zone.id — 이동 명령(NAV-01)에 그대로 싣는다 */
  id: number;
  /** 구역 코드 (예: "Z1") — 목록 정렬 기준이자 책장 매핑의 키 */
  code: string;
  name: string;
  /** 지도 이미지 위 클릭 영역 (%) */
  rect: ZoneRect;
  /** 구역 중심 (%) — 카트 정차 지점 */
  center: MapPercent;
}

/**
 * boundaryData 파싱. BE는 구역 경계를 폴리곤(꼭짓점을 이어 만든 도형)의
 * JSON 문자열로 준다 — `"[[x,y],[x,y],...]"`, 지도 이미지 픽셀·좌상단 원점.
 * 문자열이 깨졌거나 꼭짓점이 3개 미만이면 도형이 되지 않으므로 null.
 */
export function parseBoundaryPoints(boundaryData: string): DisplayPosition[] | null {
  let parsed: unknown;
  try {
    parsed = JSON.parse(boundaryData);
  } catch {
    return null;
  }
  if (!Array.isArray(parsed) || parsed.length < 3) {
    return null;
  }
  const points: DisplayPosition[] = [];
  for (const point of parsed) {
    if (!Array.isArray(point) || point.length < 2) {
      return null;
    }
    const [x, y] = point as unknown[];
    if (typeof x !== 'number' || typeof y !== 'number' || !isFinite(x) || !isFinite(y)) {
      return null;
    }
    points.push({ x, y });
  }
  return points;
}

/**
 * 폴리곤을 감싸는 사각형을 지도 % 좌표로 구한다.
 * 화면은 구역을 사각형 버튼으로 그리므로 폴리곤 그대로가 아니라 외접 사각형을 쓴다
 * (시드 데이터의 구역은 모두 축에 나란한 사각형이라 현재는 손실이 없다).
 */
export function boundingRectPercent(points: DisplayPosition[], mapInfo: MapInfo): ZoneRect {
  const topLeft = displayToPercent(
    { x: Math.min(...points.map((p) => p.x)), y: Math.min(...points.map((p) => p.y)) },
    mapInfo,
  );
  const bottomRight = displayToPercent(
    { x: Math.max(...points.map((p) => p.x)), y: Math.max(...points.map((p) => p.y)) },
    mapInfo,
  );
  return {
    left: topLeft.x,
    top: topLeft.y,
    width: bottomRight.x - topLeft.x,
    height: bottomRight.y - topLeft.y,
  };
}

/**
 * MAP-02 응답을 화면용 구역 목록으로 변환한다.
 * 경계가 깨진 구역은 건너뛰고, 코드 오름차순(Z1, Z2 …)으로 정렬한다 —
 * 화면과 책장 매핑이 구역 순서(인덱스)에 기대므로 서버 응답 순서에 좌우되면 안 된다.
 */
export function toMapZones(zones: readonly ShelfZone[], mapInfo: MapInfo): MapZone[] {
  // 이미지 크기가 0이면 % 변환이 Infinity가 된다 — 지도 메타가 덜 채워진 상태
  if (!mapInfo.imageWidth || !mapInfo.imageHeight) {
    return [];
  }
  return zones
    .map((zone) => {
      const points = parseBoundaryPoints(zone.boundaryData);
      if (points === null) {
        return null;
      }
      const rect = boundingRectPercent(points, mapInfo);
      return {
        id: zone.id,
        code: zone.code,
        name: zone.name,
        rect,
        center: { x: rect.left + rect.width / 2, y: rect.top + rect.height / 2 },
      } satisfies MapZone;
    })
    .filter((zone): zone is MapZone => zone !== null)
    .sort((a, b) => a.code.localeCompare(b.code));
}
