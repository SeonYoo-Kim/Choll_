#ifndef SERIAL_RX_H
#define SERIAL_RX_H

#include <stdint.h>

/* =========================================================
 * SerialRx
 * - USB Serial(USART2) 수신 Byte를 저장하는 고정 크기 Ring Buffer.
 * - PushFromISR는 HAL_UART_RxCpltCallback에서 호출되며, Byte 하나를
 *   버퍼에 넣는 것 외의 동작(파싱, Motor/Controller 호출 등)은 하지 않는다.
 * - Pop은 Communication_Process()에서 main loop 컨텍스트로 호출된다.
 * ========================================================= */

void SerialRx_Init(void);

/* ISR 컨텍스트 전용 호출부. 큐가 가득 차면 0(실패, Byte 유실)을 반환한다. */
uint8_t SerialRx_PushFromISR(uint8_t byte);

/* main loop에서 호출: Byte 하나를 꺼낸다. 성공 시 1과 함께 out_byte에 기록, 비어있으면 0 */
uint8_t SerialRx_Pop(uint8_t *out_byte);

#endif /* SERIAL_RX_H */
