"""수동 위치 발행기 — Jetson이 위치를 못 보낼 때 사람이 카트 위치를 대신 발행한다.

시연 최악 시나리오 대비: 추종(주행)은 되는데 SLAM 현위치 발행이 안 될 때,
사람이 카트를 눈으로 보며 이 도구로 위치를 찍으면 구역 판정·LED·화면 마커가
정상 경로(MQTT status/position → BE 아핀 변환 → WS)로 그대로 동작한다.

입력은 **평면도(1000x600) 기준**으로 받고, 스크립트가 아핀 역변환으로 SLAM 미터로
바꿔 발행한다 — 운영자는 화면에서 보이는 좌표계로만 생각하면 된다.

사용법:
    python scripts/manual_position.py [--broker localhost]
    # 배포 브로커(EC2 mosquitto)에 직접 발행 — 서버에 띄울 필요 없이 내 PC에서 실행.
    # EC2 BE는 pixels 모드(MQTT_POSITION_UNIT 미설정)이므로 --unit pixels 필수!
    python scripts/manual_position.py --broker your-server.example.com --username choll --password CHANGE_ME --unit pixels

좌표 단위 (--unit, BE의 MQTT_POSITION_UNIT과 반드시 일치):
    meters (기본)  BE가 아핀으로 픽셀 변환 — 실카트와 같은 계약 (로컬 시연 구성)
    pixels         평면도 픽셀을 그대로 발행 — BE 무변환 (EC2 배포 서버 구성)

프롬프트 명령:
    z1 / z2 / z3      각 통로 중앙으로 이동
    사서 / 반납        테이블 정차점으로 이동 (librarian / return 도 가능)
    s800 s200 s100 s000  각 서가 앞 정차점으로 이동
    start             카트 대기 지점
    540,355           평면도 픽셀 직접 지정 (x,y)
    speed 0.8         이동 속도 변경 (m/s, 기본 0.5 — 이동은 순간이동이 아니라 활주)
    jump z2           활주 없이 즉시 순간이동
    q                 종료

주의:
- 발행 좌표계는 BE의 아핀 캘리브레이션과 같아야 한다. 아래 AFFINE 상수는
  library-map-affine-initial.sql과 동일값 — **시연장에서 재캘리브레이션하면
  이 상수도 새 UPDATE SQL 값으로 바꿀 것.**
- 실물 Jetson의 위치 발행이 살아 있으면 같은 토픽에 이중 발행돼 마커가 널뛴다 —
  이 도구를 쓸 때는 EM 쪽 위치 브릿지를 꺼달라고 할 것.
"""

from __future__ import annotations

import argparse
import json
import math
import threading
import time
from datetime import datetime, timezone

import paho.mqtt.client as mqtt

TOPIC_POSITION = "status/position"
TOPIC_HEARTBEAT = "status/cart"
PUBLISH_HZ = 2.0
# 상단 통로의 평면도 y 픽셀 — 웨이포인트 이동은 이 높이를 경유해 구역 관통을 피한다
CORRIDOR_Y_PX = 117.0
HEARTBEAT_INTERVAL_S = 5.0

# world(SLAM m) -> 평면도 픽셀 아핀 (library-map-affine-v2.sql과 동일해야 함 — v2 지도 기준)
AFFINE_A = ((-20.317241, 144.564682), (108.029244, 15.182520))
AFFINE_T = (917.881, 175.555)

# 평면도 픽셀 웨이포인트 (frontend zones.ts 실측값 기준)
WAYPOINTS: dict[str, tuple[float, float]] = {
    "start": (800, 117),
    "z1": (908, 355),
    "z2": (540, 355),
    "z3": (132, 355),
    "사서": (350, 138),
    "librarian": (350, 138),
    "반납": (925, 138),
    "return": (925, 138),
    "s800": (205, 328),
    "s200": (500, 328),
    "s100": (581, 328),
    "s000": (877, 328),
}


def world_to_pixel(wx: float, wy: float) -> tuple[float, float]:
    """SLAM 미터 → 평면도 픽셀 (아핀 정변환)."""
    (a11, a12), (a21, a22) = AFFINE_A
    tx, ty = AFFINE_T
    return a11 * wx + a12 * wy + tx, a21 * wx + a22 * wy + ty


def pixel_to_world(px: float, py: float) -> tuple[float, float]:
    """평면도 픽셀 → SLAM 미터 (아핀 역변환)."""
    (a11, a12), (a21, a22) = AFFINE_A
    tx, ty = AFFINE_T
    det = a11 * a22 - a12 * a21
    dx, dy = px - tx, py - ty
    return (a22 * dx - a12 * dy) / det, (-a21 * dx + a11 * dy) / det


class PuppetCart:
    """현재 위치에서 목표로 활주하는 가상 카트 (SLAM 미터 좌표)."""

    def __init__(self, start_world: tuple[float, float], speed_mps: float) -> None:
        self.x, self.y = start_world
        self.yaw = 0.0
        self.speed = speed_mps
        self.targets: list[tuple[float, float]] = []
        self.lock = threading.Lock()

    def go(self, waypoints: list[tuple[float, float]], jump: bool = False) -> None:
        with self.lock:
            if jump:
                self.x, self.y = waypoints[-1]
                self.targets = []
            else:
                self.targets = list(waypoints)

    def step(self, dt_s: float) -> None:
        with self.lock:
            reach = self.speed * dt_s
            while self.targets and reach > 0:
                dx = self.targets[0][0] - self.x
                dy = self.targets[0][1] - self.y
                distance = math.hypot(dx, dy)
                if distance > 1e-9:
                    self.yaw = math.atan2(dy, dx)
                if distance <= reach:
                    self.x, self.y = self.targets.pop(0)
                    reach -= distance
                else:
                    self.x += dx / distance * reach
                    self.y += dy / distance * reach
                    reach = 0.0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--broker", default="localhost")
    parser.add_argument("--port", type=int, default=1883)
    parser.add_argument("--speed", type=float, default=0.5)
    parser.add_argument("--username", default=None, help="브로커 인증 계정 (배포 브로커는 필수)")
    parser.add_argument("--password", default=None)
    parser.add_argument(
        "--unit",
        choices=("meters", "pixels"),
        default="meters",
        help="발행 좌표 단위 — 대상 BE의 MQTT_POSITION_UNIT과 일치시킬 것 "
        "(로컬=meters, EC2 배포=pixels)",
    )
    args = parser.parse_args()

    # pixels 모드: 평면도 픽셀을 그대로 발행 (BE 무변환) — 내부 시뮬레이션도 픽셀 공간에서 돈다.
    # 속도는 그대로 m/s로 받되 픽셀/초로 환산한다 (평면도 1px = 약 0.0079m)
    if args.unit == "pixels":
        to_world = lambda px, py: (float(px), float(py))  # noqa: E731
        to_pixel = lambda wx, wy: (wx, wy)  # noqa: E731
        speed_scale = 1.0 / 0.0079
    else:
        to_world = pixel_to_world
        to_pixel = world_to_pixel
        speed_scale = 1.0

    cart = PuppetCart(to_world(*WAYPOINTS["start"]), args.speed * speed_scale)
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="manual-position")
    if args.username is not None:
        client.username_pw_set(args.username, args.password)
    client.connect(args.broker, args.port)
    client.loop_start()

    stop = threading.Event()

    def publish_loop() -> None:
        last_heartbeat = 0.0
        last = time.monotonic()
        while not stop.is_set():
            now = time.monotonic()
            cart.step(now - last)
            last = now
            timestamp = datetime.now(timezone.utc).isoformat()
            client.publish(TOPIC_POSITION, json.dumps({
                "x": round(cart.x, 3),
                "y": round(cart.y, 3),
                "yaw": round(cart.yaw, 4),
                "timestamp": timestamp,
            }))
            # 하트비트도 대신 발행 — 카트가 OFFLINE으로 표시되지 않게
            if now - last_heartbeat >= HEARTBEAT_INTERVAL_S:
                client.publish(TOPIC_HEARTBEAT, json.dumps({"timestamp": timestamp}))
                last_heartbeat = now
            time.sleep(1.0 / PUBLISH_HZ)

    worker = threading.Thread(target=publish_loop, daemon=True)
    worker.start()

    print("수동 위치 발행 중 (2Hz). 명령: z1/z2/z3, 사서, 반납, s800.., x,y | speed n | jump <명령> | q")
    try:
        while True:
            raw = input("> ").strip().lower()
            if not raw:
                continue
            if raw == "q":
                break
            jump = raw.startswith("jump ")
            if jump:
                raw = raw[5:].strip()
            if raw.startswith("speed "):
                cart.speed = float(raw.split()[1]) * speed_scale
                print(f"  속도 {float(raw.split()[1])} m/s")
                continue
            if raw in WAYPOINTS:
                px, py = WAYPOINTS[raw]
            elif "," in raw:
                px, py = (float(v) for v in raw.split(","))
            else:
                print("  모르는 명령입니다")
                continue
            # 직선 활주는 구역을 관통해 엉뚱한 진입 팝업을 만든다 —
            # 실제 카트 동선처럼 상단 통로(y=117px)를 경유한다
            cx, cy = to_pixel(cart.x, cart.y)
            route_px = [(cx, CORRIDOR_Y_PX), (px, CORRIDOR_Y_PX), (px, py)]
            waypoints = [to_world(*p) for p in route_px]
            cart.go(waypoints, jump=jump)
            print(f"  -> plan({px:.0f}, {py:.0f}) {'즉시' if jump else '통로 경유 활주'}")
    except (KeyboardInterrupt, EOFError):
        pass
    finally:
        stop.set()
        worker.join(timeout=2)
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    main()
