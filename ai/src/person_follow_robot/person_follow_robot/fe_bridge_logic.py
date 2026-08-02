"""fe_bridge_logic — FE 타겟 선택 연동 브릿지의 프레임워크 독립 로직.

fe_bridge_node가 사용하는 순수 함수/클래스 모음 (ROS·cv2·네트워크 무관):
- RateLimiter: 영상(10fps)·트랙(5Hz) 전송률 제한. 최신 프레임만 보내는
  drop-oldest 정책의 판단부.
- build_tracks_payload: ROS 트랙 검출 → BE MQTT(choll/cart/tracks) 페이로드.
  bbox를 중심 좌표에서 FE가 그리기 쉬운 좌상단 기준으로 변환한다.
- parse_select_command: BE 명령(choll/cart/cmd)에서 SELECT_TARGET만 골라
  track id를 꺼낸다.

pytest: ai/test/test_fe_bridge_logic.py
"""

from __future__ import annotations

import json
from collections.abc import Sequence


class RateLimiter:
    """최소 전송 간격을 강제한다 (초과분 프레임은 버려진다 = drop-oldest)."""

    def __init__(self, min_interval_sec: float) -> None:
        """전송 간 최소 간격(초)을 설정한다. 0 이하면 제한 없음."""
        self._min_interval_sec = max(0.0, float(min_interval_sec))
        self._last_sent_at: float | None = None

    def should_send(self, now_sec: float) -> bool:
        """이번 프레임을 보내야 하면 True를 반환하고 전송 시각을 기록한다.

        Args:
            now_sec: 단조 증가 시각(초). time.monotonic() 값을 넘긴다.
        """
        if (
            self._last_sent_at is not None
            and now_sec - self._last_sent_at < self._min_interval_sec
        ):
            return False
        self._last_sent_at = now_sec
        return True


def build_tracks_payload(
    image_width: int,
    image_height: int,
    tracks: Sequence[tuple[int, float, float, float, float]],
) -> dict:
    """트랙 목록을 BE 계약(choll/cart/tracks) 페이로드로 변환한다.

    Args:
        image_width: 원본 프레임 폭 (픽셀).
        image_height: 원본 프레임 높이 (픽셀).
        tracks: (track_id, center_x, center_y, size_x, size_y) 목록 (픽셀).

    Returns:
        {"image_width":…, "image_height":…,
         "tracks":[{"id":…, "x":…, "y":…, "w":…, "h":…}]} —
        x, y는 bbox 좌상단(정수 픽셀). FE가 영상 위에 그대로 그린다.
    """
    return {
        "image_width": int(image_width),
        "image_height": int(image_height),
        "tracks": [
            {
                "id": int(track_id),
                "x": int(round(center_x - size_x / 2.0)),
                "y": int(round(center_y - size_y / 2.0)),
                "w": int(round(size_x)),
                "h": int(round(size_y)),
            }
            for track_id, center_x, center_y, size_x, size_y in tracks
        ],
    }


def parse_select_command(payload: str) -> int | None:
    """BE 명령 페이로드에서 SELECT_TARGET의 track id를 추출한다.

    choll/cart/cmd 토픽은 MOVE/CANCEL 등 다른 명령도 흐르므로,
    SELECT_TARGET이 아니거나 trackId가 정수가 아니면 None을 반환한다.

    Args:
        payload: MQTT 메시지 본문 (JSON 문자열).

    Returns:
        선택된 track id, 해당 없으면 None.
    """
    try:
        message = json.loads(payload)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(message, dict):
        return None
    if message.get("command") != "SELECT_TARGET":
        return None
    track_id = message.get("trackId")
    if isinstance(track_id, bool) or not isinstance(track_id, int):
        return None
    return track_id
