"""target_auto_select — 타겟(사서) 자동 선택 로직 (프레임워크 독립).

요구사항 변경(2026-07-29): 사용자가 track id를 수동 지정하는 대신,
**가장 가까이 있는 사람 = 바운딩박스 면적이 가장 큰 사람**을 자동 선택해
바로 등록을 시작한다.

순간적으로 스쳐 가는 오탐이 선택되는 것을 막기 위해, 같은 트랙이
N프레임 연속으로 최대 면적일 때만 확정한다(AutoSelectStabilizer).

ROS에 의존하지 않는 순수 로직이므로 pytest로 검증한다
(ai/test/test_auto_select.py). reid_node가 import해 사용한다.
"""

from __future__ import annotations

from collections.abc import Sequence


def largest_track(
    track_areas: Sequence[tuple[int, float]],
    min_area_px: float = 0.0,
) -> int | None:
    """Bbox 면적이 가장 큰(=가장 가까운) 트랙 id를 반환한다.

    Args:
        track_areas: (track_id, bbox 면적 px²) 목록.
        min_area_px: 후보로 인정할 최소 면적. 너무 멀거나 작은 검출
            (오탐 가능성)이 자동 선택되는 것을 막는다.

    Returns:
        최대 면적 트랙의 id. 후보가 없거나 전부 min_area_px 미만이면 None.
    """
    best_id: int | None = None
    best_area = min_area_px
    for track_id, area in track_areas:
        if area >= best_area and (best_id is None or area > best_area):
            best_id = track_id
            best_area = area
    return best_id


class AutoSelectStabilizer:
    """같은 트랙이 N프레임 연속 최대일 때만 선택을 확정한다.

    사용 계약: 매 트랙 프레임마다 ``observe(최대 면적 트랙 id | None)``를
    호출하고, 반환값이 int이면 그 id로 등록을 시작한다.
    """

    def __init__(self, required_consecutive_frames: int) -> None:
        """확정에 필요한 연속 프레임 수를 설정한다 (1 이상으로 클램프)."""
        self._required = max(1, int(required_consecutive_frames))
        self._candidate_id: int | None = None
        self._consecutive = 0

    @property
    def candidate_id(self) -> int | None:
        """현재 관찰 중인 후보 트랙 id (디버그/로그용)."""
        return self._candidate_id

    @property
    def consecutive_frames(self) -> int:
        """현재 후보가 연속으로 최대였던 프레임 수 (디버그/로그용)."""
        return self._consecutive

    def observe(self, track_id: int | None) -> int | None:
        """이번 프레임의 최대 면적 트랙을 관찰하고, 확정되면 id를 반환.

        Args:
            track_id: 이번 프레임에서 면적이 가장 큰 트랙 id. 후보가
                없으면 None (연속 카운트가 리셋된다).

        Returns:
            required_consecutive_frames 연속으로 같은 id가 관찰되면 그 id,
            아니면 None.
        """
        if track_id is None:
            self.reset()
            return None

        if track_id != self._candidate_id:
            self._candidate_id = track_id
            self._consecutive = 1
        else:
            self._consecutive += 1

        if self._consecutive >= self._required:
            return track_id
        return None

    def reset(self) -> None:
        """후보와 연속 카운트를 초기화한다 (선택 확정/실패 후 재무장)."""
        self._candidate_id = None
        self._consecutive = 0
