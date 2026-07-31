-- 테스트 방 하나를 7개 이동 존과 KDC 대분류 10개 책장 면으로 구성합니다.
-- 중앙 통로(x=450~550)와 책장 설치 공간은 이동 존에 포함하지 않습니다.
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

INSERT INTO zones (map_id, code, name, polygon_json) VALUES
    (
        @test_map_id,
        'Z1',
        '왼쪽 상단 존',
        '[[0,0],[450,0],[450,150],[0,150]]'
    ),
    (
        @test_map_id,
        'Z2',
        '왼쪽 중상단 존',
        '[[0,200],[450,200],[450,300],[0,300]]'
    ),
    (
        @test_map_id,
        'Z3',
        '왼쪽 중하단 존',
        '[[0,350],[450,350],[450,450],[0,450]]'
    ),
    (
        @test_map_id,
        'Z4',
        '왼쪽 하단 존',
        '[[0,500],[450,500],[450,600],[0,600]]'
    ),
    (
        @test_map_id,
        'Z5',
        '오른쪽 상단 존',
        '[[550,0],[1000,0],[1000,180],[550,180]]'
    ),
    (
        @test_map_id,
        'Z6',
        '오른쪽 중앙 존',
        '[[550,230],[1000,230],[1000,360],[550,360]]'
    ),
    (
        @test_map_id,
        'Z7',
        '오른쪽 하단 존',
        '[[550,410],[1000,410],[1000,600],[550,600]]'
    )
ON DUPLICATE KEY UPDATE
    name = VALUES(name),
    polygon_json = VALUES(polygon_json);

SET @z1_id = (
    SELECT id FROM zones WHERE map_id = @test_map_id AND code = 'Z1'
);
SET @z2_id = (
    SELECT id FROM zones WHERE map_id = @test_map_id AND code = 'Z2'
);
SET @z3_id = (
    SELECT id FROM zones WHERE map_id = @test_map_id AND code = 'Z3'
);
SET @z4_id = (
    SELECT id FROM zones WHERE map_id = @test_map_id AND code = 'Z4'
);
SET @z5_id = (
    SELECT id FROM zones WHERE map_id = @test_map_id AND code = 'Z5'
);
SET @z6_id = (
    SELECT id FROM zones WHERE map_id = @test_map_id AND code = 'Z6'
);
SET @z7_id = (
    SELECT id FROM zones WHERE map_id = @test_map_id AND code = 'Z7'
);
SET @legacy_zone_id = (
    SELECT id FROM zones WHERE map_id = @test_map_id AND code = 'TEST_ROOM'
);

-- 기존 단일 TEST_ROOM 시드를 실행한 DB라면 책장 ID를 유지한 채 새 존으로 이동합니다.
UPDATE bookshelves
SET
    zone_id = CASE shelf_number
        WHEN '000' THEN @z1_id
        WHEN '100' THEN @z2_id
        WHEN '200' THEN @z2_id
        WHEN '300' THEN @z3_id
        WHEN '400' THEN @z3_id
        WHEN '500' THEN @z4_id
        WHEN '600' THEN @z5_id
        WHEN '700' THEN @z6_id
        WHEN '800' THEN @z6_id
        WHEN '900' THEN @z7_id
    END,
    x = CASE
        WHEN shelf_number IN ('000', '100', '200', '300', '400', '500')
            THEN 225.000000
        ELSE 775.000000
    END,
    y = CASE shelf_number
        WHEN '000' THEN 175.000000
        WHEN '100' THEN 175.000000
        WHEN '200' THEN 325.000000
        WHEN '300' THEN 325.000000
        WHEN '400' THEN 475.000000
        WHEN '500' THEN 475.000000
        WHEN '600' THEN 205.000000
        WHEN '700' THEN 205.000000
        WHEN '800' THEN 385.000000
        WHEN '900' THEN 385.000000
    END
WHERE shelf_number IN (
    '000', '100', '200', '300', '400',
    '500', '600', '700', '800', '900'
)
AND zone_id IN (
    SELECT id FROM zones WHERE map_id = @test_map_id
);

UPDATE carts
SET current_zone_id = @z1_id
WHERE current_zone_id = @legacy_zone_id;

DELETE FROM zones
WHERE id = @legacy_zone_id
AND NOT EXISTS (
    SELECT 1 FROM bookshelves WHERE zone_id = @legacy_zone_id
)
AND NOT EXISTS (
    SELECT 1 FROM carts WHERE current_zone_id = @legacy_zone_id
);

INSERT INTO bookshelves (
    zone_id,
    shelf_number,
    name,
    x,
    y,
    display_order
) VALUES
    (@z1_id, '000', '000 총류',       225.000000, 175.000000, 0),
    (@z2_id, '100', '100 철학',       225.000000, 175.000000, 1),
    (@z2_id, '200', '200 종교',       225.000000, 325.000000, 2),
    (@z3_id, '300', '300 사회과학',   225.000000, 325.000000, 3),
    (@z3_id, '400', '400 자연과학',   225.000000, 475.000000, 4),
    (@z4_id, '500', '500 기술과학',   225.000000, 475.000000, 5),
    (@z5_id, '600', '600 예술',       775.000000, 205.000000, 6),
    (@z6_id, '700', '700 언어',       775.000000, 205.000000, 7),
    (@z6_id, '800', '800 문학',       775.000000, 385.000000, 8),
    (@z7_id, '900', '900 역사',       775.000000, 385.000000, 9)
ON DUPLICATE KEY UPDATE
    name = VALUES(name),
    x = VALUES(x),
    y = VALUES(y),
    display_order = VALUES(display_order);

-- 이 테스트 지도의 범위만 다시 만들며 다른 지도의 데이터는 건드리지 않습니다.
DELETE bookshelf_ranges
FROM bookshelf_ranges
JOIN bookshelves
  ON bookshelves.id = bookshelf_ranges.bookshelf_id
JOIN zones
  ON zones.id = bookshelves.zone_id
WHERE zones.map_id = @test_map_id;

INSERT INTO bookshelf_ranges (
    bookshelf_id,
    start_number,
    end_number
)
SELECT
    bookshelves.id,
    CAST(bookshelves.shelf_number AS DECIMAL(10, 5)),
    CAST(bookshelves.shelf_number AS DECIMAL(10, 5)) + 99.99999
FROM bookshelves
JOIN zones
  ON zones.id = bookshelves.zone_id
WHERE zones.map_id = @test_map_id;

-- 소장 도서마다 청구기호에서 KDC 분류번호를 추출해 해당 책장에 연결합니다.
-- Book의 대표 분류번호가 아니라 각 BookCopy의 청구기호를 사용합니다.
UPDATE book_copies AS book_copy
JOIN bookshelves AS bookshelf
  ON bookshelf.shelf_number = LPAD(
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
JOIN zones AS zone
  ON zone.id = bookshelf.zone_id
 AND zone.map_id = @test_map_id
SET book_copy.bookshelf_id = bookshelf.id
WHERE REGEXP_SUBSTR(
    book_copy.call_number,
    '[0-9]{3}(\\.[0-9]+)?'
) IS NOT NULL;

COMMIT;

SELECT
    zones.code AS zone_code,
    bookshelf.shelf_number,
    bookshelf.name,
    bookshelf.id AS bookshelf_id,
    COUNT(book_copy.id) AS book_copy_count
FROM bookshelves AS bookshelf
LEFT JOIN book_copies AS book_copy
  ON book_copy.bookshelf_id = bookshelf.id
JOIN zones
  ON zones.id = bookshelf.zone_id
WHERE zones.map_id = @test_map_id
GROUP BY
    bookshelf.id,
    bookshelf.shelf_number,
    bookshelf.name,
    zones.code
ORDER BY bookshelf.display_order;
