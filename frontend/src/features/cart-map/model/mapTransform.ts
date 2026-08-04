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

/**
 * 화면에서 누른 지점을 표시 좌표(px)로 바꾼다 — NAV-01에 클릭 지점을 실어 보낼 때 쓴다.
 *
 * `client`는 마우스 이벤트의 clientX/clientY, `bounds`는 지도 영역의 getBoundingClientRect() 값이다.
 * 지도가 화면에서 어떤 크기로 그려지든 비율로 환산하므로 배율과 무관하다.
 * 지도 영역 크기를 모르거나(0) 지도 밖을 누른 경우 null — 좌표 없이 보내면 BE가 구역 중심을 쓴다.
 */
export function clientPointToDisplay(
  client: { x: number; y: number },
  bounds: { left: number; top: number; width: number; height: number },
  mapInfo: MapInfo,
): DisplayPosition | null {
  if (bounds.width <= 0 || bounds.height <= 0) {
    return null;
  }
  const percent: MapPercent = {
    x: ((client.x - bounds.left) / bounds.width) * 100,
    y: ((client.y - bounds.top) / bounds.height) * 100,
  };
  if (percent.x < 0 || percent.x > 100 || percent.y < 0 || percent.y > 100) {
    return null;
  }
  const display = percentToDisplay(percent, mapInfo);
  // BE·시드 데이터가 정수 픽셀을 쓰므로 맞춰서 보낸다
  return { x: Math.round(display.x), y: Math.round(display.y) };
}
