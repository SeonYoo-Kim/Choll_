#include "communication.h"
#include "serial_rx.h"
#include "command_parser.h"
#include "app_event.h"

#include <stdint.h>

/* CommandParser가 처리하는 한 줄의 최대 길이(NUL 포함).
 * "SET_WHEEL_VEL,-123.456789,-123.456789" 형태를 여유 있게 수용한다. */
#define COMMUNICATION_LINE_BUFFER_SIZE 64u

static char    line_buffer[COMMUNICATION_LINE_BUFFER_SIZE];
static uint8_t line_length   = 0;
static uint8_t line_overflow = 0; /* 1이면 다음 개행까지 현재 줄을 폐기 중 */

static void Communication_ResetLine(void)
{
    line_length   = 0;
    line_overflow = 0;
}

/**
 * @brief 개행 문자까지 조립된 한 줄을 파싱하고, 성공하면 AppEventQueue에 등록
 */
static void Communication_HandleCompleteLine(void)
{
    Command_t command;
    AppEvent_t event;

    /* CRLF로 전송된 경우를 대비해 줄 끝의 '\r'을 제거 */
    if ((line_length > 0u) && (line_buffer[line_length - 1u] == '\r'))
    {
        line_length--;
    }

    line_buffer[line_length] = '\0';

    if (line_overflow || (line_length == 0u))
    {
        return; /* 버퍼 초과로 잘린 줄이거나 빈 줄은 무시 */
    }

    if (!CommandParser_Parse(line_buffer, &command))
    {
        return; /* 형식 오류: 무시하고 다음 명령을 기다린다 */
    }

    switch (command.type)
    {
    case COMMAND_TYPE_SET_WHEEL_VEL:
        event.type = APP_EVENT_SET_WHEEL_VELOCITY;
        event.data.wheel_velocity.left_rad_s  = command.data.wheel_velocity.left_rad_s;
        event.data.wheel_velocity.right_rad_s = command.data.wheel_velocity.right_rad_s;
        break;

    case COMMAND_TYPE_STOP:
        event.type = APP_EVENT_OPERATIONAL_STOP;
        break;

    case COMMAND_TYPE_ESTOP:
        event.type = APP_EVENT_EMERGENCY_STOP;
        break;

    default:
        return;
    }

    /* 큐가 가득 차 실패해도 다음 명령(20~30Hz로 재전송되는 SET_WHEEL_VEL 등)에서
     * 다시 시도되므로 별도 재시도 로직 없이 무시한다. */
    (void)AppEventQueue_Push(&event);
}

void Communication_Init(void)
{
    SerialRx_Init();
    Communication_ResetLine();
}

void Communication_Process(void)
{
    uint8_t byte;

    while (SerialRx_Pop(&byte))
    {
        if (byte == '\n')
        {
            Communication_HandleCompleteLine();
            Communication_ResetLine();
            continue;
        }

        if (line_length < (COMMUNICATION_LINE_BUFFER_SIZE - 1u))
        {
            line_buffer[line_length] = (char)byte;
            line_length++;
        }
        else
        {
            /* 버퍼 초과: 다음 개행까지 이 줄을 폐기한다 */
            line_overflow = 1;
        }
    }
}
