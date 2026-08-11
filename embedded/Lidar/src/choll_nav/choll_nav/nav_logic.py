"""순수 내비게이션 로직 (ROS 의존성 없음).

goal_forwarder가 사용하는 계산 함수 모음. rclpy를 임포트하지 않으므로
ROS 미설치 환경에서도 pytest로 단독 검증할 수 있다.
"""

import math


def yaw_to_quaternion(yaw_rad: float) -> tuple[float, float, float, float]:
    """Z축 회전(yaw)을 쿼터니언으로 변환한다.

    Args:
        yaw_rad: Z축 기준 회전각 (rad, CCW+).

    Returns:
        쿼터니언 (x, y, z, w).
    """
    half = yaw_rad * 0.5
    return (0.0, 0.0, math.sin(half), math.cos(half))


def heading_between(
    from_x: float, from_y: float, to_x: float, to_y: float
) -> float:
    """시작점에서 도착점을 바라보는 방향각을 계산한다.

    Args:
        from_x: 시작점 x (m).
        from_y: 시작점 y (m).
        to_x: 도착점 x (m).
        to_y: 도착점 y (m).

    Returns:
        방향각 (rad, CCW+, atan2 규약).
    """
    return math.atan2(to_y - from_y, to_x - from_x)


def orientation_is_unset(
    x: float, y: float, z: float, w: float, eps: float = 1e-6
) -> bool:
    """쿼터니언이 미지정 상태인지 판정한다.

    전부 0(메시지 기본값) 또는 항등 회전(0, 0, 0, 1)이면 미지정으로 본다.

    Args:
        x: 쿼터니언 x.
        y: 쿼터니언 y.
        z: 쿼터니언 z.
        w: 쿼터니언 w.
        eps: 0 판정 허용 오차.

    Returns:
        미지정이면 True.
    """
    if abs(x) < eps and abs(y) < eps and abs(z) < eps:
        return abs(w) < eps or abs(w - 1.0) < eps
    return False


def compute_approach_point(
    robot_x: float,
    robot_y: float,
    target_x: float,
    target_y: float,
    approach_distance_m: float,
) -> tuple[float, float]:
    """로봇→목표 직선상에서 목표 앞 approach_distance_m 지점을 구한다.

    사람 좌표를 그대로 goal로 쓰면 로봇이 사람을 파고들다 실패하므로
    (사람 = 장애물), 목표 앞 일정 거리 지점을 goal로 사용한다.

    Args:
        robot_x: 로봇 현재 x (m).
        robot_y: 로봇 현재 y (m).
        target_x: 목표 x (m).
        target_y: 목표 y (m).
        approach_distance_m: 목표 앞 유지 거리 (m). 0 이하면 목표 그대로.

    Returns:
        goal (x, y). 로봇이 이미 유지 거리 안쪽이면 로봇 현재 위치를
        반환한다 (목표 뒤로 넘어가는 것 방지).
    """
    if approach_distance_m <= 0.0:
        return (target_x, target_y)
    dx = target_x - robot_x
    dy = target_y - robot_y
    dist = math.hypot(dx, dy)
    if dist < 1e-9:
        return (target_x, target_y)
    if dist <= approach_distance_m:
        return (robot_x, robot_y)
    scale = (dist - approach_distance_m) / dist
    return (robot_x + dx * scale, robot_y + dy * scale)


def should_send_goal(
    new_xy: tuple[float, float],
    now_sec: float,
    last_xy: tuple[float, float] | None,
    last_sent_sec: float | None,
    navigating: bool,
    min_interval_sec: float,
    min_move_dist_m: float,
    after_success: bool = False,
) -> bool:
    """Goal 전송 여부(스로틀)를 판정한다.

    상류(AI)가 임의 주기(~10Hz)로 목표를 발행해도 Nav2에 goal이 도배되지
    않도록: ① 최소 간격은 상태와 무관하게 항상 적용 (send→응답 대기 창의
    버스트, 도달 직후 send→succeed 루프 차단) ② 주행 중이거나 직전에
    성공(SUCCEEDED)한 상태면 최소 이동 거리도 요구 (사람이 approach 거리
    안에 서 있을 때 NAVIGATING↔SUCCEEDED 플래핑 방지 — 같은 지점 재전송은
    어차피 무의미). 실패 상태(ABORTED 등)에서는 간격만 지나면 같은 지점
    재지시를 허용한다. 비교 기준은 approach 보정 전의 원시 목표 좌표다 —
    보정 후 좌표는 로봇이 움직이기만 해도 변해 스로틀이 무력화되기 때문.

    Args:
        new_xy: 새 목표의 원시 좌표 (x, y) (m).
        now_sec: 현재 시각 (s).
        last_xy: 마지막 전송한 목표의 원시 좌표. 없으면 None.
        last_sent_sec: 마지막 전송 시각 (s). 없으면 None.
        navigating: 현재 주행(NAVIGATING) 중인지 여부.
        min_interval_sec: 재전송 최소 간격 (s). 상태 무관 적용.
        min_move_dist_m: 재전송 최소 이동 거리 (m). 주행 중/성공 후 적용.
        after_success: 직전 상태가 SUCCEEDED인지 여부.

    Returns:
        전송해야 하면 True. 첫 goal(기록 없음)은 항상 True.
    """
    if last_xy is None or last_sent_sec is None:
        return True
    if now_sec - last_sent_sec < min_interval_sec:
        return False
    if navigating or after_success:
        moved = math.hypot(new_xy[0] - last_xy[0], new_xy[1] - last_xy[1])
        return moved >= min_move_dist_m
    return True


def make_goal_pose_2d(
    robot_xy: tuple[float, float] | None,
    target_xy: tuple[float, float],
    input_quat_xyzw: tuple[float, float, float, float],
    approach_distance_m: float,
    auto_orient: bool,
) -> tuple[float, float, tuple[float, float, float, float]]:
    """최종 2D goal (x, y, 쿼터니언)을 합성한다.

    approach 오프셋을 적용한 뒤, 방향이 미지정이고 auto_orient가 켜져
    있으면 로봇→원시 목표 방향을 goal 방향으로 설정한다 (오프셋 지점이
    아닌 원시 목표 기준 — 목표를 바라보는 방향이 의미상 맞음).

    Args:
        robot_xy: 로봇 현재 (x, y). 미확보 시 None — approach 오프셋을
            건너뛰고(원시 좌표 사용) 방향 미지정 시 항등 쿼터니언 유지.
        target_xy: 목표 원시 좌표 (x, y) (m).
        input_quat_xyzw: 입력 goal의 쿼터니언 (x, y, z, w).
        approach_distance_m: 목표 앞 유지 거리 (m).
        auto_orient: 방향 자동 설정 여부.

    Returns:
        (goal_x, goal_y, 쿼터니언 (x, y, z, w)).
    """
    target_x, target_y = target_xy
    if robot_xy is not None and approach_distance_m > 0.0:
        goal_x, goal_y = compute_approach_point(
            robot_xy[0], robot_xy[1], target_x, target_y, approach_distance_m
        )
    else:
        goal_x, goal_y = target_x, target_y

    quat = input_quat_xyzw
    if auto_orient and orientation_is_unset(*input_quat_xyzw):
        if robot_xy is not None:
            yaw = heading_between(robot_xy[0], robot_xy[1], target_x, target_y)
            quat = yaw_to_quaternion(yaw)
        else:
            quat = (0.0, 0.0, 0.0, 1.0)
    return (goal_x, goal_y, quat)
