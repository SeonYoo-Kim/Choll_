import type { MapInfo } from '@/shared/api/generated/model';

/** 지도 이미지 위 좌표 (% 단위, 좌상단 기준) — 화면 렌더링용 */
export interface MapPercent {
  x: number;
  y: number;
}

/** WS 명세(WS-FE-01)의 X·Y 표시 좌표 — 지도 이미지 픽셀 단위, 좌상단 원점으로 해석 */
export interface DisplayPosition {
  x: number;
  y: number;
}

/**
 * 표시 좌표(px)를 지도 이미지 %로 변환한다.
 * 지도 이미지 크기(imageWidth/imageHeight)가 기준이므로 화면 배율과 무관하게 동작한다.
 * TODO: "표시 좌표"의 정확한 단위(px vs m)는 BE 구현 시 확정 필요.
 */
export function displayToPercent(position: DisplayPosition, mapInfo: MapInfo): MapPercent {
  return {
    x: (position.x / mapInfo.imageWidth) * 100,
    y: (position.y / mapInfo.imageHeight) * 100,
  };
}

/** displayToPercent의 역변환. MSW 시뮬레이터가 %로 정의된 구역 좌표를 표시 좌표로 내보낼 때 쓴다. */
export function percentToDisplay(percent: MapPercent, mapInfo: MapInfo): DisplayPosition {
  return {
    x: (percent.x / 100) * mapInfo.imageWidth,
    y: (percent.y / 100) * mapInfo.imageHeight,
  };
}
