"""스모크 테스트 보조: cmd/move/cart 구독 로거 (+선택: 가짜 하트비트 발행).

- 기본: BE가 브로커로 내리는 명령을 로그 파일에 기록만 한다 (실카트 모드).
- --heartbeat: 실카트(RPi)가 없을 때 status/cart 하트비트를 5초 간격 발행한다.
자격증명은 backend/.env에서 읽는다 (값을 출력하지 않음).
"""

import argparse
import json
import os
import time
from datetime import datetime
from pathlib import Path

import paho.mqtt.client as mqtt

REPO_ROOT = Path(__file__).resolve().parents[2]
ENV_PATH = REPO_ROOT / "backend" / ".env"


def load_env(path: Path) -> dict:
    values = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip()
    return values


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--log", required=True, help="명령 수신 로그 파일 경로")
    parser.add_argument("--heartbeat", action="store_true", help="가짜 하트비트 발행")
    parser.add_argument("--duration", type=int, default=3600, help="유지 시간(초)")
    args = parser.parse_args()

    log_path = Path(args.log)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    env = load_env(ENV_PATH)
    broker = env["MQTT_BROKER_URL"].replace("tcp://", "")
    host, _, port = broker.partition(":")

    # client_id가 겹치면 브로커가 기존 접속을 끊어내므로(재실행 시 서로 밀어냄) PID로 고유화
    client = mqtt.Client(
        mqtt.CallbackAPIVersion.VERSION2,
        client_id=f"chollae-smoke-observer-{os.getpid()}",
    )
    if env.get("MQTT_USERNAME"):
        client.username_pw_set(env["MQTT_USERNAME"], env.get("MQTT_PASSWORD", ""))

    def on_connect(c, userdata, flags, reason_code, properties):
        print(f"connected rc={reason_code}", flush=True)
        c.subscribe("cmd/move/cart")

    def on_message(c, userdata, msg):
        line = (
            f"{datetime.now().isoformat(timespec='seconds')} "
            f"{msg.topic} {msg.payload.decode('utf-8')}"
        )
        print(line, flush=True)
        with log_path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")

    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(host, int(port or 1883), keepalive=30)
    client.loop_start()

    end = time.time() + args.duration
    while time.time() < end:
        if args.heartbeat:
            client.publish(
                "status/cart", json.dumps({"timestamp": datetime.now().isoformat()})
            )
        time.sleep(5)

    client.loop_stop()
    client.disconnect()


if __name__ == "__main__":
    main()
