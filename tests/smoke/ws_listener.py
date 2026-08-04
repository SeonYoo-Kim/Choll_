"""스모크 테스트 보조: 로컬 BE의 /ws/carts/1 이벤트를 로그 파일에 기록한다."""

import argparse
from datetime import datetime
from pathlib import Path

import websocket


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--log", required=True, help="WS 수신 로그 파일 경로")
    args = parser.parse_args()

    log_path = Path(args.log)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    def on_message(ws, message):
        line = f"{datetime.now().isoformat(timespec='seconds')} {message}"
        print(line, flush=True)
        with log_path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")

    ws = websocket.WebSocketApp(
        "ws://localhost:8080/ws/carts/1", on_message=on_message
    )
    ws.run_forever(ping_interval=20)


if __name__ == "__main__":
    main()
