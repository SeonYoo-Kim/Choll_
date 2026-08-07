-- 테스트 방을 3개 존(Z1 우측 / Z2 중앙 / Z3 좌측)과 책장 4면으로 재구성합니다.
-- 기존 7존 시드(test-room-bookshelves.sql)를 실행한 DB에서 이어 실행할 수 있습니다.
--   존:   Z1 우측 존 / Z2 중앙 존 / Z3 좌측 존  (Z4~Z7과 legacy TEST_ROOM은 삭제)
--   책장: 000 총류→Z1 / 100 철학→Z2 / 200 종교→Z2 / 800 문학→Z3  (나머지 6면 삭제)
-- 여러 번 실행해도 같은 결과가 되도록(멱등) 작성했으며, 책장 id를 유지해 도서 연결을 보존합니다.
--
-- ⚠️ 아래 "실측값" 블록만 채우면 됩니다. 좌표계는 모두 **BE SLAM 지도 이미지 픽셀, 좌상단 원점**입니다.
--    (SLAM 미터 ↔ 픽셀 변환은 BE의 SlamCoordinateConverter가 map 메타로 처리합니다.)
--
-- ⚠️ FE 평면도(frontend/src/assets/map.png) 위에서 재지 마십시오 — 좌표 공간이 다릅니다.
--    2026-08-06부터 FE는 화면 그림·구역 클릭 영역을 번들 평면도와 zones.ts로 정하고,
--    서버에서는 구역 **id만** code(Z1·Z2·Z3)로 조인해 받습니다.
--    따라서 여기의 polygon_json은 화면을 그리지 않고, **카트 현재 구역 판정**(LED·정리 대상)에만
--    쓰입니다. 판정 대상인 카트 좌표가 SLAM 미터→SLAM 지도 픽셀로 변환된 값이므로,
--    폴리곤도 반드시 그 픽셀 공간(= library_maps.width·height)에서 재야 합니다.
--
-- 실행: mysql -u <user> -p <db> < test-room-3zones.sql

START TRANSACTION;

-- ─────────────────────────────────────────────────────────────
-- 실측값 (여기만 수정)
-- ─────────────────────────────────────────────────────────────

-- 지도 메타 — name이 기존 행과 같으면 그 행을 갱신합니다.
-- 현재 운영 DB의 지도는 id=2 (`mqtt.map-id` 기본값)이며 name='테스트 도서관'입니다.
SET @map_name       = '테스트 도서관';
-- FE는 이 그림을 띄우지 않습니다(번들 평면도 사용, 2026-08-06) — MAP-01 응답의 필수 필드라 값만 채웁니다
SET @map_image_url  = '/maps/test-room.png';
-- 아래 좌표는 모두 평면도(frontend/src/assets/map.png) 1000x600 격자에서 측정했습니다.
-- FE가 서버 그림을 쓰지 않게 된 뒤로 library_maps는 "그림"이 아니라 **좌표계 정의**입니다 —
-- 실제 SLAM png의 픽셀 크기와 같을 필요가 없고, (width·height·resolution·origin)이 평면도와
-- 같은 바닥 범위를 가리키기만 하면 됩니다. 그래서 격자는 평면도에 맞춰 1000x600으로 고정하고,
-- resolution·origin만 실측으로 채웁니다.
SET @map_width      = 1000;
SET @map_height     = 600;
-- TODO: 방 가로 실측 길이(m) / 1000. 예) 가로 10m면 0.010000
--       평면도가 5:3이므로 방도 5:3으로 재야 세로가 맞습니다 (가로 10m ↔ 세로 6m)
SET @map_resolution = 0.010000;
-- TODO: 평면도 좌하단(0, 600px)에 해당하는 지점의 SLAM 좌표(m) — map.yaml의 origin과 다릅니다.
--       SLAM 지도 전체가 아니라 이 평면도가 덮는 범위의 좌하단입니다
SET @map_origin_x   = 0.000000;
SET @map_origin_y   = 0.000000;

-- 존 경계 폴리곤 — '[[x,y],[x,y],...]' (꼭짓점 3개 이상, 닫는 점 반복 불필요).
-- 평면도의 청록색 통로 3개 = 카트가 들어가 정차하는 영역.
-- 용도가 두 가지입니다: (1) 카트 현재 구역 판정, (2) 구역 밖 클릭의 스냅 대상
--   (NavigationService.snapIntoZone — 서가·테이블을 누르면 이 폴리곤 안 최근접점으로 옮깁니다).
--   그래서 폴리곤을 서가까지 넓게 잡으면 스냅 결과가 서가 안이 됩니다. 통로만 덮으세요.
-- 존끼리 겹치지 않게 할 것: ZoneLocator가 첫 매칭을 쓰므로 겹치면 판정이 임의가 됩니다.
-- code는 FE zones.ts의 ZONE_CODES(Z1·Z2·Z3)와 정확히 같아야 id 조인이 됩니다.
SET @z1_polygon = '[[755,121],[967,121],[967,564],[755,564]]';  -- 우측 통로 (000 총류 서가 앞)
SET @z2_polygon = '[[389,121],[601,121],[601,564],[389,564]]';  -- 중앙 통로 (100 철학·200 종교 앞)
SET @z3_polygon = '[[24,121],[236,121],[236,564],[24,564]]';    -- 좌측 통로 (800 문학 서가 앞)

-- 책장 위치 — 평면도의 어두운 서가 면 중심 (1000x600 픽셀, 캔버스 픽셀 스캔 실측).
-- 좌→우로 800 · 200 | 통로 | 100 · 000 순서이고 네 면의 y는 같습니다 (y 231~453의 중심).
SET @shelf_000_x = 710.000000; SET @shelf_000_y = 342.000000;
SET @shelf_100_x = 646.000000; SET @shelf_100_y = 342.000000;
SET @shelf_200_x = 345.000000; SET @shelf_200_y = 342.000000;
SET @shelf_800_x = 280.000000; SET @shelf_800_y = 342.000000;

-- ─────────────────────────────────────────────────────────────
-- 1. 지도
-- ─────────────────────────────────────────────────────────────

INSERT INTO library_maps (
    name, image_url, resolution, origin_x, origin_y, width, height
) VALUES (
    @map_name, @map_image_url, @map_resolution,
    @map_origin_x, @map_origin_y, @map_width, @map_height
)
ON DUPLICATE KEY UPDATE
    id         = LAST_INSERT_ID(id),
    image_url  = VALUES(image_url),
    resolution = VALUES(resolution),
    origin_x   = VALUES(origin_x),
    origin_y   = VALUES(origin_y),
    width      = VALUES(width),
    height     = VALUES(height);

SET @map_id = LAST_INSERT_ID();

-- ─────────────────────────────────────────────────────────────
-- 2. 존 3개 (Z1~Z3) — code는 그대로 두고 이름·경계만 갱신
--    FE는 code 오름차순으로 "1구역, 2구역, 3구역"을 만듭니다.
-- ─────────────────────────────────────────────────────────────

INSERT INTO zones (map_id, code, name, polygon_json) VALUES
    (@map_id, 'Z1', '우측 존', @z1_polygon),
    (@map_id, 'Z2', '중앙 존', @z2_polygon),
    (@map_id, 'Z3', '좌측 존', @z3_polygon)
ON DUPLICATE KEY UPDATE
    name         = VALUES(name),
    polygon_json = VALUES(polygon_json);

SET @z1_id = (SELECT id FROM zones WHERE map_id = @map_id AND code = 'Z1');
SET @z2_id = (SELECT id FROM zones WHERE map_id = @map_id AND code = 'Z2');
SET @z3_id = (SELECT id FROM zones WHERE map_id = @map_id AND code = 'Z3');

-- ─────────────────────────────────────────────────────────────
-- 3. 도서-책장 연결 해제 (이 지도의 책장에 대해서만)
--    아래 8번에서 청구기호 기준으로 다시 연결합니다. 없어진 책장(300~700, 900)에
--    걸려 있던 사본은 여기서 끊겨 bookshelf_id = NULL로 남습니다.
-- ─────────────────────────────────────────────────────────────

UPDATE book_copies AS book_copy
JOIN bookshelves AS bookshelf ON bookshelf.id = book_copy.bookshelf_id
JOIN zones       AS zone      ON zone.id = bookshelf.zone_id
SET book_copy.bookshelf_id = NULL
WHERE zone.map_id = @map_id;

-- ─────────────────────────────────────────────────────────────
-- 4. 남길 책장 4면을 새 존으로 이동 (id 유지 → 작업·이력이 끊기지 않음)
--    800은 기존 Z6에 있으므로, 아래 6번에서 Z6를 지우기 전에 반드시 먼저 옮깁니다.
-- ─────────────────────────────────────────────────────────────

UPDATE bookshelves
SET
    zone_id = CASE shelf_number
        WHEN '000' THEN @z1_id
        WHEN '100' THEN @z2_id
        WHEN '200' THEN @z2_id
        WHEN '800' THEN @z3_id
    END,
    x = CASE shelf_number
        WHEN '000' THEN @shelf_000_x
        WHEN '100' THEN @shelf_100_x
        WHEN '200' THEN @shelf_200_x
        WHEN '800' THEN @shelf_800_x
    END,
    y = CASE shelf_number
        WHEN '000' THEN @shelf_000_y
        WHEN '100' THEN @shelf_100_y
        WHEN '200' THEN @shelf_200_y
        WHEN '800' THEN @shelf_800_y
    END
WHERE shelf_number IN ('000', '100', '200', '800')
AND zone_id IN (SELECT id FROM zones WHERE map_id = @map_id);

-- ─────────────────────────────────────────────────────────────
-- 5. 쓰지 않는 책장 삭제 (이 지도 한정) — 범위 → 책장 순서
-- ─────────────────────────────────────────────────────────────

DELETE bookshelf_range
FROM bookshelf_ranges AS bookshelf_range
JOIN bookshelves AS bookshelf ON bookshelf.id = bookshelf_range.bookshelf_id
JOIN zones       AS zone      ON zone.id = bookshelf.zone_id
WHERE zone.map_id = @map_id
AND bookshelf.shelf_number NOT IN ('000', '100', '200', '800');

DELETE bookshelf
FROM bookshelves AS bookshelf
JOIN zones AS zone ON zone.id = bookshelf.zone_id
WHERE zone.map_id = @map_id
AND bookshelf.shelf_number NOT IN ('000', '100', '200', '800');

-- ─────────────────────────────────────────────────────────────
-- 6. 쓰지 않는 존 삭제 (Z4~Z7, legacy TEST_ROOM)
--    카트가 그 존을 가리키고 있으면 FK가 걸리므로 먼저 떼어냅니다.
--    임의의 존으로 옮기지 않고 NULL로 둡니다 — 다음 위치 수신 때 다시 판정됩니다.
-- ─────────────────────────────────────────────────────────────

UPDATE carts
SET current_zone_id = NULL
WHERE current_zone_id IN (
    SELECT id FROM zones WHERE map_id = @map_id AND code NOT IN ('Z1', 'Z2', 'Z3')
);

DELETE FROM zones
WHERE map_id = @map_id
AND code NOT IN ('Z1', 'Z2', 'Z3');

-- ─────────────────────────────────────────────────────────────
-- 7. 책장 4면 확정 (빈 DB면 생성, 4번을 거친 DB면 이름·순서만 갱신)
-- ─────────────────────────────────────────────────────────────

INSERT INTO bookshelves (zone_id, shelf_number, name, x, y, display_order) VALUES
    (@z1_id, '000', '000 총류', @shelf_000_x, @shelf_000_y, 0),
    (@z2_id, '100', '100 철학', @shelf_100_x, @shelf_100_y, 1),
    (@z2_id, '200', '200 종교', @shelf_200_x, @shelf_200_y, 2),
    (@z3_id, '800', '800 문학', @shelf_800_x, @shelf_800_y, 3)
ON DUPLICATE KEY UPDATE
    name          = VALUES(name),
    x             = VALUES(x),
    y             = VALUES(y),
    display_order = VALUES(display_order);

-- ─────────────────────────────────────────────────────────────
-- 8. 책장 담당 범위 + 도서 연결 재구성
--    범위는 KDC 백단위 한 구간(예: 800 ~ 899.99999).
-- ─────────────────────────────────────────────────────────────

DELETE bookshelf_range
FROM bookshelf_ranges AS bookshelf_range
JOIN bookshelves AS bookshelf ON bookshelf.id = bookshelf_range.bookshelf_id
JOIN zones       AS zone      ON zone.id = bookshelf.zone_id
WHERE zone.map_id = @map_id;

INSERT INTO bookshelf_ranges (bookshelf_id, start_number, end_number)
SELECT
    bookshelf.id,
    CAST(bookshelf.shelf_number AS DECIMAL(10, 5)),
    CAST(bookshelf.shelf_number AS DECIMAL(10, 5)) + 99.99999
FROM bookshelves AS bookshelf
JOIN zones AS zone ON zone.id = bookshelf.zone_id
WHERE zone.map_id = @map_id;

-- 사본의 청구기호에서 KDC 분류번호를 뽑아 담당 책장에 연결합니다.
-- (Book의 대표 분류번호가 아니라 BookCopy의 청구기호 기준)
-- 책장이 없는 분류(300~700, 900)의 사본은 3번에서 끊긴 채 NULL로 남습니다.
UPDATE book_copies AS book_copy
JOIN bookshelves AS bookshelf
  ON bookshelf.shelf_number = LPAD(
        FLOOR(
            CAST(
                REGEXP_SUBSTR(book_copy.call_number, '[0-9]{3}(\\.[0-9]+)?') AS DECIMAL(10, 5)
            ) / 100
        ) * 100,
        3,
        '0'
    )
JOIN zones AS zone
  ON zone.id = bookshelf.zone_id
 AND zone.map_id = @map_id
SET book_copy.bookshelf_id = bookshelf.id
WHERE REGEXP_SUBSTR(book_copy.call_number, '[0-9]{3}(\\.[0-9]+)?') IS NOT NULL;

COMMIT;

-- ─────────────────────────────────────────────────────────────
-- 확인
-- ─────────────────────────────────────────────────────────────

SELECT id, code, name, polygon_json
FROM zones
WHERE map_id = @map_id
ORDER BY code;

SELECT
    zone.code AS zone_code,
    zone.name AS zone_name,
    bookshelf.id AS bookshelf_id,
    bookshelf.shelf_number,
    bookshelf.name,
    bookshelf.x,
    bookshelf.y,
    COUNT(book_copy.id) AS book_copy_count
FROM bookshelves AS bookshelf
JOIN zones AS zone ON zone.id = bookshelf.zone_id
LEFT JOIN book_copies AS book_copy ON book_copy.bookshelf_id = bookshelf.id
WHERE zone.map_id = @map_id
GROUP BY
    bookshelf.id, bookshelf.shelf_number, bookshelf.name,
    bookshelf.x, bookshelf.y, zone.code, zone.name
ORDER BY bookshelf.display_order;
