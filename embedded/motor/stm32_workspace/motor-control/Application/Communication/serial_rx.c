#include "serial_rx.h"
#include "main.h"

#define SERIAL_RX_BUFFER_SIZE 64u

static uint8_t          rx_buffer[SERIAL_RX_BUFFER_SIZE];
static volatile uint8_t rx_head  = 0; /* 다음 Pop 위치 */
static volatile uint8_t rx_tail  = 0; /* 다음 Push 위치 */
static volatile uint8_t rx_count = 0; /* 현재 저장된 Byte 수 */

/* PushFromISR(USART2 RX 콜백)와 Pop(main loop)이 동시에 호출되어도
 * head/tail/count가 일관되게 유지되도록 짧게 인터럽트를 막는다. */
static uint32_t SerialRx_EnterCritical(void)
{
    uint32_t primask = __get_PRIMASK();
    __disable_irq();
    return primask;
}

static void SerialRx_ExitCritical(uint32_t primask)
{
    if (!primask)
    {
        __enable_irq();
    }
}

void SerialRx_Init(void)
{
    rx_head  = 0;
    rx_tail  = 0;
    rx_count = 0;
}

uint8_t SerialRx_PushFromISR(uint8_t byte)
{
    uint8_t result = 0;
    uint32_t primask = SerialRx_EnterCritical();

    if (rx_count < SERIAL_RX_BUFFER_SIZE)
    {
        rx_buffer[rx_tail] = byte;
        rx_tail = (uint8_t)((rx_tail + 1u) % SERIAL_RX_BUFFER_SIZE);
        rx_count++;
        result = 1;
    }

    SerialRx_ExitCritical(primask);

    return result;
}

uint8_t SerialRx_Pop(uint8_t *out_byte)
{
    uint8_t result = 0;
    uint32_t primask = SerialRx_EnterCritical();

    if (rx_count > 0u)
    {
        *out_byte = rx_buffer[rx_head];
        rx_head = (uint8_t)((rx_head + 1u) % SERIAL_RX_BUFFER_SIZE);
        rx_count--;
        result = 1;
    }

    SerialRx_ExitCritical(primask);

    return result;
}
