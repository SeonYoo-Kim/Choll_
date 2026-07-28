"""Unit tests for the target-loss search behavior (no ROS required)."""

import importlib
import math

import pytest

search_behavior = importlib.import_module("search_behavior")
SearchBehavior = search_behavior.SearchBehavior
SearchConfig = search_behavior.SearchConfig
SearchState = search_behavior.SearchState
TargetSnapshot = search_behavior.TargetSnapshot
estimate_exit_direction = search_behavior.estimate_exit_direction


def make_snapshot(bearing=0.0, distance=1.0, direction=1):
    return TargetSnapshot(
        bearing_rad=bearing, approach_distance_m=distance, exit_direction=direction
    )


class TestEstimateExitDirection:
    def test_moving_right_means_clockwise(self):
        # 화면 오른쪽(+x)으로 이동 중 소실 → 오른쪽(시계, -1)으로 탐색.
        samples = [(0.0, 0.1), (0.2, 0.3), (0.4, 0.6)]
        assert estimate_exit_direction(samples) == -1

    def test_moving_left_means_counterclockwise(self):
        samples = [(0.0, -0.1), (0.2, -0.4), (0.4, -0.7)]
        assert estimate_exit_direction(samples) == 1

    def test_slow_motion_falls_back_to_position_sign(self):
        # 속도가 임계 미만이면 마지막 위치의 부호로 판단 (오른쪽 가장자리 → -1).
        samples = [(0.0, 0.79), (0.5, 0.80)]
        assert estimate_exit_direction(samples) == -1

    def test_center_loss_defaults_to_left(self):
        # 화면 중앙에서 소실(가림)은 방향 정보가 없음 → 기본값 왼쪽(+1).
        samples = [(0.0, 0.01), (0.5, 0.0)]
        assert estimate_exit_direction(samples) == 1

    def test_empty_history_defaults_to_left(self):
        assert estimate_exit_direction([]) == 1


class TestStartSearch:
    def test_with_distance_starts_goto_last(self):
        behavior = SearchBehavior()
        behavior.start_search(make_snapshot(distance=1.5))
        assert behavior.state is SearchState.GOTO_LAST
        assert behavior.active

    def test_without_distance_skips_to_rotate(self):
        behavior = SearchBehavior()
        behavior.start_search(make_snapshot(distance=None))
        assert behavior.state is SearchState.SEARCH_ROTATE

    def test_non_positive_distance_skips_to_rotate(self):
        behavior = SearchBehavior()
        behavior.start_search(make_snapshot(distance=-0.2))
        assert behavior.state is SearchState.SEARCH_ROTATE


class TestGotoLast:
    def test_aligns_heading_before_driving(self):
        # 마지막 방위각이 왼쪽(+30°)이면 먼저 +ω로 제자리 정렬한다.
        behavior = SearchBehavior()
        behavior.start_search(make_snapshot(bearing=math.radians(30.0)))
        linear, angular = behavior.step(dt=0.1, target_visible=False)
        assert linear == 0.0
        assert angular > 0.0

    def test_drives_forward_once_aligned(self):
        behavior = SearchBehavior()
        behavior.start_search(make_snapshot(bearing=0.0, distance=1.0))
        linear, angular = behavior.step(dt=0.1, target_visible=False)
        assert linear == pytest.approx(SearchConfig().goto_linear_vel_mps)
        assert angular == 0.0

    def test_transitions_to_rotate_after_covering_distance(self):
        # 0.3 m/s로 1.0 m → 3.4초면 도착. dead reckoning 적분 검증.
        behavior = SearchBehavior()
        behavior.start_search(make_snapshot(bearing=0.0, distance=1.0))
        for _ in range(40):  # 4.0초
            behavior.step(dt=0.1, target_visible=False)
            if behavior.state is not SearchState.GOTO_LAST:
                break
        assert behavior.state is SearchState.SEARCH_ROTATE

    def test_obstacle_aborts_forward_motion(self):
        behavior = SearchBehavior()
        behavior.start_search(make_snapshot(bearing=0.0, distance=2.0))
        linear, angular = behavior.step(
            dt=0.1, target_visible=False, obstacle_distance_m=0.4
        )
        assert (linear, angular) == (0.0, 0.0)
        assert behavior.state is SearchState.SEARCH_ROTATE

    def test_far_obstacle_does_not_abort(self):
        behavior = SearchBehavior()
        behavior.start_search(make_snapshot(bearing=0.0, distance=2.0))
        linear, _ = behavior.step(
            dt=0.1, target_visible=False, obstacle_distance_m=3.0
        )
        assert linear > 0.0


class TestSearchRotate:
    def test_rotates_toward_exit_direction(self):
        behavior = SearchBehavior()
        behavior.start_search(make_snapshot(distance=None, direction=-1))
        _, angular = behavior.step(dt=0.1, target_visible=False)
        assert angular < 0.0  # 오른쪽으로 사라짐 → 시계 방향 회전

    def test_gives_up_after_max_rotation(self):
        # 0.5 rad/s × 120° 상한 → 약 4.2초 후 SEARCH_FAILED로 정지.
        behavior = SearchBehavior()
        behavior.start_search(make_snapshot(distance=None, direction=1))
        for _ in range(60):  # 6.0초
            behavior.step(dt=0.1, target_visible=False)
        assert behavior.state is SearchState.SEARCH_FAILED
        assert behavior.step(dt=0.1, target_visible=False) == (0.0, 0.0)


class TestGlobalRules:
    def test_target_reappearance_resets_from_any_state(self):
        behavior = SearchBehavior()
        behavior.start_search(make_snapshot(distance=1.0))
        behavior.step(dt=0.1, target_visible=False)
        cmd = behavior.step(dt=0.1, target_visible=True)
        assert cmd == (0.0, 0.0)
        assert behavior.state is SearchState.TRACKING
        assert not behavior.active

    def test_total_duration_timeout_fails_search(self):
        config = SearchConfig(max_search_duration_sec=1.0)
        behavior = SearchBehavior(config)
        behavior.start_search(make_snapshot(distance=100.0))  # 오래 걸리는 접근
        for _ in range(15):  # 1.5초
            behavior.step(dt=0.1, target_visible=False)
        assert behavior.state is SearchState.SEARCH_FAILED

    def test_tracking_state_outputs_zero(self):
        behavior = SearchBehavior()
        assert behavior.step(dt=0.1, target_visible=False) == (0.0, 0.0)

    def test_non_positive_dt_is_safe(self):
        behavior = SearchBehavior()
        behavior.start_search(make_snapshot(distance=1.0))
        assert behavior.step(dt=0.0, target_visible=False) == (0.0, 0.0)
        assert behavior.state is SearchState.GOTO_LAST
