# MQTT 카트 위치 수신 테스트

로봇이 MQTT로 보낸 카트 좌표를 백엔드가 수신하고, 최근 좌표와 현재 구역을
계산하는 테스트용 구현입니다.

## 동작 방식

- 구독 토픽: `carts/+/telemetry/position`
- 실제 메시지 예시 토픽: `carts/1/telemetry/position`
- 카트별 최근 위치 20개를 메모리에 유지합니다.
- 좌표가 구역 다각형 안에 있는지 계산합니다. 경계선 위의 좌표도 해당 구역으로
  판단합니다.
- 좌표 오차로 구역이 계속 바뀌는 것을 줄이기 위해 같은 구역이 3회 연속 감지된
  후 `carts.current_zone_id`를 변경합니다.
- MQTT는 기본적으로 꺼져 있어 브로커가 없는 평상시 개발과 테스트를 방해하지
  않습니다.

메시지 본문은 다음 형식입니다.

```json
{
  "x": 100.0,
  "y": 100.0,
  "timestamp": "2026-07-27T07:00:00Z"
}
```

`x`와 `y`는 필수이며 `timestamp`를 생략하면 백엔드 수신 시각을 사용합니다.
토픽의 카트 ID는 DB의 `carts.id`에 실제로 존재해야 합니다.

## 로컬 실행

먼저 로컬 MQTT 브로커가 `localhost:1883`에서 실행 중이어야 합니다. 예를 들어
Mosquitto를 사용할 수 있습니다.

`backend/.env`에 아래 설정을 추가하거나 수정합니다.

```properties
MQTT_ENABLED=true
MQTT_BROKER_URL=tcp://localhost:1883
MQTT_CLIENT_ID=chollae-backend
MQTT_POSITION_TOPIC=carts/+/telemetry/position
MQTT_QOS=0
```

첫 번째 터미널에서 백엔드를 실행합니다.

```powershell
cd backend
.\gradlew.bat bootRun
```

두 번째 터미널에서 카트 1번의 테스트 좌표 5개를 발행합니다.

```powershell
cd backend
.\gradlew.bat mqttTestPublish
```

다른 카트 ID를 테스트하려면 해당 카트가 DB에 존재하는지 확인한 뒤 다음처럼
지정합니다.

```powershell
$env:MQTT_TEST_CART_ID="2"
.\gradlew.bat mqttTestPublish
```

테스트 발행기는 `(100,100)`부터 `(180,140)`까지 총 5개의 좌표를 0.5초 간격으로
보냅니다. 정상 수신되면 백엔드 로그에 원본 메시지가 다음처럼 표시됩니다.

```text
[MQTT RECEIVE] topic=carts/1/telemetry/position, payload={"x":100.000000,...}
```

이어지는 처리 로그에서는 카트 ID, 좌표, 감지 구역, 안정화 여부, 현재 버퍼 크기를
확인할 수 있습니다.

## 현재 구현 범위

최근 위치 20개는 재시작하면 사라지는 테스트용 메모리 데이터입니다. 현재 구역과
마지막 좌표 및 통신 시각은 `carts` 테이블에 반영됩니다. 프론트 실시간 전달용
WebSocket 연결은 다음 단계에서 추가합니다.
