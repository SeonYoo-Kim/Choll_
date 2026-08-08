"""가짜 Jetson(EM SLAM Nav) — 실물 카트 없이 FE→BE→MQTT 왕복을 구동하는 시뮬레이터.

BE가 내려보내는 이동 명령(cmd/move/cart)을 구독하고, 실제 카트처럼
- 하트비트(status/cart)를 5초마다,
- SLAM 위치(status/position, **미터 좌표**)를 이동 중 5Hz / 정지 중 1Hz로 발행한다.

MOVE 명령을 받으면 target(SLAM 미터)을 향해 일정 속도로 이동하며 위치를 흘리고,
CANCEL이면 그 자리에 멈춘다. BE는 이 위치를 지도 메타(library_maps)로 픽셀 변환해
WS CART_POSITION_UPDATE로 FE에 중계한다 — FE 마커는 오직 이 경로로만 움직인다.

사용법:
    python scripts/fake_jetson.py [--broker localhost] [--speed 0.5]

전제: BE가 MQTT_POSITION_UNIT=meters로 떠 있고, library_maps(id=mqtt.map-id)에
      이 시뮬레이터와 같은 좌표계(resolution·origin·height)가 들어 있어야 한다.
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone

import paho.mqtt.client as mqtt

logging.basicConfig(format="%(asctime)s [%(levelname)s] %(message)s", level=logging.INFO)
log = logging.getLogger("fake-jetson")

TOPIC_COMMAND = "cmd/move/cart"
TOPIC_POSITION = "status/position"
TOPIC_HEARTBEAT = "status/cart"
# ROS2 /cart/nav_status(7종)를 MQTT로 중계하는 토픽 (2026-08-07 EM 합의)
TOPIC_NAV_RESULT = "status/nav-result"

HEARTBEAT_INTERVAL_S = 5.0
MOVING_PUBLISH_HZ = 5.0
IDLE_PUBLISH_HZ = 1.0


@dataclass
class MapMeta:
    """BE library_maps 행과 같은 좌표계 정의 — 시작 위치 계산에만 쓴다."""

    resolution: float = 0.01  # m/px (test-room-3zones.sql 기준)
    origin_x: float = 0.0
    origin_y: float = 0.0
    height_px: int = 600


class FakeCart:
    """SLAM 미터 좌표계에서 목표를 향해 등속 이동하는 카트."""

    def __init__(self, start_x: float, start_y: float, speed_mps: float) -> None:
        self.x = start_x
        self.y = start_y
        self.speed = speed_mps
        self.target: tuple[float, float] | None = None
        self.lock = threading.Lock()

    def set_target(self, x: float, y: float) -> None:
        with self.lock:
            self.target = (x, y)

    def cancel(self) -> None:
        with self.lock:
            self.target = None

    def step(self, dt_s: float) -> tuple[bool, bool]:
        """dt만큼 이동. (이동 중인가, 이번 스텝에 도착했는가)를 반환."""
        with self.lock:
            if self.target is None:
                return False, False
            dx = self.target[0] - self.x
            dy = self.target[1] - self.y
            distance = math.hypot(dx, dy)
            reach = self.speed * dt_s
            if distance <= reach:
                self.x, self.y = self.target
                self.target = None
                log.info("도착 x=%.3f y=%.3f", self.x, self.y)
                return False, True
            self.x += dx / distance * reach
            self.y += dy / distance * reach
            return True, False


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--broker", default="localhost")
    parser.add_argument("--port", type=int, default=1883)
    parser.add_argument("--speed", type=float, default=0.5, help="이동 속도 (m/s)")
    parser.add_argument("--start-px", default="800,108", help="시작 위치 (지도 픽셀 x,y — 레거시 메타 기준)")
    parser.add_argument(
        "--start-world",
        default=None,
        help="시작 위치 (SLAM 미터 x,y) — 지정하면 --start-px 무시. "
        "BE가 아핀 캘리브레이션을 쓰는 경우 픽셀 환산이 이 스크립트의 레거시 메타와 달라지므로 이 옵션을 쓸 것",
    )
    args = parser.parse_args()

    if args.start_world is not None:
        start_x, start_y = (float(v) for v in args.start_world.split(","))
        log.info("시작 위치: SLAM(%.3f, %.3f)", start_x, start_y)
    else:
        meta = MapMeta()
        start_px_x, start_px_y = (float(v) for v in args.start_px.split(","))
        # 픽셀 → SLAM 미터 (ROS 규약: 세로축 반전)
        start_x = meta.origin_x + start_px_x * meta.resolution
        start_y = meta.origin_y + (meta.height_px - start_px_y) * meta.resolution
        log.info("시작 위치: 픽셀(%.0f, %.0f) = SLAM(%.3f, %.3f)", start_px_x, start_px_y, start_x, start_y)
    cart = FakeCart(start_x, start_y, args.speed)

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="fake-jetson")

    def on_connect(client: mqtt.Client, userdata: object, flags: dict, reason: object, props: object) -> None:
        log.info("브로커 연결 — %s 구독", TOPIC_COMMAND)
        client.subscribe(TOPIC_COMMAND)

    def publish_nav_result(status: str) -> None:
        payload = json.dumps({"status": status, "timestamp": now_iso()})
        client.publish(TOPIC_NAV_RESULT, payload)
        log.info("주행 결과 발행 %s: %s", TOPIC_NAV_RESULT, payload)

    def on_message(client: mqtt.Client, userdata: object, message: mqtt.MQTTMessage) -> None:
        try:
            command = json.loads(message.payload)
        except json.JSONDecodeError:
            log.warning("명령 파싱 실패: %s", message.payload)
            return
        log.info("명령 수신 %s: %s", message.topic, json.dumps(command, ensure_ascii=False))
        kind = command.get("command")
        if kind == "MOVE":
            target = command.get("target")
            if target is None:
                # pixels 모드(BE가 미터 변환을 끈 상태) — 이 시뮬레이터는 meters 전제라 거부한다
                log.warning("target이 없습니다 — BE가 MQTT_POSITION_UNIT=meters로 떠 있는지 확인하세요")
                publish_nav_result("REJECTED")
                return
            cart.set_target(float(target["x"]), float(target["y"]))
            log.info("이동 시작 → SLAM(%.3f, %.3f)", target["x"], target["y"])
            publish_nav_result("NAVIGATING")  # Nav2가 goal을 수락한 순간에 대응
        elif kind == "CANCEL":
            was_moving = cart.target is not None
            cart.cancel()
            log.info("이동 취소 — 현 위치 정지")
            if was_moving:
                publish_nav_result("CANCELED")

    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(args.broker, args.port)
    client.loop_start()

    last_heartbeat = 0.0
    last_step = time.monotonic()
    try:
        while True:
            now = time.monotonic()
            moving, just_arrived = cart.step(now - last_step)
            last_step = now

            if just_arrived:
                publish_nav_result("SUCCEEDED")

            if now - last_heartbeat >= HEARTBEAT_INTERVAL_S:
                client.publish(TOPIC_HEARTBEAT, json.dumps({"timestamp": now_iso()}))
                last_heartbeat = now

            position = {"x": round(cart.x, 3), "y": round(cart.y, 3), "timestamp": now_iso()}
            client.publish(TOPIC_POSITION, json.dumps(position))
            if moving:
                log.info("위치 발행 %s", position)

            time.sleep(1.0 / (MOVING_PUBLISH_HZ if moving else IDLE_PUBLISH_HZ))
    except KeyboardInterrupt:
        log.info("종료")
    finally:
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    main()
