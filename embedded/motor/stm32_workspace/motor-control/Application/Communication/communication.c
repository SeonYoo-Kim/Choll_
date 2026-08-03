#include "communication.h"
#include "serial_rx.h"
#include "command_parser.h"
#include "app_event.h"
#include "motor.h"
#include "status_reporter.h"
#include "stop_controller.h"
#include "motion_controller.h"

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
 * @brief SET_PI_GAINS 처리: AppEventQueue를 거치지 않고 즉시 적용 + ACK/ERROR 응답
 *
 * SET_WHEEL_VEL 등은 20~30Hz로 반복 전송되므로 AppEventQueue가 가득 차 드롭돼도
 * 다음 전송에서 복구되지만, SET_PI_GAINS는 Tera Term 등에서 1회성으로 입력하는
 * 튜닝 명령이라 드롭되면 응답 없이 조용히 실패한다. 그래서 이 명령만 예외적으로
 * Communication 계층에서 동기적으로 Motor_SetPiGains()를 호출하고, 그 자리에서
 * ACK(PI_GAINS,<kp>,<ki>) 또는 ERROR(ERROR,SET_PI_GAINS,<reason>)를 보낸다
 * (motor/docs/serial_protocol.md 참고).
 */
static void Communication_HandleSetPiGains(const CommandPiGains_t *pi_gains)
{
    if (!pi_gains->format_valid)
    {
        StatusReporter_SendPiGainsError("INVALID_FORMAT");
        return;
    }

    if (!Motor_SetPiGains(pi_gains->kp, pi_gains->ki))
    {
        StatusReporter_SendPiGainsError("OUT_OF_RANGE");
        return;
    }

    StatusReporter_SendPiGainsAck(pi_gains->kp, pi_gains->ki);
}

/**
 * @brief RESET_STALL 처리: AppEventQueue를 거치지 않고 즉시 적용 + ACK/ERROR 응답
 *
 * SET_PI_GAINS와 동일한 이유(1회성 안전 명령, 확정적 ACK/ERROR 필요)로
 * Communication 계층에서 동기적으로 처리한다.
 *
 * StopController_ClearStall()이 성공했을 때만 MotionController_ResetTarget()을
 * 이어서 호출한다 - Stall 이전에 마지막으로 요청됐던 target이 MotionController
 * 안에 그대로 남아 있으면, Fault가 풀리는 순간 StopController_IsStopped()==false가
 * 되어 MotionController_Process()가 그 오래된 target을 Motor에 그대로 흘려보내
 * 자동으로 재출발할 수 있기 때문이다(motor/docs/serial_protocol.md RESET_STALL
 * 절 참고). 실패(Emergency/Latched Safe 활성, 또는 애초에 Stall이 없었음)했을
 * 때는 아무 상태도 건드리지 않고 이유만 응답한다.
 */
static void Communication_HandleResetStall(void)
{
    StopControllerStallResetResult_t result = StopController_ClearStall();

    switch (result)
    {
    case STOP_CONTROLLER_STALL_RESET_OK:
        MotionController_ResetTarget();
        StatusReporter_SendResetStallAck();
        break;

    case STOP_CONTROLLER_STALL_RESET_ESTOP_ACTIVE:
        StatusReporter_SendResetStallError("ESTOP_ACTIVE");
        break;

    case STOP_CONTROLLER_STALL_RESET_LATCHED_SAFE_ACTIVE:
        StatusReporter_SendResetStallError("LATCHED_SAFE_ACTIVE");
        break;

    case STOP_CONTROLLER_STALL_RESET_NO_STALL:
    default:
        StatusReporter_SendResetStallError("NO_STALL");
        break;
    }
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

    if (command.type == COMMAND_TYPE_SET_PI_GAINS)
    {
        Communication_HandleSetPiGains(&command.data.pi_gains);
        return; /* AppEvent를 만들지 않는다 - 위 함수가 즉시 처리 */
    }

    if (command.type == COMMAND_TYPE_RESET_STALL)
    {
        Communication_HandleResetStall();
        return; /* AppEvent를 만들지 않는다 - 위 함수가 즉시 처리 */
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
