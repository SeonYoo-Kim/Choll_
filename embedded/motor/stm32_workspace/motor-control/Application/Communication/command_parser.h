#ifndef COMMAND_PARSER_H
#define COMMAND_PARSER_H

#include <stdint.h>

/* =========================================================
 * CommandParser
 * - 완성된 한 줄(개행 제외) 문자열을 검증하고 명령 구조체로 변환한다.
 * - Motor/Controller/AppEventQueue를 알지 못하며, 순수 파싱만 수행한다.
 *   (SET_PI_GAINS의 Kp/Ki 허용 범위 검증은 예외적으로 Motor_SetPiGains()가
 *   담당한다 — 아래 CommandPiGains_t 주석 참고)
 * - sscanf 대신 bounded parsing + strtof를 사용해 코드 크기와
 *   입력 안전성을 확보한다.
 * - 지원 명령: SET_WHEEL_VEL,<left_rad_s>,<right_rad_s> / STOP / ESTOP /
 *   SET_PI_GAINS,<kp>,<ki> / RESET_STALL
 * ========================================================= */

typedef enum
{
    COMMAND_TYPE_SET_WHEEL_VEL = 0,
    COMMAND_TYPE_STOP,
    COMMAND_TYPE_ESTOP,
    COMMAND_TYPE_SET_PI_GAINS,
    COMMAND_TYPE_RESET_STALL
} CommandType_t;

typedef struct
{
    float left_rad_s;
    float right_rad_s;
} CommandWheelVelocity_t;

/* type == COMMAND_TYPE_SET_PI_GAINS 일 때만 유효.
 * format_valid == 0이면 kp/ki 본문 파싱에 실패했다는 뜻이며(형식 오류,
 * NaN/Infinity 포함) kp/ki는 0.0f로 채워진다 — 호출자(Communication)가
 * ERROR,SET_PI_GAINS,INVALID_FORMAT을 응답해야 한다는 신호로 쓴다.
 * Kp/Ki의 허용 범위(motor_config.h MOTOR_PI_KP/KI_MIN/MAX) 검증은 여기서
 * 하지 않으며 Motor_SetPiGains()가 담당한다(CommandParser는 순수 파싱만
 * 수행한다는 원칙 유지). */
typedef struct
{
    float   kp;
    float   ki;
    uint8_t format_valid;
} CommandPiGains_t;

typedef struct
{
    CommandType_t type;

    /* type에 대응하는 멤버만 유효 (SET_WHEEL_VEL -> wheel_velocity,
     * SET_PI_GAINS -> pi_gains, STOP/ESTOP은 payload 없음) */
    union
    {
        CommandWheelVelocity_t wheel_velocity;
        CommandPiGains_t       pi_gains;
    } data;
} Command_t;

/* line은 널 종료 문자열이며 개행 문자를 포함하지 않는다고 가정한다.
 * 성공하면 1을 반환하고 out_command를 채운다.
 *
 * SET_WHEEL_VEL/STOP/ESTOP/RESET_STALL: 형식 오류, NaN/Infinity, 여분의
 * 토큰 등 어떤 이유로든 실패하면 0을 반환하고 out_command는 변경하지
 * 않는다(기존 동작 유지). RESET_STALL은 STOP/ESTOP과 동일하게 문자열
 * 전체 일치(strcmp)만으로 파싱되며 payload가 없다 — ACK/ERROR 응답은
 * CommandParser가 아니라 Communication이 StopController_ClearStall()의
 * 반환값을 보고 결정한다(SET_PI_GAINS와 달리 형식 오류 자체를 구분해
 * 알려줄 필요가 없어 더 단순한 STOP/ESTOP 패턴을 그대로 따른다).
 *
 * SET_PI_GAINS: 토큰("SET_PI_GAINS,")이 매칭되면 본문 파싱 성공 여부와
 * 무관하게 항상 1을 반환하고 out_command->type = COMMAND_TYPE_SET_PI_GAINS로
 * 채운다 — 형식 오류를 CommandPiGains_t.format_valid로 알려줘야 Communication이
 * ERROR,SET_PI_GAINS,INVALID_FORMAT을 응답할 수 있기 때문이다(다른 세 명령과의
 * 유일한 차이). 토큰 자체가 매칭되지 않으면(알 수 없는 명령) 다른 명령과 동일하게
 * 0을 반환한다. */
uint8_t CommandParser_Parse(const char *line, Command_t *out_command);

#endif /* COMMAND_PARSER_H */
