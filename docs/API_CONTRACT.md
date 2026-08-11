# FE-BE API 계약

FE와 BE가 함께 사용하는 REST 경로와 응답 필드를 고정합니다.
실제 구현에서 사용하는 JSON 필드명은 이 문서를 따릅니다.
WebSocket 이벤트·MQTT·ROS2 토픽 계약은 [specs/API_SPEC.md](specs/API_SPEC.md)를 참조하세요.

## 1. 경로 (상태 열은 최종 코드 실측 — 2026-08-11)

| ID | Method | Path | 상태 |
|---|---|---|---|
| CART-01 | GET | `/api/carts/{cartId}` | ✅ 구현 |
| SLOT-01 | GET | `/api/carts/{cartId}/slots` | ✅ 구현 |
| SLOT-02 | GET | `/api/carts/{cartId}/slots/{slotNumber}` | ✅ 구현 |
| SLOT-03 | POST | `/api/carts/{cartId}/slots/{slotNumber}/rescan` | ❌ 미구현 (재인식은 RPi가 자체 재시도) |
| MAP-01 | GET | `/api/maps/{mapId}` | ✅ 구현 |
| MAP-02 | GET | `/api/maps/{mapId}/zones` | ✅ 구현 |
| TASK-01 | GET | `/api/carts/{cartId}/tasks` | △ 슬롯 기준 집계로 대체 |
| TASK-02 | GET | `/api/carts/{cartId}/tasks/progress` | ✅ 구현 (슬롯 기준 집계) |
| TASK-03 | GET | `/api/carts/{cartId}/current-zone/tasks` | △ WS `CURRENT_ZONE_TASKS_UPDATED` 이벤트로 대체 |
| NAV-01 | POST | `/api/carts/{cartId}/navigation` | ✅ 구현 (MQTT `cmd/move/cart` MOVE 하행) |
| NAV-02 | DELETE | `/api/carts/{cartId}/navigation` | ✅ 구현 (MQTT CANCEL 하행) |
| NAV-03 | GET | `/api/carts/{cartId}/navigation` | ❌ 미구현 (상태는 WS `NAVIGATION_STATUS_UPDATED`로 수신) |
| FOLLOW-01 | POST | `/api/carts/{cartId}/follow/pause` | ✅ 구현 (일시정지) |
| FOLLOW-02 | DELETE | `/api/carts/{cartId}/follow` | ✅ 구현 (종료) |
| FOLLOW-03 | POST | `/api/carts/{cartId}/follow/target` | ✅ 구현 (MQTT SELECT_TARGET 하행) |
| FOLLOW-04 | POST | `/api/carts/{cartId}/follow` | ✅ 구현 (시작) |
| FOLLOW-05 | GET | `/api/carts/{cartId}/follow/status` | ❌ 미구현 (상태는 WS `FOLLOW_STATUS_UPDATED`로 수신) |

카트가 한 대이므로 별도 카트 목록 API는 제공하지 않습니다.
`/api/books`, `/api/book-copies`, `/api/bookshelves` 등 도서 마스터 CRUD는 관리용으로 별도 존재합니다 (Swagger 참조).

## 2. 공통 규칙

- DB의 `BIGINT` 식별자는 OpenAPI `integer(int64)`로 표현합니다.
- 아직 수집되지 않은 실제 장비 값은 임시값을 만들지 않고 `null`로 반환합니다.
- 날짜와 시각은 ISO 8601 `date-time` 문자열을 사용합니다.
- 리소스가 없으면 `404 Not Found`, 잘못된 상태나 입력이면 `400 Bad Request`를 반환합니다.
- 비동기 MQTT 명령은 구현 후 `202 Accepted`와 `CommandAccepted`를 반환합니다.

## 3. 응답 DTO

### CartDetail

```json
{
  "id": 1,
  "name": "쫄래쫄래 카트",
  "status": "IDLE",
  "online": false,
  "mapId": null,
  "currentZoneId": null,
  "currentZoneName": null,
  "position": null,
  "lastSeenAt": null
}
```

`status`는 `IDLE`, `MOVING`, `FOLLOWING`, `ERROR` 중 하나입니다.
`online`은 카트 연결 상태가 `ONLINE`인지 여부입니다.

### CartPosition

```json
{
  "x": 1.25,
  "y": 3.5
}
```

### Slot

```json
{
  "id": 1,
  "slotNumber": 1,
  "status": "EMPTY",
  "isTarget": false,
  "book": null,
  "lastDetectedAt": null
}
```

`status`는 `EMPTY`, `OCCUPIED`, `RECOGNIZING`, `RECOGNITION_FAILED` 중 하나입니다.
`isTarget`은 카트의 현재 구역과 도서의 목표 구역이 같은지 나타냅니다.

### SlotBook

```json
{
  "id": 30,
  "bookId": 20,
  "title": "테스트 도서",
  "author": "저자",
  "callNumber": "325.04-공44ㅅ",
  "rfidTagId": null,
  "bookshelfId": 4,
  "bookshelfNumber": "300",
  "shelfZoneId": 1,
  "zoneName": "테스트실"
}
```

`id`는 물리적 소장 도서인 `BookCopy.id`입니다. RFID가 아직 등록되지 않았다면
`rfidTagId`는 `null`입니다.

### MapInfo

```json
{
  "id": 1,
  "name": "테스트 도서관",
  "imageUrl": "/maps/test-room.png",
  "resolution": 0.05,
  "originX": 0,
  "originY": 0,
  "imageWidth": 1000,
  "imageHeight": 600
}
```

### ShelfZone

```json
{
  "id": 1,
  "mapId": 1,
  "code": "TEST_ROOM",
  "name": "테스트실",
  "boundaryData": "[[0,0],[1000,0],[1000,600],[0,600]]"
}
```

`boundaryData`는 현재 DB의 구역 폴리곤 JSON 문자열입니다.

### TaskProgress

```json
{
  "totalBooks": 0,
  "shelvedBooks": 0,
  "remainingBooks": 0,
  "currentZoneSlotNumbers": []
}
```

정리 작업 테이블이 추가되기 전에는 슬롯에 적재된 도서 수를 `totalBooks`와
`remainingBooks`로 사용하고 `shelvedBooks`는 0으로 반환합니다.

## 4. 구현 예정 DTO

### CommandAccepted

```json
{
  "requestId": "UUID",
  "acceptedAt": "2026-07-27T15:00:00+09:00"
}
```

### NavigationStatus

```json
{
  "status": "IDLE",
  "targetZoneId": null,
  "requestId": null
}
```

### FollowStatus

```json
{
  "status": "IDLE",
  "targetId": null,
  "requestId": null
}
```

이동과 추종 상태값은 MQTT 명세가 확정될 때 최종 enum을 추가합니다.

