#include "stop_controller.h"
#include "motor.h"
#include "status_reporter.h"

/* ISR(B1 콜백 등)에서 설정될 수 있으므로 volatile로 선언 */
static volatile uint8_t operational_stop_requested  = 0;
static volatile uint8_t latched_safe_stop_requested  = 0;
static volatile uint8_t emergency_stop_requested     = 0;

/* Process()가 아닌 곳(main.c 등)에서 읽기만 하므로 volatile 불필요 */
static uint8_t operational_stopped = 0;
static uint8_t latched_stopped     = 0;
static uint8_t emergency_stopped   = 0;

/* Stall Fault. 다른 세 레벨과 달리 ISR/AppEventQueue로 "요청"되지 않고,
 * Motor가 이미 내부에서 확정한 상태를 StopController_Process()가 매 tick
 * 폴링해 반영한다(rising edge에서만 1로 래치). */
static uint8_t stall_stopped = 0;

void StopController_Init(void)
{
    operational_stop_requested = 0;
    latched_safe_stop_requested = 0;
    emergency_stop_requested = 0;

    operational_stopped = 0;
    latched_stopped = 0;
    emergency_stopped = 0;
    stall_stopped = 0;
}

void StopController_RequestOperationalStop(void)
{
    operational_stop_requested = 1;
}

void StopController_RequestLatchedSafeStop(void)
{
    latched_safe_stop_requested = 1;
}

void StopController_RequestEmergencyStop(void)
{
    emergency_stop_requested = 1;
}

void StopController_ClearOperationalStop(void)
{
    /* Latched Safe Stop과 Emergency Stop 상태에서는 해제되지 않는다 */
    if (!latched_stopped && !emergency_stopped)
    {
        operational_stop_requested = 0;
        operational_stopped = 0;
    }
}

void StopController_Process(void)
{
    /* Stall Fault 폴링: Motor가 이미 스스로 보호(PWM 0 + Integral Reset +
     * Speed Controller Disable)를 마친 상태를 여기서는 반영만 한다. rising
     * edge(!stall_stopped)에서만 진입하므로 FAULT Packet은 정확히 1회만
     * 나간다. Motor_NormalStop() 재호출은 Motor 자체 보호에 더해 "모든 정지
     * 트리거가 Motor_NormalStop/EmergencyStop으로 수렴한다"는 기존 불변식을
     * 유지하기 위한 멱등 재확인이다(부수효과 없음, 이미 0인 상태를 다시 0으로). */
    if (Motor_IsStalled() && !stall_stopped)
    {
        stall_stopped = 1;
        Motor_NormalStop();
        StatusReporter_SendStallFault(Motor_GetStallCause());
    }

    /* Emergency가 가장 우선이므로, 대기 중인 하위 레벨 요청은 폐기하고
     * Emergency만 수행한다. */
    if (emergency_stop_requested)
    {
        emergency_stop_requested = 0;
        latched_safe_stop_requested = 0;
        operational_stop_requested = 0;

        Motor_EmergencyStop();
        emergency_stopped = 1;
        return;
    }

    if (latched_safe_stop_requested)
    {
        latched_safe_stop_requested = 0;
        operational_stop_requested = 0;

        Motor_NormalStop();
        latched_stopped = 1;
        return;
    }

    if (operational_stop_requested)
    {
        operational_stop_requested = 0;

        Motor_NormalStop();
        operational_stopped = 1;
    }
}

uint8_t StopController_IsStopped(void)
{
    return (uint8_t)(operational_stopped || latched_stopped || emergency_stopped || stall_stopped);
}

uint8_t StopController_IsLatched(void)
{
    /* Stall Fault도 Latched Safe/Emergency와 마찬가지로 자동 해제되지 않는
     * 상태이므로 여기 포함한다 - AppTest_Process()의 자가진단 중단 조건 등
     * 기존에 IsLatched()를 참조하던 코드가 별도 수정 없이 Stall도 함께
     * 인식하게 된다. */
    return (uint8_t)(latched_stopped || emergency_stopped || stall_stopped);
}

uint8_t StopController_IsEmergency(void)
{
    return emergency_stopped;
}

StopControllerStallResetResult_t StopController_ClearStall(void)
{
    /* Emergency/Latched Safe Stop은 RESET_STALL로 절대 풀리지 않는다 -
     * StopController_ClearOperationalStop()의 기존 가드와 동일한 패턴.
     * 이 두 상태를 확인하는 동안에는 stall_stopped/Motor 쪽 상태를 전혀
     * 건드리지 않는다. */
    if (emergency_stopped)
    {
        return STOP_CONTROLLER_STALL_RESET_ESTOP_ACTIVE;
    }

    if (latched_stopped)
    {
        return STOP_CONTROLLER_STALL_RESET_LATCHED_SAFE_ACTIVE;
    }

    if (!stall_stopped)
    {
        return STOP_CONTROLLER_STALL_RESET_NO_STALL;
    }

    stall_stopped = 0;
    Motor_ClearStall();
    StatusReporter_SendStallCleared();

    return STOP_CONTROLLER_STALL_RESET_OK;
}
