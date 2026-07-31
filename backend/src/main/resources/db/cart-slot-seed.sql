-- 카트 1대와 빈 슬롯 12개를 생성합니다.
-- 실제 RFID나 소장 도서는 연결하지 않으며, 여러 번 실행해도 중복 생성되지 않습니다.
-- 슬롯이 30개이던 시절 시드된 DB에서는 13번 이후 슬롯을 삭제해 12개로 맞춥니다.

START TRANSACTION;

INSERT INTO carts (
    name,
    connection_status,
    operation_status,
    position_x,
    position_y,
    current_zone_id,
    last_communication_at
) VALUES (
    '쫄래쫄래 카트',
    'OFFLINE',
    'IDLE',
    NULL,
    NULL,
    NULL,
    NULL
)
ON DUPLICATE KEY UPDATE
    id = LAST_INSERT_ID(id);

SET @default_cart_id = LAST_INSERT_ID();

DELETE FROM slots
WHERE cart_id = @default_cart_id
  AND slot_number > 12;

INSERT INTO slots (
    cart_id,
    slot_number,
    status,
    book_copy_id,
    last_scanned_at
) VALUES
    (@default_cart_id,  1, 'EMPTY', NULL, NULL),
    (@default_cart_id,  2, 'EMPTY', NULL, NULL),
    (@default_cart_id,  3, 'EMPTY', NULL, NULL),
    (@default_cart_id,  4, 'EMPTY', NULL, NULL),
    (@default_cart_id,  5, 'EMPTY', NULL, NULL),
    (@default_cart_id,  6, 'EMPTY', NULL, NULL),
    (@default_cart_id,  7, 'EMPTY', NULL, NULL),
    (@default_cart_id,  8, 'EMPTY', NULL, NULL),
    (@default_cart_id,  9, 'EMPTY', NULL, NULL),
    (@default_cart_id, 10, 'EMPTY', NULL, NULL),
    (@default_cart_id, 11, 'EMPTY', NULL, NULL),
    (@default_cart_id, 12, 'EMPTY', NULL, NULL)
ON DUPLICATE KEY UPDATE
    id = LAST_INSERT_ID(id);

COMMIT;

SELECT
    cart.id AS cart_id,
    cart.name,
    cart.connection_status,
    cart.operation_status,
    COUNT(slot.id) AS slot_count,
    SUM(slot.status = 'EMPTY') AS empty_slot_count
FROM carts AS cart
LEFT JOIN slots AS slot
  ON slot.cart_id = cart.id
WHERE cart.id = @default_cart_id
GROUP BY
    cart.id,
    cart.name,
    cart.connection_status,
    cart.operation_status;

