# 카트와 슬롯

## 구성

현재 테스트 환경은 카트 1대와 슬롯 30개를 사용합니다.

### Cart

| 컬럼 | 설명 | 초기값 |
|---|---|---|
| `name` | 카트 이름 | `쫄래쫄래 카트` |
| `connection_status` | 연결 상태 | `OFFLINE` |
| `operation_status` | 동작 상태 | `IDLE` |
| `position_x`, `position_y` | 현재 SLAM 좌표 | `NULL` |
| `current_zone_id` | 현재 구역 | `NULL` |
| `last_communication_at` | 마지막 MQTT 통신 시각 | `NULL` |

연결 상태는 `ONLINE`, `OFFLINE`을 사용합니다.
동작 상태는 `IDLE`, `FOLLOWING`, `NAVIGATING`, `ERROR`를 사용합니다.

### Slot

| 컬럼 | 설명 | 초기값 |
|---|---|---|
| `cart_id` | 슬롯을 보유한 카트 | 기본 카트 ID |
| `slot_number` | 카트 안의 슬롯 번호 | `1` ~ `30` |
| `status` | 슬롯 상태 | `EMPTY` |
| `book_copy_id` | 적재된 소장 도서 | `NULL` |
| `last_scanned_at` | 마지막 RFID 인식 시각 | `NULL` |

슬롯 상태는 `EMPTY`, `OCCUPIED`, `RFID_READING`, `RFID_ERROR`를 사용합니다.
같은 카트에서 슬롯 번호는 중복될 수 없고, 슬롯 번호는 1부터 30까지만 허용합니다.
하나의 소장 도서는 동시에 두 슬롯에 배정될 수 없습니다.

## 조회 API

카트 상태 조회:

```text
GET /api/carts/{cartId}
```

카트의 전체 슬롯 조회:

```text
GET /api/carts/{cartId}/slots
```

카트의 개별 슬롯 조회:

```text
GET /api/carts/{cartId}/slots/{slotNumber}
```

빈 슬롯은 `book`을 `null`로 반환합니다. 도서가 적재되면 소장 도서, RFID,
목표 책장과 목표 구역 정보를 함께 반환합니다.

## 초기 데이터

다음 SQL은 카트 1대와 빈 슬롯 30개를 생성합니다.

```text
src/main/resources/db/cart-slot-seed.sql
```

여러 번 실행해도 기존 카트나 슬롯을 중복 생성하지 않으며, 기존 슬롯 상태와
도서 배정을 초기값으로 덮어쓰지 않습니다. 임시 RFID나 임시 도서는 생성하지 않습니다.

