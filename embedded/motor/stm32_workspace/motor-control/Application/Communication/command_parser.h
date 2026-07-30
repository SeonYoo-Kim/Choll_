#ifndef COMMAND_PARSER_H
#define COMMAND_PARSER_H

#include <stdint.h>

/* =========================================================
 * CommandParser
 * - 완성된 한 줄(개행 제외) 문자열을 검증하고 명령 구조체로 변환한다.
 * - Motor/Controller/AppEventQueue를 알지 못하며, 순수 파싱만 수행한다.
 * - sscanf 대신 bounded parsing + strtof를 사용해 코드 크기와
 *   입력 안전성을 확보한다.
 * - 지원 명령: SET_WHEEL_VEL,<left_rad_s>,<right_rad_s> / STOP / ESTOP
 * ========================================================= */

typedef enum
{
    COMMAND_TYPE_SET_WHEEL_VEL = 0,
    COMMAND_TYPE_STOP,
    COMMAND_TYPE_ESTOP
} CommandType_t;

typedef struct
{
    float left_rad_s;
    float right_rad_s;
} CommandWheelVelocity_t;

typedef struct
{
    CommandType_t type;

    /* type == COMMAND_TYPE_SET_WHEEL_VEL 일 때만 유효 */
    union
    {
        CommandWheelVelocity_t wheel_velocity;
    } data;
} Command_t;

/* line은 널 종료 문자열이며 개행 문자를 포함하지 않는다고 가정한다.
 * 성공하면 1을 반환하고 out_command를 채운다. 형식 오류, 범위 초과,
 * NaN/Infinity, 여분의 토큰 등 어떤 이유로든 실패하면 0을 반환하고
 * out_command는 변경하지 않는다. */
uint8_t CommandParser_Parse(const char *line, Command_t *out_command);

#endif /* COMMAND_PARSER_H */
