#!/usr/bin/env python3
"""브로커의 모든 토픽(`#`)을 구독해 토픽별 건수·Hz·최근 페이로드를 출력한다.

**읽기 전용** — 아무것도 발행하지 않는다. mosquitto_sub 가 설치돼 있지 않아
paho 로 직접 구현한다. client_id 를 브릿지와 다르게 잡아야 상호 강퇴가 없다.

🔴 자격증명은 하드코딩하지 않는다 (저장소가 공개될 수 있다). 환경변수로 받는다:

    export CHOLL_MQTT_USER=<계정>
    export CHOLL_MQTT_PASS=<비밀번호>
    python3 scripts/mqtt_sniff.py [초]

브로커 호스트는 `CHOLL_MQTT_HOST` 로 덮어쓸 수 있다 (기본값은 데모용 임시 브로커).
"""

from __future__ import annotations

import collections
import json
import os
import sys
import time

import paho.mqtt.client as mqtt

# 데모용 임시 브로커. SSAFY 리소스로 프로젝트 종료 시 회수된다.
BROKER_HOST = os.environ.get("CHOLL_MQTT_HOST", "your-server.example.com")
BROKER_PORT = int(os.environ.get("CHOLL_MQTT_PORT", "1883"))
BROKER_USER = os.environ.get("CHOLL_MQTT_USER", "")
BROKER_PASS = os.environ.get("CHOLL_MQTT_PASS", "")

counts: collections.Counter[str] = collections.Counter()
last_payload: dict[str, str] = {}
first_seen: dict[str, float] = {}


def on_connect(client: mqtt.Client, userdata: object, flags: dict, rc: int) -> None:
    """접속 결과를 출력하고 전체 토픽을 구독한다."""
    # rc=0 만 성공이다. fe_bridge_node 가 rc 를 검사하지 않아 rc=5(인증거부)를
    # 성공으로 로깅한 전례가 있다 (2026-08-08 TEST_LOG).
    if rc != 0:
        print(f"🔴 접속 실패 rc={rc} (0=성공, 4=인증정보오류, 5=인증거부)")
        return
    print(f"✅ 접속 성공 {BROKER_HOST}:{BROKER_PORT} — '#' 구독")
    client.subscribe("#", qos=0)


def on_message(client: mqtt.Client, userdata: object, msg: mqtt.MQTTMessage) -> None:
    """토픽별 건수와 최근 페이로드를 기록한다."""
    counts[msg.topic] += 1
    first_seen.setdefault(msg.topic, time.monotonic())
    try:
        last_payload[msg.topic] = msg.payload.decode("utf-8")[:200]
    except UnicodeDecodeError:
        last_payload[msg.topic] = f"<binary {len(msg.payload)} bytes>"


def main() -> None:
    """지정한 시간 동안 관측하고 요약을 출력한다."""
    if not BROKER_USER or not BROKER_PASS:
        print(
            "🔴 자격증명이 없습니다. 환경변수를 설정하세요:\n"
            "   export CHOLL_MQTT_USER=<계정>\n"
            "   export CHOLL_MQTT_PASS=<비밀번호>",
            file=sys.stderr,
        )
        sys.exit(2)

    duration = float(sys.argv[1]) if len(sys.argv) > 1 else 15.0

    client = mqtt.Client(client_id="choll-sniffer-readonly")
    client.username_pw_set(BROKER_USER, BROKER_PASS)
    client.on_connect = on_connect
    client.on_message = on_message

    try:
        client.connect(BROKER_HOST, BROKER_PORT, keepalive=30)
    except OSError as exc:
        print(f"🔴 접속 불가: {exc}")
        sys.exit(1)

    client.loop_start()
    time.sleep(duration)
    client.loop_stop()
    client.disconnect()

    print(f"\n===== {duration:.0f}초 관측 결과 =====")
    if not counts:
        print("🔴 아무 메시지도 안 옴 — 발행자가 전부 죽었거나 브로커가 비어 있다")
        return

    for topic, n in sorted(counts.items(), key=lambda kv: -kv[1]):
        elapsed = max(time.monotonic() - first_seen[topic], 1e-6)
        hz = n / elapsed
        payload = last_payload.get(topic, "")
        try:  # JSON 이면 키만 요약해 한 줄로
            obj = json.loads(payload)
            if isinstance(obj, dict):
                payload = json.dumps(obj, ensure_ascii=False)[:160]
        except (ValueError, TypeError):
            pass
        print(f"\n[{topic}]  {n}건  ~{hz:.2f} Hz")
        print(f"   {payload}")


if __name__ == "__main__":
    main()
