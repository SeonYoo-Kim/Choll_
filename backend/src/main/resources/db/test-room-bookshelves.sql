-- 테스트 방 하나를 KDC 대분류 10개 책장으로 구성합니다.
-- 여러 번 실행해도 같은 지도/구역/책장을 갱신하도록 작성했습니다.

START TRANSACTION;

INSERT INTO library_maps (
    name,
    image_url,
    resolution,
    origin_x,
    origin_y,
    width,
    height
) VALUES (
    '테스트 도서관',
    '/maps/test-room.png',
    0.050000,
    0.000000,
    0.000000,
    1000,
    600
)
ON DUPLICATE KEY UPDATE
    id = LAST_INSERT_ID(id),
    image_url = VALUES(image_url),
    resolution = VALUES(resolution),
    origin_x = VALUES(origin_x),
    origin_y = VALUES(origin_y),
    width = VALUES(width),
    height = VALUES(height);

SET @test_map_id = LAST_INSERT_ID();

INSERT INTO zones (
    map_id,
    code,
    name,
    polygon_json
) VALUES (
    @test_map_id,
    'TEST_ROOM',
    '테스트실',
    '[[0,0],[1000,0],[1000,600],[0,600]]'
)
ON DUPLICATE KEY UPDATE
    id = LAST_INSERT_ID(id),
    name = VALUES(name),
    polygon_json = VALUES(polygon_json);

SET @test_zone_id = LAST_INSERT_ID();

INSERT INTO bookshelves (
    zone_id,
    shelf_number,
    name,
    x,
    y,
    display_order
) VALUES
    (@test_zone_id, '000', '000 총류',       100.000000, 150.000000, 0),
    (@test_zone_id, '100', '100 철학',       300.000000, 150.000000, 1),
    (@test_zone_id, '200', '200 종교',       500.000000, 150.000000, 2),
    (@test_zone_id, '300', '300 사회과학',   700.000000, 150.000000, 3),
    (@test_zone_id, '400', '400 자연과학',   900.000000, 150.000000, 4),
    (@test_zone_id, '500', '500 기술과학',   100.000000, 450.000000, 5),
    (@test_zone_id, '600', '600 예술',       300.000000, 450.000000, 6),
    (@test_zone_id, '700', '700 언어',       500.000000, 450.000000, 7),
    (@test_zone_id, '800', '800 문학',       700.000000, 450.000000, 8),
    (@test_zone_id, '900', '900 역사',       900.000000, 450.000000, 9)
ON DUPLICATE KEY UPDATE
    name = VALUES(name),
    x = VALUES(x),
    y = VALUES(y),
    display_order = VALUES(display_order);

-- 이 테스트 구역의 범위만 다시 만들며 다른 지도/구역의 데이터는 건드리지 않습니다.
DELETE bookshelf_ranges
FROM bookshelf_ranges
JOIN bookshelves
  ON bookshelves.id = bookshelf_ranges.bookshelf_id
WHERE bookshelves.zone_id = @test_zone_id;

INSERT INTO bookshelf_ranges (
    bookshelf_id,
    start_number,
    end_number
)
SELECT
    id,
    CAST(shelf_number AS DECIMAL(10, 5)),
    CAST(shelf_number AS DECIMAL(10, 5)) + 99.99999
FROM bookshelves
WHERE zone_id = @test_zone_id;

-- 소장 도서마다 청구기호에서 KDC 분류번호를 추출해 해당 책장에 연결합니다.
-- Book의 대표 분류번호가 아니라 각 BookCopy의 청구기호를 사용합니다.
UPDATE book_copies AS book_copy
JOIN bookshelves AS bookshelf
  ON bookshelf.zone_id = @test_zone_id
 AND bookshelf.shelf_number = LPAD(
        FLOOR(
            CAST(
                REGEXP_SUBSTR(
                    book_copy.call_number,
                    '[0-9]{3}(\\.[0-9]+)?'
                ) AS DECIMAL(10, 5)
            ) / 100
        ) * 100,
        3,
        '0'
    )
SET book_copy.bookshelf_id = bookshelf.id
WHERE REGEXP_SUBSTR(
    book_copy.call_number,
    '[0-9]{3}(\\.[0-9]+)?'
) IS NOT NULL;

COMMIT;

SELECT
    bookshelf.shelf_number,
    bookshelf.name,
    bookshelf.id AS bookshelf_id,
    COUNT(book_copy.id) AS book_copy_count
FROM bookshelves AS bookshelf
LEFT JOIN book_copies AS book_copy
  ON book_copy.bookshelf_id = bookshelf.id
WHERE bookshelf.zone_id = @test_zone_id
GROUP BY bookshelf.id, bookshelf.shelf_number, bookshelf.name
ORDER BY bookshelf.display_order;

