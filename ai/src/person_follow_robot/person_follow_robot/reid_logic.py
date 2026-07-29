"""reid_logic — reid_node의 프레임워크 독립 판정 로직.

재인식 실패 분석(2026-07-29, result10.mp4) 결과 도입된 두 가지 판정:

1. crop_quality_ok — 잘리거나 초근접인 bbox를 Memory Bank 등록/갱신과
   자동 선택 후보에서 배제한다. OSNet은 전신(128x256) 이미지로 학습된
   모델이라 몸통 조각 크롭은 뱅크를 오염시켜 재인식을 망가뜨린다.
2. accept_recovery — 재탐색 수락 판정. 임계값에 더해 1위-2위 유사도
   차이(margin)를 요구해, 비슷한 옷의 타인을 오인하는 것을 막는다.

ROS에 의존하지 않는 순수 로직이므로 pytest로 검증한다
(ai/test/test_reid_logic.py).
"""

from __future__ import annotations

from collections.abc import Sequence


def crop_quality_ok(
    center_x: float,
    center_y: float,
    width_px: float,
    height_px: float,
    image_width_px: float,
    image_height_px: float,
    side_margin_px: float = 4.0,
    max_area_fraction: float = 0.5,
) -> bool:
    """Bbox가 Re-ID 피처로 쓸 만한 크롭인지 판정한다.

    거르는 것: **좌우 가장자리에 잘린 몸**(프레임 밖으로 나가는 중)과
    **초근접**(bbox가 화면의 max_area_fraction 초과 — 몸통 조각만 보임).

    상하 접촉은 배제하지 않는다: 목표 추종 거리(1 m)에서는 전신이
    세로 화각을 넘는 것이 정상 상태라, 상하 기준으로 거르면 추종 중
    뱅크 갱신이 전부 막힌다.

    Args:
        center_x: bbox 중심 x (픽셀).
        center_y: bbox 중심 y (픽셀). (현재 판정에는 미사용, 대칭성 유지용)
        width_px: bbox 폭 (픽셀).
        height_px: bbox 높이 (픽셀).
        image_width_px: 이미지 폭 (픽셀).
        image_height_px: 이미지 높이 (픽셀).
        side_margin_px: 좌우 가장자리 접촉 판정 여유 (픽셀).
        max_area_fraction: 허용하는 bbox/이미지 면적 비율 상한.

    Returns:
        품질 기준을 통과하면 True.
    """
    if width_px <= 0.0 or height_px <= 0.0:
        return False
    if image_width_px <= 0.0 or image_height_px <= 0.0:
        return False

    half_width = width_px / 2.0
    if center_x - half_width < side_margin_px:
        return False
    if center_x + half_width > image_width_px - side_margin_px:
        return False

    area_fraction = (width_px * height_px) / (image_width_px * image_height_px)
    return area_fraction <= max_area_fraction


def accept_recovery(
    candidate_scores: Sequence[tuple[int, float]],
    similarity_threshold: float,
    margin: float = 0.05,
) -> int | None:
    """재탐색 후보 유사도 목록에서 수락할 track id를 결정한다.

    수락 조건: 최고 유사도가 임계값 이상이고, 2위 후보가 있다면
    1위와의 차이가 margin 이상이어야 한다 (모호한 매치 보류 —
    다음 프레임에서 더 확실해지면 그때 수락된다).

    Args:
        candidate_scores: (track_id, 코사인 유사도) 목록. 순서 무관.
        similarity_threshold: 동일인 수락 최소 유사도.
        margin: 1위-2위 최소 유사도 차이.

    Returns:
        수락된 track id, 조건 미달이면 None.
    """
    if not candidate_scores:
        return None

    ordered = sorted(candidate_scores, key=lambda item: item[1], reverse=True)
    best_id, best_score = ordered[0]
    if best_score < similarity_threshold:
        return None
    if len(ordered) > 1 and best_score - ordered[1][1] < margin:
        return None
    return best_id
