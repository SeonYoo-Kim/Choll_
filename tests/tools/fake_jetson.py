"""가짜 Jetson: mp4/웹캠 → JPEG 프레임 WS 발행 + 가짜 트랙 MQTT 발행.

사용: python fake_jetson.py [지속초] [소스]
  소스: 파일 경로(mp4) 또는 웹캠 인덱스(숫자). 기본 result01.mp4
"""

import json
import math
import sys
import time

import cv2
import paho.mqtt.client as mqtt
import websocket

DEFAULT_VIDEO = r"C:\Users\SSAFY\Downloads\result\refer\result01.mp4"
URL = "ws://localhost:8081/ws/carts/1/video/publish"
FPS = 10.0
JPEG_QUALITY = 70
TRACKS_INTERVAL = 0.2  # 5Hz


def main() -> None:
    duration = float(sys.argv[1]) if len(sys.argv) > 1 else 30.0
    source = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_VIDEO
    capture_source = int(source) if source.isdigit() else source

    ws = websocket.create_connection(URL)
    print(f"video ws connected: {URL}")

    mq = mqtt.Client()
    mq.connect("localhost", 1883)
    mq.loop_start()
    print("mqtt connected: localhost:1883")

    cap = cv2.VideoCapture(capture_source)
    print(f"capture source: {source}, opened={cap.isOpened()}")
    sent = 0
    started = time.time()
    last_tracks_at = 0.0
    try:
        while time.time() - started < duration:
            ok, frame = cap.read()
            if not ok:
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0)  # 파일이면 되감기
                continue
            frame = cv2.resize(frame, (640, 480))
            ok, jpg = cv2.imencode(
                ".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY]
            )
            if ok:
                ws.send_binary(jpg.tobytes())
                sent += 1

            now = time.time()
            if now - last_tracks_at >= TRACKS_INTERVAL:
                last_tracks_at = now
                # 가짜 트랙 2개: 하나는 좌우로 흔들리고 하나는 고정
                t = now - started
                moving_x = int(200 + 120 * math.sin(t * 0.8))
                payload = {
                    "image_width": 640,
                    "image_height": 480,
                    "tracks": [
                        {"id": 16, "x": moving_x, "y": 40, "w": 170, "h": 400},
                        {"id": 23, "x": 30, "y": 200, "w": 70, "h": 150},
                    ],
                }
                mq.publish("status/target", json.dumps(payload))
            time.sleep(1.0 / FPS)
    finally:
        cap.release()
        ws.close()
        mq.loop_stop()
        elapsed = time.time() - started
        print(f"sent {sent} frames in {elapsed:.1f}s (~{sent / elapsed:.1f} fps)")


if __name__ == "__main__":
    main()
