import type { CartPosition, MapInfo } from '@/shared/api/generated/model';

/** 지도 이미지 위 좌표 (% 단위, 좌상단 기준) */
export interface MapPercent {
  x: number;
  y: number;
}

/**
 * SLAM 좌표(m, 좌하단 원점·y 위쪽 증가)를 지도 이미지 %(좌상단 원점·y 아래쪽 증가)로 변환한다.
 * 축 방향(y 반전)은 ROS 지도 관례 기준 초안 — BE와 좌표계 합의 시 재확인 필요.
 */
export function toMapPercent(position: CartPosition, mapInfo: MapInfo): MapPercent {
  const widthM = mapInfo.imageWidth * mapInfo.resolution;
  const heightM = mapInfo.imageHeight * mapInfo.resolution;
  return {
    x: ((position.x - mapInfo.originX) / widthM) * 100,
    y: (1 - (position.y - mapInfo.originY) / heightM) * 100,
  };
}

/** toMapPercent의 역변환. MSW 시뮬레이터가 %로 정의된 구역 좌표를 SLAM 좌표로 내보낼 때 쓴다. */
export function toSlamPosition(percent: MapPercent, mapInfo: MapInfo): CartPosition {
  const widthM = mapInfo.imageWidth * mapInfo.resolution;
  const heightM = mapInfo.imageHeight * mapInfo.resolution;
  return {
    x: mapInfo.originX + (percent.x / 100) * widthM,
    y: mapInfo.originY + (1 - percent.y / 100) * heightM,
  };
}
