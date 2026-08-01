#include "motion_controller.h"
#include "stop_controller.h"
#include "motor.h"
#include "app_event.h"
#include "main.h"

/* TODO(motion_controller): 실제 Wheel PID 및 하드웨어(기어비/바퀴 반지름/최대 RPM)가
 * 확정되면 이 값을 실측 최대 rad/s로 채우고, MotionController_RequestWheelVelocity()에서
 * left_rad_s/right_rad_s를 [-MOTION_CONTROLLER_MAX_WHEEL_RAD_S, +MOTION_CONTROLLER_MAX_WHEEL_RAD_S]
 * 범위로 clamp한다. 현재는 정의만 해두고 적용하지 않는다. */
#define MOTION_CONTROLLER_MAX_WHEEL_RAD_S 0.0f

/* Orin은 20~30Hz로 SET_WHEEL_VEL을 전송할 예정이므로 300ms면 충분히 여유 있는 기준이다 */
#define MOTION_CONTROLLER_COMM_TIMEOUT_MS 5000u

static float target_left_rad_s  = 0.0f;
static float target_right_rad_s = 0.0f;

static uint32_t last_command_tick          = 0;
static uint8_t  has_received_first_command = 0; /* 부팅 직후(첫 명령 수신 전) Timeout 검사 제외용 */
static uint8_t  timeout_latched            = 0; /* Timeout 이벤트 1회 발행 후 재발행 방지 */

void MotionController_Init(void)
{
    target_left_rad_s  = 0.0f;
    target_right_rad_s = 0.0f;

    last_command_tick = 0;
    has_received_first_command = 0;
    timeout_latched = 0;
}

void MotionController_RequestWheelVelocity(float left_rad_s, float right_rad_s)
{
    /* Emergency Stop 상태에서는 이동 명령을 완전히 무시한다(래치 유지) */
    if (StopController_IsEmergency())
    {
        return;
    }

    /* TODO(motion_controller): MOTION_CONTROLLER_MAX_WHEEL_RAD_S 확정 후 clamp 적용 */
    target_left_rad_s  = left_rad_s;
    target_right_rad_s = right_rad_s;

    last_command_tick = HAL_GetTick();
    has_received_first_command = 1;
    timeout_latched = 0; /* 새 유효 명령 수신: Timeout 래치 해제 */

    /* 새로운 유효 이동 명령이므로 Operational Stop(USB STOP/Timeout)을 해제한다.
     * Latched Safe Stop/Emergency Stop에는 영향을 주지 않는다. */
    StopController_ClearOperationalStop();
}

/**
 * @brief 300ms 이상 유효 SET_WHEEL_VEL 미수신 시 1회만 Timeout 이벤트 발행
 *
 * HAL_GetTick() 오버플로우에도 안전하도록 부호 없는 뺄셈만 사용한다.
 * 부팅 직후(첫 명령 수신 전)에는 검사하지 않는다.
 */
static void MotionController_CheckCommunicationTimeout(void)
{
    uint32_t elapsed_ms;
    AppEvent_t event;

    if (!has_received_first_command || timeout_latched)
    {
        return;
    }

    elapsed_ms = HAL_GetTick() - last_command_tick;

    if (elapsed_ms >= MOTION_CONTROLLER_COMM_TIMEOUT_MS)
    {
        timeout_latched = 1;

        event.type = APP_EVENT_COMMUNICATION_TIMEOUT;
        (void)AppEventQueue_Push(&event);
    }
}

void MotionController_ResetTarget(void)
{
    target_left_rad_s  = 0.0f;
    target_right_rad_s = 0.0f;
}

void MotionController_Process(void)
{
    MotionController_CheckCommunicationTimeout();

    if (StopController_IsStopped())
    {
        Motor_SetTargetWheelVelocity(0.0f, 0.0f);
        return;
    }

    /* PI Speed Controller 활성화. 세 정지 레벨(Operational/Latched/Emergency)이
     * 모두 해제된 경우에만 도달하는 지점이므로, 여기서 활성화하는 것이 안전하다
     * (MotionController_RequestWheelVelocity()는 Latched Safe Stop 중에도 호출될
     * 수 있어 그곳에서는 활성화하지 않는다). 매 tick 호출되지만 멱등하다. */
    Motor_EnableSpeedControl();

    Motor_SetTargetWheelVelocity(target_left_rad_s, target_right_rad_s);
}
