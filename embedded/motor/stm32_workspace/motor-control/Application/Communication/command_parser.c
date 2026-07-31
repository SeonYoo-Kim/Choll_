#include "command_parser.h"

#include <math.h>
#include <stdlib.h>
#include <string.h>

#define COMMAND_TOKEN_SET_WHEEL_VEL "SET_WHEEL_VEL"
#define COMMAND_TOKEN_STOP          "STOP"
#define COMMAND_TOKEN_ESTOP         "ESTOP"

/**
 * @brief line이 token으로 정확히 시작하고 그 다음이 delimiter인지 확인
 *
 * strncmp만으로는 "SET_WHEEL_VEL"과 "SET_WHEEL_VELOCITY"를 구분할 수 없으므로
 * token 직후 문자까지 함께 검사한다. 성공 시 delimiter 다음 위치를 out_rest에 담는다.
 */
static uint8_t CommandParser_MatchToken(const char *line, const char *token, char delimiter, const char **out_rest)
{
    size_t token_len = strlen(token);

    if (strncmp(line, token, token_len) != 0)
    {
        return 0;
    }

    if (line[token_len] != delimiter)
    {
        return 0;
    }

    *out_rest = &line[token_len + 1u];
    return 1;
}

/**
 * @brief 문자열에서 float 하나를 파싱하고 이어지는 문자가 expected_terminator인지 확인
 *
 * strtof가 아무 것도 소비하지 못했거나(형식 오류), 결과가 NaN/Infinity이거나,
 * 파싱 직후 문자가 expected_terminator가 아니면(여분의 토큰 등) 실패로 처리한다.
 */
static uint8_t CommandParser_ParseFloat(const char *text, char expected_terminator,
                                         float *out_value, const char **out_rest)
{
    char *endptr = NULL;
    float value = strtof(text, &endptr);

    if (endptr == text)
    {
        return 0; /* 변환된 문자가 없음 (예: "abc") */
    }

    if (!isfinite(value))
    {
        return 0; /* NaN/Infinity 거부 */
    }

    if (*endptr != expected_terminator)
    {
        return 0; /* 예상치 못한 위치의 문자 (예: "1,2,3"의 여분 토큰) */
    }

    *out_value = value;
    *out_rest = endptr + 1;
    return 1;
}

static uint8_t CommandParser_ParseSetWheelVel(const char *rest, Command_t *out_command)
{
    float left = 0.0f;
    float right = 0.0f;
    const char *after_left = NULL;
    const char *after_right = NULL;

    if (!CommandParser_ParseFloat(rest, ',', &left, &after_left))
    {
        return 0;
    }

    /* 두 번째 값 뒤에는 반드시 문자열 끝(NUL)이 와야 한다 (여분 토큰 거부) */
    if (!CommandParser_ParseFloat(after_left, '\0', &right, &after_right))
    {
        return 0;
    }

    out_command->type = COMMAND_TYPE_SET_WHEEL_VEL;
    out_command->data.wheel_velocity.left_rad_s = left;
    out_command->data.wheel_velocity.right_rad_s = right;
    return 1;
}

uint8_t CommandParser_Parse(const char *line, Command_t *out_command)
{
    const char *rest = NULL;

    if ((line == NULL) || (out_command == NULL))
    {
        return 0;
    }

    if (CommandParser_MatchToken(line, COMMAND_TOKEN_SET_WHEEL_VEL, ',', &rest))
    {
        return CommandParser_ParseSetWheelVel(rest, out_command);
    }

    if (strcmp(line, COMMAND_TOKEN_STOP) == 0)
    {
        out_command->type = COMMAND_TYPE_STOP;
        return 1;
    }

    if (strcmp(line, COMMAND_TOKEN_ESTOP) == 0)
    {
        out_command->type = COMMAND_TYPE_ESTOP;
        return 1;
    }

    return 0;
}
