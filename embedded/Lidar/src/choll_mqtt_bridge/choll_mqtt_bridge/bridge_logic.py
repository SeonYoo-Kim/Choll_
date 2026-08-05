"""MQTT↔ROS2 브릿지 순수 로직 (ROS·paho 무관 — pytest 단독 실행 가능).

EM-BE MQTT 명세서(MQTT-01 status/position, MQTT-04 cmd/move/cart)
페이로드의 파싱·생성 규칙을 담당한다. BE와 키 이름이 바뀌면 이 파일과
테스트만 수정하면 된다.
"""

import json
import math
from datetime import datetime, timezone


def yaw_from_quaternion(x: float, y: float, z: float, w: float) -> float:
    """쿼터니언에서 z축 회전(yaw, 라디안, CCW+)을 계산한다."""
    return math.atan2(2.0 * (w * z + x * y), 1.0 - 2.0 * (y * y + z * z))


def parse_cart_command(payload: "str | bytes") -> dict:
    """MQTT-04 ``cmd/move/cart`` 페이로드를 라우팅 명령 dict로 변환한다.

    반환 dict의 ``kind`` 값:

    - ``move``: x, y[m, map 프레임], request_id, zone_id
    - ``cancel``: request_id
    - ``select_target``: track_id (AI 파트 라우팅용)
    - ``follow``: action (FOLLOW_START | FOLLOW_PAUSE | FOLLOW_STOP)
    - ``error``: reason (발행하지 말고 경고 로그만 남길 것)
    """
    try:
        data = json.loads(payload)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {"kind": "error", "reason": "JSON 파싱 실패"}
    if not isinstance(data, dict):
        return {"kind": "error", "reason": "JSON 객체가 아닌 페이로드"}

    command = data.get("command")
    request_id = str(data.get("requestId") or "")

    if command == "MOVE":
        target = data.get("target")
        if not isinstance(target, dict):
            if isinstance(data.get("pixel"), dict):
                return {
                    "kind": "error",
                    "reason": "pixel 좌표만 수신 — target{x,y}(SLAM 미터) 필요",
                }
            return {"kind": "error", "reason": "MOVE에 target{x,y} 없음"}
        try:
            move_x = float(target["x"])
            move_y = float(target["y"])
        except (KeyError, TypeError, ValueError):
            return {"kind": "error", "reason": "target.x/y가 숫자가 아님"}
        return {
            "kind": "move",
            "x": move_x,
            "y": move_y,
            "request_id": request_id,
            "zone_id": data.get("zoneId"),
        }

    if command == "CANCEL":
        return {"kind": "cancel", "request_id": request_id}

    if command == "SELECT_TARGET":
        track_id = data.get("trackId")
        if not isinstance(track_id, int) or isinstance(track_id, bool):
            return {"kind": "error", "reason": "SELECT_TARGET에 trackId(정수) 없음"}
        return {"kind": "select_target", "track_id": track_id}

    if command in ("FOLLOW_START", "FOLLOW_PAUSE", "FOLLOW_STOP"):
        return {"kind": "follow", "action": command}

    return {"kind": "error", "reason": f"알 수 없는 command: {command!r}"}


def build_position_payload(x: float, y: float, yaw_rad: float, stamp_sec: float) -> str:
    """MQTT-01 ``status/position`` 페이로드(JSON 문자열)를 생성한다.

    키 계약은 BE 파서 실측 기준 (backend MqttPositionMessageHandler의
    PositionPayload: x·y·timestamp[ISO-8601 Instant, 선택]). yaw(라디안,
    CCW+)는 BE가 아직 파싱하지 않는 추가 필드 — WS CART_POSITION_UPDATE의
    yaw(현재 임시 0) 채움용으로 BE 파서 확장 제안 상태.
    stamp_sec이 0 이하(미설정)면 timestamp를 생략해 BE가 수신 시각을 쓴다.
    """
    payload: dict = {
        "x": round(x, 3),
        "y": round(y, 3),
        "yaw": round(yaw_rad, 4),
    }
    if stamp_sec > 0:
        utc = datetime.fromtimestamp(stamp_sec, tz=timezone.utc)
        payload["timestamp"] = utc.isoformat(timespec="milliseconds").replace(
            "+00:00", "Z"
        )
    return json.dumps(payload, separators=(",", ":"))


def should_publish_position(
    now_sec: float, last_pub_sec: "float | None", min_period_sec: float
) -> bool:
    """위치 텔레메트리 발행 여부(주기 스로틀)를 판정한다."""
    if last_pub_sec is None:
        return True
    return (now_sec - last_pub_sec) >= min_period_sec
