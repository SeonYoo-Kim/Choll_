"""Unit tests for automatic nearest-person target selection (no ROS required)."""

import importlib

target_auto_select = importlib.import_module("target_auto_select")
AutoSelectStabilizer = target_auto_select.AutoSelectStabilizer
largest_track = target_auto_select.largest_track


class TestLargestTrack:
    def test_picks_largest_area(self):
        # 면적 최대 = 가장 가까운 사람. (id, 면적) 중 3번이 최대.
        assert largest_track([(1, 5000.0), (3, 20000.0), (7, 12000.0)]) == 3

    def test_empty_returns_none(self):
        assert largest_track([]) is None

    def test_all_below_min_area_returns_none(self):
        # 전부 최소 면적 미만(멀리 있는 사람/오탐)이면 선택하지 않는다.
        assert largest_track([(1, 900.0), (2, 400.0)], min_area_px=1000.0) is None

    def test_min_area_filters_small_but_keeps_large(self):
        assert largest_track([(1, 900.0), (2, 8000.0)], min_area_px=1000.0) == 2


class TestAutoSelectStabilizer:
    def test_confirms_after_required_consecutive_frames(self):
        stabilizer = AutoSelectStabilizer(required_consecutive_frames=3)
        assert stabilizer.observe(5) is None
        assert stabilizer.observe(5) is None
        assert stabilizer.observe(5) == 5

    def test_candidate_change_resets_count(self):
        # 두 사람이 엎치락뒤치락하면 확정하지 않는다.
        stabilizer = AutoSelectStabilizer(required_consecutive_frames=3)
        stabilizer.observe(5)
        stabilizer.observe(5)
        assert stabilizer.observe(9) is None  # 후보 교체 → 카운트 1부터
        assert stabilizer.observe(9) is None
        assert stabilizer.observe(9) == 9

    def test_none_frame_resets_count(self):
        # 후보가 사라진 프레임(검출 없음)은 연속성을 끊는다.
        stabilizer = AutoSelectStabilizer(required_consecutive_frames=2)
        stabilizer.observe(5)
        assert stabilizer.observe(None) is None
        assert stabilizer.observe(5) is None  # 처음부터 다시
        assert stabilizer.observe(5) == 5

    def test_reset_rearms_for_next_selection(self):
        stabilizer = AutoSelectStabilizer(required_consecutive_frames=2)
        stabilizer.observe(5)
        stabilizer.observe(5)
        stabilizer.reset()
        assert stabilizer.observe(5) is None  # 리셋 후 연속 1프레임째

    def test_required_frames_clamped_to_one(self):
        # 0 이하로 설정해도 최소 1프레임은 관찰해야 확정.
        stabilizer = AutoSelectStabilizer(required_consecutive_frames=0)
        assert stabilizer.observe(5) == 5
