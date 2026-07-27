# 공공 도서 데이터 가져오기

## 데이터 원본

- 공공데이터포털: `서울특별시 동작구 도서관 보유도서 현황`
- 페이지: https://www.data.go.kr/data/15038435/fileData.do
- CSV 인코딩: MS949
- 주요 열: 관리구분, 등록번호, 서명, 저자, 발행자, 발행년도, 청구기호, ISBN, 자료실

CSV에는 실제 책장 번호가 없으므로 가져오기 시 `book_copies.bookshelf_id`는 비워 둡니다.
청구기호에서 KDC 분류 번호를 추출해 000~900 상위 섹터에 연결하고, 실제 도서관의
책장별 분류 범위가 정해진 뒤 `BookshelfRange`를 사용해 책장을 배정합니다.

## 실행

1. 공공데이터포털에서 CSV를 내려받습니다.
2. `backend/.env`에 아래 항목을 추가합니다.

```properties
BOOK_IMPORT_ENABLED=true
BOOK_IMPORT_PATH=C:/absolute/path/to/dongjak-books.csv
BOOK_IMPORT_LIMIT=5000
BOOK_IMPORT_BATCH_SIZE=500
BOOK_IMPORT_LIBRARY_NAME=사당솔밭도서관
```

3. `backend` 디렉터리에서 서버를 실행합니다.

```powershell
.\gradlew.bat bootRun
```

- `BOOK_IMPORT_LIMIT=0`: 전체 데이터 가져오기
- `BOOK_IMPORT_LIBRARY_NAME`: 지정한 단일 도서관의 자료만 가져오기
- 같은 등록번호는 다시 실행해도 건너뜁니다.
- 공공 CSV에는 RFID 값이 없으므로 `rfid_uid`는 비워 두며, 카트에 태그를 등록할 때 갱신합니다.
- DVD, LP, CD 등 청구기호로 명확히 식별되는 비도서 자료는 가져오지 않습니다.
- 가져오기가 끝나면 다음 실행 전에 `BOOK_IMPORT_ENABLED=false`로 되돌립니다.
