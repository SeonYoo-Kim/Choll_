#include "status_reporter.h"
#include "motor.h"
#include "main.h"

#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <math.h>

/* USART2(ST-LINK VCP). main.c에서 정의되며 헤더로 extern 선언되어 있지 않아
 * Motor 모듈이 htim2/htim3/htim4/htim8를 extern하는 것과 같은 방식으로 참조한다. */
extern UART_HandleTypeDef huart2;

/* STATUS Packet 송신 주기(ms). 10Hz 또는 20Hz 중 하나로 이 매크로만 바꿔 조정한다. */
#define STATUS_REPORTER_INTERVAL_MS 100u /* 10Hz */

/* "STATUS,-999.99,-999.99,-999.99,-999.99,-99,-99,-2147483648,-2147483648\r\n"
 * (72byte + NUL = 73byte) 기준 여유 포함. LPWM/RPWM(-99~99)과 LE/RE(int32_t 전체
 * 범위)는 이 범위를 벗어나지 않지만, LT/RT는 SET_WHEEL_VEL에 아직 clamp가 없어
 * (motion_controller.c의 MOTION_CONTROLLER_MAX_WHEEL_RAD_S TODO 참고) 이론상
 * -999.99~999.99를 벗어날 수 있다. 그 경우 snprintf가 이 버퍼 크기 안에서 안전하게
 * 잘라내므로 오버플로우는 없지만 줄 끝 "\r\n"이 잘려 프레이밍이 깨질 수 있다.
 * (docs/serial_protocol.md STATUS Packet 절 참고) */
#define STATUS_REPORTER_LINE_BUFFER_SIZE 96u

/* HAL_UART_Transmit()은 블로킹이지만, 위 버퍼 크기 기준 115200bps에서
 * 전송 시간은 최대 약 8ms이므로 Main Loop 다른 Process들의 tick 주기(수백ms)에
 * 비해 무시할 수 있는 수준이다(이번 단계 유지 결정). Wheel Velocity PID로 제어
 * 루프 주기가 더 촘촘해지면 HAL_UART_Transmit_IT/DMA 전환을 검토해야 한다
 * (docs/serial_protocol.md TODO 참고). */
#define STATUS_REPORTER_UART_TIMEOUT_MS 20u

/* "PI_GAINS,50.0000,20.0000\r\n" (26byte + NUL = 27byte) 기준 여유 포함.
 * Kp/Ki는 motor_config.h MOTOR_PI_KP/KI_MAX(각각 50.0f/20.0f)로 상한이
 * clamp되어 있어 STATUS Packet의 LT/RT(clamp 없음)와 달리 최악의 경우 길이가
 * 고정적으로 짧다. */
#define PI_GAINS_ACK_LINE_BUFFER_SIZE 40u

/* "ERROR,SET_PI_GAINS,INVALID_FORMAT\r\n" 기준 여유 포함(reason은 이 파일 안
 * 호출부에서만 짧은 상수 문자열로 전달됨, Communication_HandleSetPiGains 참고). */
#define PI_GAINS_ERROR_LINE_BUFFER_SIZE 48u

/* "FAULT,STALL,BOTH\r\n" 기준 여유 포함. cause 문자열은 이 파일 안에서만
 * "LEFT"/"RIGHT"/"BOTH" 중 하나로 고정되므로 길이가 짧게 고정적이다. */
#define STALL_FAULT_LINE_BUFFER_SIZE 24u

/* "FAULT_CLEARED,STALL\r\n" 고정 문자열 기준(가변 필드 없음). */
#define STALL_CLEARED_LINE_BUFFER_SIZE 24u

/* "STALL_RESET,OK\r\n" 고정 문자열 기준(가변 필드 없음). */
#define RESET_STALL_ACK_LINE_BUFFER_SIZE 20u

/* "ERROR,RESET_STALL,LATCHED_SAFE_ACTIVE\r\n" 기준 여유 포함(reason은 이 파일
 * 안 호출부에서만 짧은 상수 문자열로 전달됨, Communication_HandleResetStall 참고). */
#define RESET_STALL_ERROR_LINE_BUFFER_SIZE 48u

static uint32_t last_report_tick = 0;

/**
 * @brief 부호 있는 실수를 소수점 둘째 자리까지 문자열로 변환
 *
 * 이 프로젝트의 빌드는 --specs=nano.specs(newlib-nano)를 사용하며 별도
 * 링커 옵션(-u _printf_float) 없이는 snprintf가 %f를 지원하지 않는다.
 * 따라서 float를 정수 연산(반올림 후 정수부/소수부 분리)만으로 포맷한다.
 */
static void StatusReporter_FormatFloat2(float value, char *out_buf, size_t buf_size)
{
    int32_t scaled = (int32_t)lroundf(value * 100.0f);
    int32_t int_part;
    int32_t frac_part;

    if (scaled < 0)
    {
        scaled = -scaled;
        int_part  = scaled / 100;
        frac_part = scaled % 100;
        (void)snprintf(out_buf, buf_size, "-%ld.%02ld", (long)int_part, (long)frac_part);
    }
    else
    {
        int_part  = scaled / 100;
        frac_part = scaled % 100;
        (void)snprintf(out_buf, buf_size, "%ld.%02ld", (long)int_part, (long)frac_part);
    }
}

/**
 * @brief 부호 있는 실수를 소수점 넷째 자리까지 문자열로 변환 (SET_PI_GAINS 응답 전용)
 *
 * StatusReporter_FormatFloat2()와 동일한 이유(newlib-nano, %f 미지원)로 정수
 * 연산만 사용한다. STATUS Packet(둘째 자리)과 별도 함수로 둔 이유는, 기존
 * STATUS Packet 포맷/정밀도에 어떤 영향도 주지 않기 위함이다. Kp/Ki는
 * motor_config.h 범위(최대 50.0f)로 이미 clamp되어 있어 오버플로우 우려가 없다.
 */
static void StatusReporter_FormatFloat4(float value, char *out_buf, size_t buf_size)
{
    int32_t scaled = (int32_t)lroundf(value * 10000.0f);
    int32_t int_part;
    int32_t frac_part;

    if (scaled < 0)
    {
        scaled = -scaled;
        int_part  = scaled / 10000;
        frac_part = scaled % 10000;
        (void)snprintf(out_buf, buf_size, "-%ld.%04ld", (long)int_part, (long)frac_part);
    }
    else
    {
        int_part  = scaled / 10000;
        frac_part = scaled % 10000;
        (void)snprintf(out_buf, buf_size, "%ld.%04ld", (long)int_part, (long)frac_part);
    }
}

/**
 * @brief STATUS Packet 한 줄 조립
 *
 * 필드 순서(LT,LA,RT,RA,LPWM,RPWM,LE,RE)는 docs/serial_protocol.md의
 * Protocol v1 정의를 따르며 임의로 바꾸지 않는다. left_actual_rad_s /
 * right_actual_rad_s는 Motor_GetActualWheelVelocity()가 엔코더 실측값으로
 * 계산한 값이며(motor_config.h MOTOR_SAMPLE_PERIOD_SEC 주기 갱신), Wheel
 * Velocity PID는 아직 미구현이므로 이 값은 제어에는 아직 쓰이지 않고 텔레메트리
 * 용도로만 사용된다.
 */
static int StatusReporter_BuildPacket(char *out_buf, size_t buf_size,
                                       float left_target_rad_s, float left_actual_rad_s,
                                       float right_target_rad_s, float right_actual_rad_s,
                                       int16_t left_pwm, int16_t right_pwm,
                                       int32_t left_encoder, int32_t right_encoder)
{
    char lt[16];
    char la[16];
    char rt[16];
    char ra[16];

    StatusReporter_FormatFloat2(left_target_rad_s, lt, sizeof(lt));
    StatusReporter_FormatFloat2(left_actual_rad_s, la, sizeof(la));
    StatusReporter_FormatFloat2(right_target_rad_s, rt, sizeof(rt));
    StatusReporter_FormatFloat2(right_actual_rad_s, ra, sizeof(ra));

    return snprintf(out_buf, buf_size, "STATUS,%s,%s,%s,%s,%d,%d,%ld,%ld\r\n",
                     lt, la, rt, ra,
                     (int)left_pwm, (int)right_pwm,
                     (long)left_encoder, (long)right_encoder);
}

void StatusReporter_Init(void)
{
    last_report_tick = HAL_GetTick();
}

void StatusReporter_Process(void)
{
    char    line[STATUS_REPORTER_LINE_BUFFER_SIZE];
    float   target_left_rad_s;
    float   target_right_rad_s;
    float   actual_left_rad_s;
    float   actual_right_rad_s;
    int16_t left_pwm;
    int16_t right_pwm;
    int     line_length;

    if ((HAL_GetTick() - last_report_tick) < STATUS_REPORTER_INTERVAL_MS)
    {
        return;
    }
    last_report_tick = HAL_GetTick();

    Motor_GetTargetWheelVelocity(&target_left_rad_s, &target_right_rad_s);
    Motor_GetActualWheelVelocity(&actual_left_rad_s, &actual_right_rad_s);
    Motor_GetLastPwm(&left_pwm, &right_pwm);

    /* motor1 = 왼쪽, motor2 = 오른쪽 (motor.h Motor1/Motor2 정의 참고) */
    line_length = StatusReporter_BuildPacket(line, sizeof(line),
                                              target_left_rad_s, actual_left_rad_s,
                                              target_right_rad_s, actual_right_rad_s,
                                              left_pwm, right_pwm,
                                              motor1_encoder_total, motor2_encoder_total);

    if (line_length > 0)
    {
        (void)HAL_UART_Transmit(&huart2, (uint8_t *)line, (uint16_t)line_length,
                                 STATUS_REPORTER_UART_TIMEOUT_MS);
    }
}

void StatusReporter_SendPiGainsAck(float kp, float ki)
{
    char line[PI_GAINS_ACK_LINE_BUFFER_SIZE];
    char kp_str[16];
    char ki_str[16];
    int  line_length;

    StatusReporter_FormatFloat4(kp, kp_str, sizeof(kp_str));
    StatusReporter_FormatFloat4(ki, ki_str, sizeof(ki_str));

    line_length = snprintf(line, sizeof(line), "PI_GAINS,%s,%s\r\n", kp_str, ki_str);

    if (line_length > 0)
    {
        (void)HAL_UART_Transmit(&huart2, (uint8_t *)line, (uint16_t)line_length,
                                 STATUS_REPORTER_UART_TIMEOUT_MS);
    }
}

void StatusReporter_SendPiGainsError(const char *reason)
{
    char line[PI_GAINS_ERROR_LINE_BUFFER_SIZE];
    int  line_length;

    line_length = snprintf(line, sizeof(line), "ERROR,SET_PI_GAINS,%s\r\n", reason);

    if (line_length > 0)
    {
        (void)HAL_UART_Transmit(&huart2, (uint8_t *)line, (uint16_t)line_length,
                                 STATUS_REPORTER_UART_TIMEOUT_MS);
    }
}

void StatusReporter_SendStallFault(MotorStallCause_t cause)
{
    char line[STALL_FAULT_LINE_BUFFER_SIZE];
    int  line_length;
    const char *cause_str;

    switch (cause)
    {
    case MOTOR_STALL_LEFT:
        cause_str = "LEFT";
        break;
    case MOTOR_STALL_RIGHT:
        cause_str = "RIGHT";
        break;
    case MOTOR_STALL_BOTH:
        cause_str = "BOTH";
        break;
    default:
        /* 호출부(StopController_Process())가 NONE으로는 부르지 않지만,
         * 방어적으로 처리한다. */
        return;
    }

    line_length = snprintf(line, sizeof(line), "FAULT,STALL,%s\r\n", cause_str);

    if (line_length > 0)
    {
        (void)HAL_UART_Transmit(&huart2, (uint8_t *)line, (uint16_t)line_length,
                                 STATUS_REPORTER_UART_TIMEOUT_MS);
    }
}

void StatusReporter_SendStallCleared(void)
{
    char line[STALL_CLEARED_LINE_BUFFER_SIZE];
    int  line_length;

    line_length = snprintf(line, sizeof(line), "FAULT_CLEARED,STALL\r\n");

    if (line_length > 0)
    {
        (void)HAL_UART_Transmit(&huart2, (uint8_t *)line, (uint16_t)line_length,
                                 STATUS_REPORTER_UART_TIMEOUT_MS);
    }
}

void StatusReporter_SendResetStallAck(void)
{
    char line[RESET_STALL_ACK_LINE_BUFFER_SIZE];
    int  line_length;

    line_length = snprintf(line, sizeof(line), "STALL_RESET,OK\r\n");

    if (line_length > 0)
    {
        (void)HAL_UART_Transmit(&huart2, (uint8_t *)line, (uint16_t)line_length,
                                 STATUS_REPORTER_UART_TIMEOUT_MS);
    }
}

void StatusReporter_SendResetStallError(const char *reason)
{
    char line[RESET_STALL_ERROR_LINE_BUFFER_SIZE];
    int  line_length;

    line_length = snprintf(line, sizeof(line), "ERROR,RESET_STALL,%s\r\n", reason);

    if (line_length > 0)
    {
        (void)HAL_UART_Transmit(&huart2, (uint8_t *)line, (uint16_t)line_length,
                                 STATUS_REPORTER_UART_TIMEOUT_MS);
    }
}
