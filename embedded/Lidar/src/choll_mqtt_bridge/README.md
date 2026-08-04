# choll_mqtt_bridge — MQTT↔ROS2 브릿지

BE Mosquitto 브로커(`your-server.example.com:1883`)와 Jetson 내부 ROS2 사이의
번역기. ROS2 노드는 DDS만, BE는 MQTT만 말하므로 둘 다 하는 이 노드가
젯슨에서 돌며 중계한다. AI 파트 작업 불필요 — EM-BE MQTT 명세서의 EM 측 구현.

## 매핑 (정본: launch/bridge.launch.py)

| 방향 | MQTT (EM-BE 명세) | ROS2 (AI-EM 명세) | 처리 |
|---|---|---|---|
| BE→카트 | MQTT-04 `cmd/move/cart` MOVE | ROS2-14 `/cart/target_pose` | `target{x,y}`(SLAM 미터) → PoseStamped(map). pixel만 오면 무시+경고 |
| BE→카트 | MQTT-04 `cmd/move/cart` CANCEL | ROS2-15 `/cart/cancel` | String(data=requestId) |
| BE→카트 | MQTT-04 SELECT_TARGET | — (무시) | AI `fe_bridge_node`가 `/select_target` 변환 담당 (backend/CLAUDE.md 실측) — 이중 처리 금지 |
| BE→카트 | MQTT-04 FOLLOW_START/PAUSE/STOP | (미연결) | EM/AI 수신측 계약 미확정 — 경고 로그만 |
| 카트→BE | MQTT-01 `status/position` | ROS2-08 `/robot_pose` | 쿼터니언→yaw 변환, 기본 2Hz 스로틀, QoS0 |

MQTT-01 페이로드 — **BE 파서 실측 계약**
(`backend/.../mqtt/position/MqttPositionMessageHandler.java`의
`PositionPayload(x, y, timestamp)`, 2026-08-04 코드 확인):

```json
{"x":1.235,"y":-0.988,"yaw":1.5708,"timestamp":"1970-01-02T00:00:00.500Z"}
```

- `x`/`y`: SLAM 미터 (BE `mqtt.position-unit=meters` 전환 필요 — 기본 pixels)
- `timestamp`: ISO-8601 UTC(Java Instant). 스탬프 미설정 시 생략 → BE가 수신 시각 사용
- `yaw`: 라디안, CCW+(REP 103), map +x 기준 — **BE 미파싱 추가 필드** (WS
  CART_POSITION_UPDATE의 yaw가 임시 0이라 파서 확장 제안)
- 명령 수신은 QoS1 구독, paho 자동 재접속(1~30s 백오프)

## 실행

```bash
ros2 launch choll_mqtt_bridge bridge.launch.py                        # Jetson
ros2 launch choll_mqtt_bridge bridge.launch.py client_id:=choll-laptop-bridge  # 노트북 검증
```

⚠ client_id가 같은 클라이언트 둘이 붙으면 브로커가 서로 강퇴시켜
무한 재접속 루프가 된다 — 기기마다 다르게 줄 것.

## 의존성

`python3-paho-mqtt` (1.x). Jetson: `sudo apt install python3-paho-mqtt`.
노트북은 PyPI 1.6.1 소스를 `~/.local/lib/python3.10/site-packages`에 설치함.

## 검증 (Nav2 없이)

```bash
ros2 run choll_mqtt_bridge mqtt_bridge   # "MQTT 접속·구독 완료" 로그 확인
# 다른 터미널에서 BE 대신 명령 주입:
python3 - <<'EOF'
import paho.mqtt.publish as publish
publish.single(
    "cmd/move/cart",
    '{"requestId":"test-1","command":"CANCEL"}',
    hostname="your-server.example.com",
    auth={"username": "choll", "password": "CHANGE_ME"},
)
EOF
ros2 topic echo /cart/cancel --once       # data: test-1 수신 확인
```

## 순수 로직 테스트 (ROS·paho 불필요)

```bash
python3 -m pytest src/choll_mqtt_bridge/test/test_bridge_logic.py -q
```

## TODO-확인 (팀 합의 후 확정)

- [ ] BE: `mqtt.position-unit=meters` 전환 + `library_maps`(id=`mqtt.map-id`)
      행에 최종 map.yaml의 resolution·origin 입력 (EM 발행 시작 조건)
- [ ] BE: 파서에 `yaw` 필드 추가 (WS CART_POSITION_UPDATE yaw 임시 0 해소)
- [ ] BE: 위치 발행 주기 합의 (기본 2Hz)
- [ ] BE: 주행 결과 상행 토픽 신설 — 제안 `status/nav`
      `{"requestId","status"}` (BE가 NAVIGATION_STATUS_UPDATED의
      STARTED/ARRIVED/FAILED를 "카트 상행 결과 토픽 확정 후"로 보류 중,
      `/cart/nav_status` 7종이 원천). 확정 시 이 브릿지에 발행 추가
- [ ] EM/AI: FOLLOW_START/PAUSE/STOP 수신 주체·동작 합의
      (BE 정의: /target_position을 nav 목표로 소비 시작/해제하는 모드 전환)
