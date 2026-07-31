"""search_behavior — 타겟 상실 시 탐색 거동 상태머신 (프레임워크 독립).

사서가 시야에서 사라졌을 때의 거동을 결정한다:

    TRACKING ─(start_search)→ GOTO_LAST ─(도착/장애물)→ SEARCH_ROTATE
        ↑                                                   │
        └────── 타겟 재관측(step의 target_visible) ←─ (타임아웃)→ SEARCH_FAILED(정지)

- GOTO_LAST: 마지막 방위각으로 정렬 후, 마지막 위치 근방까지 전진.
- SEARCH_ROTATE: 사라진 방향(왼쪽/오른쪽)으로 제자리 회전하며 재탐색.
- 어느 상태에서든 타겟이 다시 보이면 TRACKING으로 복귀 (추종은 PID 담당).

ROS에 의존하지 않는 순수 로직이므로 pytest로 검증한다
(ai/test/test_search_logic.py). 실기 배선(control_node 연결)은 조립 후 진행.

오도메트리(/odom)가 아직 없어 이동량은 명령 속도 적분(dead reckoning)으로
추정한다. EM 파트가 엔코더 피드백을 올려주면 이 적분을 odom 기반으로 교체할 것.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum


class SearchState(Enum):
    """탐색 상태머신의 상태."""

    TRACKING = "tracking"
    GOTO_LAST = "goto_last"
    SEARCH_ROTATE = "search_rotate"
    SEARCH_FAILED = "search_failed"


@dataclass(frozen=True)
class SearchConfig:
    """탐색 거동 파라미터.

    안전 기본값: 사람이 안 보이는 상태의 자율 거동이므로 추종 때보다 느리게.
    """

    goto_linear_vel_mps: float = 0.3
    rotate_angular_vel_rps: float = 0.5
    align_tolerance_rad: float = math.radians(8.0)
    max_rotate_angle_rad: float = math.radians(120.0)
    obstacle_stop_m: float = 0.5
    max_search_duration_sec: float = 10.0


@dataclass(frozen=True)
class TargetSnapshot:
    """타겟 상실 시점의 마지막 관측 요약.

    Attributes:
        bearing_rad: 로봇 전방 기준 마지막 방위각 (rad, 반시계 +).
        approach_distance_m: 전진할 거리(m) — 마지막 LiDAR 거리에서 목표 정지
            거리(target_distance)를 뺀 값을 호출자가 넣는다. 모르면 None
            (GOTO_LAST를 건너뛰고 바로 회전 탐색).
        exit_direction: 사라진 방향. +1=왼쪽(반시계), -1=오른쪽(시계).
    """

    bearing_rad: float
    approach_distance_m: float | None
    exit_direction: int


def estimate_exit_direction(
    samples: Sequence[tuple[float, float]],
    min_speed: float = 0.05,
    min_offset: float = 0.05,
) -> int:
    """상실 직전 bbox 이력으로 사라진 방향을 추정한다.

    화면 좌표 +x는 오른쪽, 로봇 회전 +는 반시계(왼쪽)이므로 부호가 반대다.

    Args:
        samples: (시각 sec, center_x_normalized[-1,1]) 목록, 시간 오름차순.
        min_speed: 속도 판정에 필요한 최소 |dx/dt| (정규화 단위/초).
        min_offset: 위치 판정에 필요한 최소 |x| (중앙 소실은 방향 정보 없음).

    Returns:
        +1=왼쪽(반시계 회전), -1=오른쪽(시계 회전). 판단 불가 시 +1.
    """
    if len(samples) >= 2:
        first_t, first_x = samples[0]
        last_t, last_x = samples[-1]
        elapsed = last_t - first_t
        if elapsed > 0.0:
            speed = (last_x - first_x) / elapsed
            if abs(speed) >= min_speed:
                return -1 if speed > 0 else 1
    if samples:
        last_x = samples[-1][1]
        if abs(last_x) >= min_offset:
            return -1 if last_x > 0 else 1
    return 1


class SearchBehavior:
    """상실 → 마지막 위치 접근 → 회전 탐색 상태머신.

    사용 계약 (control_node의 15Hz 루프 기준):
    - 타겟 상실이 확정되면 ``start_search(snapshot)``를 1회 호출.
    - 이후 매 루프 ``step(dt, target_visible, obstacle_distance_m)``을 호출해
      (선속도, 각속도)를 받아 cmd_vel로 발행.
    - 타겟이 다시 보이면(step의 target_visible=True) 즉시 TRACKING으로
      복귀하며 (0, 0)을 반환 — 이후 추종은 기존 PID가 담당.
    """

    def __init__(self, config: SearchConfig | None = None) -> None:
        """상태를 TRACKING으로 초기화한다."""
        self.config = config if config is not None else SearchConfig()
        self.state = SearchState.TRACKING
        self._snapshot: TargetSnapshot | None = None
        self._heading_error_rad = 0.0
        self._remaining_m = 0.0
        self._rotated_rad = 0.0
        self._elapsed_sec = 0.0

    @property
    def active(self) -> bool:
        """탐색 거동이 cmd를 결정 중이면 True (TRACKING이면 False)."""
        return self.state is not SearchState.TRACKING

    def reset(self) -> None:
        """TRACKING으로 복귀하고 내부 누적치를 지운다."""
        self.state = SearchState.TRACKING
        self._snapshot = None
        self._heading_error_rad = 0.0
        self._remaining_m = 0.0
        self._rotated_rad = 0.0
        self._elapsed_sec = 0.0

    def start_search(self, snapshot: TargetSnapshot) -> None:
        """타겟 상실 확정 시 탐색을 시작한다.

        마지막 거리를 알면 GOTO_LAST부터, 모르면 바로 SEARCH_ROTATE.
        """
        self.reset()
        self._snapshot = snapshot
        if (
            snapshot.approach_distance_m is not None
            and snapshot.approach_distance_m > 0.0
        ):
            self.state = SearchState.GOTO_LAST
            self._heading_error_rad = snapshot.bearing_rad
            self._remaining_m = snapshot.approach_distance_m
        else:
            self.state = SearchState.SEARCH_ROTATE

    def step(
        self,
        dt: float,
        target_visible: bool,
        obstacle_distance_m: float | None = None,
    ) -> tuple[float, float]:
        """한 제어 주기의 (선속도 m/s, 각속도 rad/s)를 반환한다.

        Args:
            dt: 직전 호출로부터 경과 시간(초).
            target_visible: 이번 주기에 타겟이 관측되면 True → TRACKING 복귀.
            obstacle_distance_m: 전방 장애물 거리(m). GOTO_LAST 전진 중
                obstacle_stop_m 이하이면 전진을 포기하고 회전 탐색으로 전환.
        """
        if target_visible:
            self.reset()
            return 0.0, 0.0
        if self.state is SearchState.TRACKING or dt <= 0.0:
            return 0.0, 0.0

        self._elapsed_sec += dt
        if self._elapsed_sec > self.config.max_search_duration_sec:
            self.state = SearchState.SEARCH_FAILED

        if self.state is SearchState.SEARCH_FAILED:
            return 0.0, 0.0
        if self.state is SearchState.GOTO_LAST:
            return self._step_goto_last(dt, obstacle_distance_m)
        return self._step_search_rotate(dt)

    def _step_goto_last(
        self, dt: float, obstacle_distance_m: float | None
    ) -> tuple[float, float]:
        """마지막 방위각으로 정렬 후 마지막 위치 근방까지 전진."""
        cfg = self.config

        # 1) 제자리 회전으로 마지막 방위각에 정렬 (dead reckoning으로 잔여각 추적)
        if abs(self._heading_error_rad) > cfg.align_tolerance_rad:
            angular = math.copysign(
                cfg.rotate_angular_vel_rps, self._heading_error_rad
            )
            self._heading_error_rad -= angular * dt
            if self._heading_error_rad * angular < 0.0:  # 초과 회전 방지
                self._heading_error_rad = 0.0
            return 0.0, angular

        # 2) 전진. 사람이 안 보이는 상태의 전진이므로 장애물이면 즉시 포기.
        if (
            obstacle_distance_m is not None
            and obstacle_distance_m <= cfg.obstacle_stop_m
        ):
            self.state = SearchState.SEARCH_ROTATE
            return 0.0, 0.0

        self._remaining_m -= cfg.goto_linear_vel_mps * dt
        if self._remaining_m <= 0.0:
            self.state = SearchState.SEARCH_ROTATE
            return 0.0, 0.0
        return cfg.goto_linear_vel_mps, 0.0

    def _step_search_rotate(self, dt: float) -> tuple[float, float]:
        """사라진 방향으로 제자리 회전. 최대 회전각을 넘으면 실패 처리."""
        cfg = self.config
        direction = self._snapshot.exit_direction if self._snapshot else 1
        angular = direction * cfg.rotate_angular_vel_rps
        self._rotated_rad += abs(angular) * dt
        if self._rotated_rad >= cfg.max_rotate_angle_rad:
            self.state = SearchState.SEARCH_FAILED
            return 0.0, 0.0
        return 0.0, angular
