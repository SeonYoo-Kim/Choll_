import mapImage from '@/assets/map.png';

/**
 * 지도 화면의 바탕 그림 — **번들된 평면도를 쓴다.**
 *
 * BE는 MAP-01 응답에 SLAM 지도 그림 주소(`imageUrl`)를 주지만 그 그림을 띄우지 않는다.
 * SLAM 점유격자를 그대로 렌더한 그림은 사서가 읽기 어려워, 같은 방을 사람이 알아보게 그린
 * 평면도로 대체했다(2026-08-06).
 *
 * ## 좌표 계약은 그대로다
 *
 * FE↔BE가 주고받는 좌표(WS 위치, NAV-01 클릭 지점)는 여전히 **BE 지도 이미지 픽셀**이다.
 * 화면은 좌표를 항상 "그림 폭·높이의 몇 %"로 환산해 쓰므로(mapTransform), 이 평면도의
 * 해상도나 가로세로 비율이 BE 지도 메타와 달라도 계약은 깨지지 않는다.
 *
 * 대신 지켜야 할 전제가 하나 있다 — **이 평면도와 BE 지도가 같은 바닥 범위를 그려야 한다.**
 * 한쪽에만 여백이 더 있거나 방향이 다르면 카트 마커와 목적지가 그만큼 밀린다.
 * 평면도를 교체할 때는 zones.ts의 구역 좌표와 함께, BE `library_maps` 행의
 * width·height·origin·resolution이 같은 범위를 가리키는지 확인할 것.
 */
export const FLOOR_PLAN_IMAGE: string = mapImage;

/**
 * 평면도 원본 픽셀 크기 — 지도 영역의 가로세로 비율을 이 값에 맞춘다.
 * 비율이 어긋나면 `object-fit: cover`가 그림을 잘라내고, 잘린 만큼 클릭 지점이 실제와 달라진다.
 */
export const FLOOR_PLAN_SIZE: { width: number; height: number } = { width: 1707, height: 921 };
