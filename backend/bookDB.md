# Book DB 정리

## 1. 개요

쫄래쫄래 프로젝트에서 사용하는 도서 데이터베이스의 구조, 공공데이터 적재 및
정제 과정, 테스트 책장, 카트와 슬롯 구성을 정리한 문서입니다.

현재는 서울특별시 동작구 도서관 보유도서 데이터 중 소장 자료가 가장 많은
`사당솔밭도서관` 한 곳만 사용합니다.

## 2. 개발 환경

| 항목 | 값 |
|---|---|
| Java | 21 |
| Spring Boot | 4.1.0 |
| 데이터베이스 | MySQL 8.4 |
| 데이터 접근 | Spring Data JPA |
| 로컬 데이터베이스 | `chollae` |
| CSV 처리 | Apache Commons CSV |

DB 계정 정보와 CSV 경로는 `backend/.env`에 작성하며, `.env`는 Git에 커밋하지
않습니다. 공유 가능한 설정 예시는 `backend/.env.example`에서 관리합니다.

## 3. 도서 도메인 구조

도서 데이터는 `Book`과 `BookCopy`로 분리합니다.

### 3.1 Book

책의 공통 서지 정보를 나타냅니다.

| 필드 | 설명 |
|---|---|
| `id` | 내부 식별자 |
| `isbn` | ISBN 10자리 또는 13자리, 없는 자료는 `NULL` |
| `title` | 제목 |
| `author` | 저자 |
| `publisher` | 출판사 |
| `publicationYear` | 발행연도 |
| `classificationCode` | 청구기호에서 추출한 KDC 코드 |
| `classificationNumber` | 검색과 범위 비교에 사용하는 KDC 숫자 |
| `classificationSection` | 000~900 분류 섹터 |

ISBN이 같은 여러 소장본은 하나의 `Book`을 공유합니다.

### 3.2 BookCopy

도서관이 실제로 보유한 개별 도서 한 권을 나타냅니다.

| 필드 | 설명 |
|---|---|
| `id` | 내부 식별자 |
| `book` | 연결된 `Book` |
| `libraryBookId` | 도서관 등록번호, 중복 불가 |
| `rfidUid` | 개별 도서 RFID, 등록 전에는 `NULL` |
| `callNumber` | 청구기호 |
| `libraryName` | 도서관명 |
| `roomName` | 자료실 |
| `bookshelf` | 실제 책장, 배정 전에는 `NULL` |
| `status` | 소장본 상태 |

사용 가능한 상태 값은 다음과 같습니다.

| 상태 | 의미 |
|---|---|
| `AVAILABLE` | 이용 가능 |
| `LOANED` | 대출 중 |
| `LOST` | 분실 |
| `PROCESSING` | 등록 또는 정리 작업 중 |

관계는 다음과 같습니다.

```text
Book 1개
 ├─ BookCopy 1권
 ├─ BookCopy 2권
 └─ BookCopy 3권
```

## 4. KDC 분류와 책장

현재 사용하는 KDC 상위 분류는 다음과 같습니다.

| 코드 | 분류 |
|---:|---|
| 000 | 총류 |
| 100 | 철학 |
| 200 | 종교 |
| 300 | 사회과학 |
| 400 | 자연과학 |
| 500 | 기술과학 |
| 600 | 예술 |
| 700 | 언어 |
| 800 | 문학 |
| 900 | 역사 |

책장 배정 구조는 다음과 같습니다.

```text
BookCopy.callNumber
  → KDC 분류번호 추출
    → BookshelfRange
      → Bookshelf
        → Zone
          → LibraryMap
```

공공데이터에는 실제 책장 번호가 없으므로 테스트 환경에서는 청구기호에서 추출한
KDC 대분류에 따라 `000`부터 `900`까지 10개 책장에 배정합니다.
현재 모든 `BookCopy`에 테스트 책장이 연결되어 있습니다.

## 5. 공공데이터

사용한 데이터는 공공데이터포털의 `서울특별시 동작구 도서관 보유도서 현황`입니다.

- 데이터 페이지: https://www.data.go.kr/data/15038435/fileData.do
- 파일 형식: CSV
- 문자 인코딩: MS949
- 원본 소장 자료 수: 344,314건
- 주요 열:
  - 관리구분
  - 등록번호
  - 서명
  - 저자
  - 발행자
  - 발행년도
  - 청구기호
  - 국제표준도서번호(ISBN)
  - 자료실

## 6. CSV 가져오기 규칙

CSV 가져오기는 기본적으로 비활성화되어 있으며, `.env`에서 활성화합니다.

```properties
BOOK_IMPORT_ENABLED=true
BOOK_IMPORT_PATH=C:/absolute/path/to/dongjak-books.csv
BOOK_IMPORT_LIMIT=0
BOOK_IMPORT_BATCH_SIZE=500
BOOK_IMPORT_LIBRARY_NAME=사당솔밭도서관
```

| 설정 | 설명 |
|---|---|
| `BOOK_IMPORT_ENABLED` | CSV 가져오기 실행 여부 |
| `BOOK_IMPORT_PATH` | CSV 절대 경로 |
| `BOOK_IMPORT_LIMIT` | 최대 처리 행 수, `0`이면 전체 |
| `BOOK_IMPORT_BATCH_SIZE` | 한 번에 저장할 행 수 |
| `BOOK_IMPORT_LIBRARY_NAME` | 가져올 단일 도서관 |

가져오기 과정에서 다음 규칙을 적용합니다.

1. MS949 인코딩으로 CSV를 읽습니다.
2. `BOOK_IMPORT_LIBRARY_NAME`과 다른 도서관의 행은 제외합니다.
3. 등록번호, 제목, 청구기호 또는 KDC 번호가 없는 행은 제외합니다.
4. ISBN의 하이픈과 공백을 제거하고 10자리 또는 13자리로 정규화합니다.
5. 같은 ISBN은 하나의 `Book`으로 통합합니다.
6. 같은 등록번호의 `BookCopy`가 존재하면 다시 등록하지 않습니다.
7. 청구기호에서 KDC 번호를 추출해 000~900 섹터에 연결합니다.
8. 공공데이터에 없는 RFID와 책장 값은 `NULL`로 저장합니다.
9. 새 소장본의 상태는 `AVAILABLE`로 저장합니다.

가져오기가 끝나면 다음 서버 실행 전에 아래와 같이 비활성화합니다.

```properties
BOOK_IMPORT_ENABLED=false
```

## 7. 데이터 정제 기준

Book 도메인에서 관리할 수 없는 비도서 자료는 제외합니다.

청구기호가 다음 유형으로 시작하면 가져오지 않습니다.

- `DV`, `DVD`
- `LP`
- `CD`, `CD-ROM`
- `오디오`
- `비도서`

정제 결과는 다음과 같습니다.

| 항목 | 수량 |
|---|---:|
| 제거한 DVD | 4,108권 |
| 제거한 LP | 362권 |
| 제거한 전체 비도서 소장본 | 4,470권 |
| 비도서 제거 후 고아가 된 `Book` | 4,223종 |

자료실이나 청구기호에 잡지, 정기간행물 또는 연속간행물로 명시된 데이터는
발견되지 않았습니다. 제목에 `잡지`가 포함됐다는 이유만으로 삭제하면 일반 단행본이
삭제될 수 있으므로 제목 기반 삭제는 수행하지 않습니다.

## 8. 단일 도서관 선정

비도서 정제 후 도서관별 소장본 수를 비교한 결과 `사당솔밭도서관`이 가장 많은
자료를 보유하고 있었습니다.

| 도서관 | 소장본 수 |
|---|---:|
| 사당솔밭도서관 | 67,289권 |
| 김영삼도서관 | 61,961권 |
| 동작영어마루도서관 | 42,368권 |
| 까망돌도서관 | 36,942권 |
| 대방어린이도서관 | 31,458권 |
| 신대방누리도서관 | 29,562권 |
| 동작샘터도서관 | 27,165권 |
| 약수도서관 | 22,615권 |
| 다울작은도서관 | 12,700권 |
| 국사봉숲속작은도서관 | 5,193권 |
| 어린이청소년북카페신대방햇살 | 2,591권 |

프로젝트에서는 사당솔밭도서관만 사용하며 다른 도서관의 `BookCopy`는 삭제했습니다.
삭제 후 어떤 `BookCopy`와도 연결되지 않는 `Book`도 함께 삭제했습니다.

## 9. 현재 DB 상태

| 항목 | 수량 |
|---|---:|
| 사용 도서관 | 사당솔밭도서관 1개 |
| `Book` | 66,411종 |
| `BookCopy` | 67,289권 |
| `ClassificationSection` | 10개 |
| `LibraryMap` | 1개 |
| `Zone` | 1개 |
| `Bookshelf` | 10개 |
| `BookshelfRange` | 10개 |
| `Cart` | 1대 |
| `Slot` | 30개 |
| RFID가 등록된 `BookCopy` | 0권 |
| 도서가 적재된 `Slot` | 0개 |
| 다른 도서관에서 삭제한 `BookCopy` | 272,555권 |
| 다른 도서관 제거 후 삭제한 고아 `Book` | 121,368종 |
| 현재 고아 `Book` | 0종 |
| 현재 비도서 `BookCopy` | 0권 |

## 10. 도서 API

### Book

```text
POST   /api/books
GET    /api/books
GET    /api/books/{id}
PUT    /api/books/{id}
DELETE /api/books/{id}
```

소장본이 연결된 `Book`은 삭제할 수 없습니다.

### BookCopy

```text
POST   /api/book-copies
GET    /api/book-copies
GET    /api/book-copies/{id}
PUT    /api/book-copies/{id}
DELETE /api/book-copies/{id}
```

목록 조회 시 다음 조건을 선택적으로 사용할 수 있습니다.

```text
GET /api/book-copies?bookId={bookId}
GET /api/book-copies?bookshelfId={bookshelfId}
GET /api/book-copies?bookId={bookId}&bookshelfId={bookshelfId}
```

### 도서 위치 조회

RFID가 등록된 소장 도서의 책장과 구역 조회:

```text
GET /api/book-copies/rfid/{rfidUid}/zone
```

RFID가 등록되지 않았거나 일치하는 소장 도서가 없으면 `404 Not Found`를 반환합니다.
도서에 책장이 배정되지 않아 구역을 확인할 수 없으면 `400 Bad Request`를 반환합니다.
실제 RFID가 없는 도서에 임시 UID를 만들거나 저장하지 않습니다.

구역에 배치된 소장 도서 목록 조회:

```text
GET /api/zones/{zoneId}/book-copies
```

- 해당 구역에 배치된 소장 도서 전체를 한 번에 반환
- RFID가 등록되지 않은 소장 도서의 `rfidUid`는 `null`
- 책장 표시 순서, 청구기호, 도서 등록번호 순으로 정렬

### Cart와 Slot

카트 1대의 상태 조회:

```text
GET /api/carts/{cartId}
```

카트의 전체 슬롯과 개별 슬롯 조회:

```text
GET /api/carts/{cartId}/slots
GET /api/carts/{cartId}/slots/{slotNumber}
```

현재 카트 ID는 `1`이며 연결 상태는 `OFFLINE`, 동작 상태는 `IDLE`입니다.
슬롯은 1번부터 30번까지 존재하며 모두 `EMPTY`입니다. 실제 RFID와 도서가 아직
등록되지 않았으므로 각 슬롯의 `book`은 `null`입니다.

## 11. 조회 쿼리

도서관과 자료실의 고유 조합:

```sql
SELECT DISTINCT
    library_name,
    room_name
FROM book_copies
ORDER BY library_name, room_name;
```

자료실별 소장본 수:

```sql
SELECT
    library_name,
    room_name,
    COUNT(*) AS book_count
FROM book_copies
GROUP BY library_name, room_name
ORDER BY library_name, room_name;
```

Book과 BookCopy 수:

```sql
SELECT COUNT(*) AS book_count
FROM books;

SELECT COUNT(*) AS book_copy_count
FROM book_copies;
```

연결된 소장본이 없는 Book:

```sql
SELECT COUNT(*) AS orphan_book_count
FROM books b
WHERE NOT EXISTS (
    SELECT 1
    FROM book_copies bc
    WHERE bc.book_id = b.id
);
```

카트별 슬롯 수와 적재 상태:

```sql
SELECT
    c.id AS cart_id,
    c.name,
    c.connection_status,
    c.operation_status,
    COUNT(s.id) AS slot_count,
    SUM(s.status = 'EMPTY') AS empty_slot_count,
    SUM(s.book_copy_id IS NOT NULL) AS occupied_slot_count
FROM carts c
LEFT JOIN slots s
    ON s.cart_id = c.id
GROUP BY
    c.id,
    c.name,
    c.connection_status,
    c.operation_status;
```

## 12. 관련 커밋

```text
5628748 [refactor] 도서 서지 정보 분리
b1b5716 [feat] 소장 도서 CRUD 추가
1abdb27 [feat] 공공 도서 CSV 가져오기 추가
0200bfd [fix] 비도서 자료 가져오기 제외
b4f89b7 [feat] 단일 도서관 가져오기 필터 추가
5989148 [feat] KDC 테스트 책장 배치 추가
6e6069f [feat] RFID 도서 위치 조회 추가
163d3f9 [fix] 구역 도서 전체 조회 적용
29060ca [feat] 카트 상태 조회 도메인 추가
56a2eae [feat] 카트 슬롯 30개 구성 추가
36dee85 [chore] MySQL 초기 데이터 덤프 추가
```

## 13. 테스트 방 책장 구성

실제 도서관 구조 대신 방 하나에 KDC 대분류별 책장 10개가 있다고 가정합니다.

| 책장 번호 | 분류 | 분류 범위 | 소장본 수 |
|---|---|---:|---:|
| 000 | 총류 | 000.00000 ~ 099.99999 | 1,825 |
| 100 | 철학 | 100.00000 ~ 199.99999 | 3,817 |
| 200 | 종교 | 200.00000 ~ 299.99999 | 1,312 |
| 300 | 사회과학 | 300.00000 ~ 399.99999 | 10,370 |
| 400 | 자연과학 | 400.00000 ~ 499.99999 | 3,857 |
| 500 | 기술과학 | 500.00000 ~ 599.99999 | 5,277 |
| 600 | 예술 | 600.00000 ~ 699.99999 | 2,558 |
| 700 | 언어 | 700.00000 ~ 799.99999 | 2,427 |
| 800 | 문학 | 800.00000 ~ 899.99999 | 30,809 |
| 900 | 역사 | 900.00000 ~ 999.99999 | 5,037 |

구성 결과:

- `LibraryMap`: 테스트 도서관 1개
- `Zone`: 테스트실 1개
- `Bookshelf`: KDC 대분류 책장 10개
- `BookshelfRange`: 책장별 분류 범위 10개
- 책장이 배정된 `BookCopy`: 67,289권
- 책장이 배정되지 않은 `BookCopy`: 0권

소장본은 `Book.classificationNumber`가 아니라 각 `BookCopy.callNumber`에서 분류번호를
추출해 배정합니다. 동일한 책이라도 소장본별 청구기호가 다를 수 있기 때문입니다.
원본 `libraryName`, `roomName`, `callNumber`는 변경하지 않습니다.

재구성이 필요하면 다음 SQL을 실행합니다.

```text
src/main/resources/db/test-room-bookshelves.sql
```

이 SQL은 같은 지도, 구역, 책장을 중복 생성하지 않으며 여러 번 실행할 수 있습니다.

## 14. 카트와 슬롯 구성

테스트 환경은 카트 1대와 슬롯 30개로 구성합니다.

| 항목 | 현재 값 |
|---|---|
| 카트 | `쫄래쫄래 카트` 1대 |
| 카트 연결 상태 | `OFFLINE` |
| 카트 동작 상태 | `IDLE` |
| 카트 좌표와 현재 구역 | `NULL` |
| 슬롯 번호 | 1 ~ 30 |
| 슬롯 상태 | 모두 `EMPTY` |
| 슬롯의 소장 도서 | 모두 `NULL` |
| RFID | 등록된 값 없음 |

카트 상태는 MQTT 연결과 Heartbeat가 연동되면 갱신합니다. 슬롯은 RFID 인식 결과를
받았을 때 실제 `BookCopy`와 연결하며 임시 RFID나 임시 도서를 생성하지 않습니다.

초기 데이터는 다음 SQL로 재구성할 수 있습니다.

```text
src/main/resources/db/cart-slot-seed.sql
```

이 SQL은 여러 번 실행해도 카트와 슬롯을 중복 생성하지 않으며, 기존 슬롯 상태나
도서 배정을 초기값으로 덮어쓰지 않습니다. 자세한 내용은 `CART_SLOT.md`를 참고합니다.

## 15. 전체 DB 덤프

현재 MySQL `chollae` 스키마의 테이블 구조와 데이터를 포함한 전체 덤프를 관리합니다.

```text
backend/chollae-ful.sql
```

덤프에는 도서 66,411종, 소장 도서 67,289권, KDC 테스트 책장, 카트 1대,
슬롯 30개가 포함되어 있습니다. DB 비밀번호나 `.env` 값은 포함하지 않습니다.

빈 MySQL 환경에서 다음과 같이 복원할 수 있습니다.

```powershell
& 'C:\Program Files\MySQL\MySQL Server 8.4\bin\mysql.exe' `
  -uroot -p `
  --default-character-set=utf8mb4 `
  -e 'source C:/ssafy2_1/S15P11C101/backend/chollae-ful.sql'
```

## 16. 다음 작업

1. 실제 테스트 방 크기에 맞춰 지도 크기와 책장 좌표를 조정합니다.
2. MQTT 연결과 Heartbeat로 카트 상태 및 마지막 통신 시각을 갱신합니다.
3. RFID 인식 이벤트로 `BookCopy.rfidUid`와 `Slot.bookCopy`를 연결합니다.
4. 도서가 슬롯에 적재되면 구역별 정리 작업을 생성합니다.
5. 프론트에서 `Bookshelf.id`, `shelfNumber`, 좌표를 사용해 근처 책을 조회합니다.
6. 전체 도서 목록 API에 페이지네이션과 검색 조건을 추가합니다.
7. `800 문학` 책장의 물리적 수납이 필요해지면 하위 분류로 책장을 세분화합니다.
