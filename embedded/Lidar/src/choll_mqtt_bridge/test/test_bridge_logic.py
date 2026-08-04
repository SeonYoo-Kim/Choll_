"""bridge_logic 순수 로직 테스트 (ROS·paho 불필요)."""

import json
import math

from choll_mqtt_bridge.bridge_logic import (
    build_position_payload,
    parse_cart_command,
    should_publish_position,
    yaw_from_quaternion,
)

# ── yaw_from_quaternion ──────────────────────────────────────────────


def test_yaw_identity() -> None:
    """무회전 쿼터니언은 yaw 0."""
    assert yaw_from_quaternion(0.0, 0.0, 0.0, 1.0) == 0.0


def test_yaw_left_90deg() -> None:
    """왼쪽(CCW) 90° 회전은 +pi/2."""
    s = math.sin(math.pi / 4)
    c = math.cos(math.pi / 4)
    assert math.isclose(yaw_from_quaternion(0.0, 0.0, s, c), math.pi / 2)


def test_yaw_right_90deg() -> None:
    """오른쪽(CW) 90° 회전은 -pi/2."""
    s = math.sin(-math.pi / 4)
    c = math.cos(-math.pi / 4)
    assert math.isclose(yaw_from_quaternion(0.0, 0.0, s, c), -math.pi / 2)


# ── parse_cart_command: MOVE ─────────────────────────────────────────


def test_parse_move_meters() -> None:
    """Meters 모드 MOVE는 move 명령으로 변환."""
    payload = json.dumps(
        {
            "requestId": "req-1",
            "command": "MOVE",
            "zoneId": 3,
            "target": {"x": 1.5, "y": -0.7},
        }
    )
    assert parse_cart_command(payload) == {
        "kind": "move",
        "x": 1.5,
        "y": -0.7,
        "request_id": "req-1",
        "zone_id": 3,
    }


def test_parse_move_bytes_payload() -> None:
    """Bytes 페이로드(paho 원형)도 파싱된다."""
    payload = json.dumps({"command": "MOVE", "target": {"x": 0, "y": 0}})
    result = parse_cart_command(payload.encode())
    assert result["kind"] == "move"
    assert result["request_id"] == ""


def test_parse_move_pixel_only_rejected() -> None:
    """Pixel 좌표만 오면 오류로 분류 (BE meters 모드 필요)."""
    payload = json.dumps(
        {"command": "MOVE", "pixel": {"x": 120, "y": 88}}
    )
    result = parse_cart_command(payload)
    assert result["kind"] == "error"
    assert "pixel" in result["reason"]


def test_parse_move_missing_target() -> None:
    """Target 없는 MOVE는 오류."""
    result = parse_cart_command(json.dumps({"command": "MOVE"}))
    assert result["kind"] == "error"


def test_parse_move_non_numeric_target() -> None:
    """Target 좌표가 숫자가 아니면 오류."""
    payload = json.dumps({"command": "MOVE", "target": {"x": "a", "y": 1}})
    assert parse_cart_command(payload)["kind"] == "error"


# ── parse_cart_command: CANCEL / SELECT_TARGET / FOLLOW ──────────────


def test_parse_cancel_with_request_id() -> None:
    """CANCEL은 requestId를 실어 cancel 명령으로 변환."""
    payload = json.dumps({"requestId": "req-9", "command": "CANCEL"})
    assert parse_cart_command(payload) == {"kind": "cancel", "request_id": "req-9"}


def test_parse_cancel_null_request_id() -> None:
    """requestId가 null이어도 빈 문자열로 처리."""
    payload = json.dumps({"requestId": None, "command": "CANCEL"})
    assert parse_cart_command(payload) == {"kind": "cancel", "request_id": ""}


def test_parse_select_target() -> None:
    """SELECT_TARGET은 trackId를 실어 변환."""
    payload = json.dumps({"command": "SELECT_TARGET", "trackId": 3})
    assert parse_cart_command(payload) == {"kind": "select_target", "track_id": 3}


def test_parse_select_target_missing_track_id() -> None:
    """TrackId 없는 SELECT_TARGET은 오류."""
    assert parse_cart_command(json.dumps({"command": "SELECT_TARGET"}))[
        "kind"
    ] == "error"


def test_parse_follow_actions() -> None:
    """FOLLOW_* 3종은 follow 명령으로 변환."""
    for action in ("FOLLOW_START", "FOLLOW_PAUSE", "FOLLOW_STOP"):
        payload = json.dumps({"requestId": "r", "command": action})
        assert parse_cart_command(payload) == {"kind": "follow", "action": action}


# ── parse_cart_command: 오류 페이로드 ────────────────────────────────


def test_parse_invalid_json() -> None:
    """JSON이 아니면 오류."""
    assert parse_cart_command("{broken")["kind"] == "error"


def test_parse_non_object_json() -> None:
    """배열 등 객체가 아닌 JSON은 오류."""
    assert parse_cart_command("[1,2]")["kind"] == "error"


def test_parse_unknown_command() -> None:
    """모르는 command는 오류."""
    result = parse_cart_command(json.dumps({"command": "DANCE"}))
    assert result["kind"] == "error"
    assert "DANCE" in result["reason"]


# ── build_position_payload ───────────────────────────────────────────


def test_position_payload_fields() -> None:
    """MQTT-01 페이로드는 BE 파서 계약(x/y/timestamp)+yaw를 가진다."""
    payload = json.loads(build_position_payload(1.23456, -0.98765, 1.5708, 86400.5))
    assert payload == {
        "x": 1.235,
        "y": -0.988,
        "yaw": 1.5708,
        "timestamp": "1970-01-02T00:00:00.500Z",
    }


def test_position_payload_without_stamp() -> None:
    """Stamp 미설정(0)이면 timestamp를 생략해 BE가 수신 시각을 쓰게 한다."""
    payload = json.loads(build_position_payload(0.0, 0.0, 0.0, 0.0))
    assert "timestamp" not in payload


# ── should_publish_position ──────────────────────────────────────────


def test_position_throttle_first_always() -> None:
    """첫 발행은 무조건 허용."""
    assert should_publish_position(10.0, None, 0.5) is True


def test_position_throttle_within_period() -> None:
    """주기 미만 재발행은 차단."""
    assert should_publish_position(10.4, 10.0, 0.5) is False


def test_position_throttle_after_period() -> None:
    """주기 경과 시 발행 허용."""
    assert should_publish_position(10.5, 10.0, 0.5) is True
