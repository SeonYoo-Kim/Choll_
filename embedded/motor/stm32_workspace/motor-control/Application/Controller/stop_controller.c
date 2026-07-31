#include "stop_controller.h"
#include "motor.h"

/* ISR(B1 콜백 등)에서 설정될 수 있으므로 volatile로 선언 */
static volatile uint8_t operational_stop_requested  = 0;
static volatile uint8_t latched_safe_stop_requested  = 0;
static volatile uint8_t emergency_stop_requested     = 0;

/* Process()가 아닌 곳(main.c 등)에서 읽기만 하므로 volatile 불필요 */
static uint8_t operational_stopped = 0;
static uint8_t latched_stopped     = 0;
static uint8_t emergency_stopped   = 0;

void StopController_Init(void)
{
    operational_stop_requested = 0;
    latched_safe_stop_requested = 0;
    emergency_stop_requested = 0;

    operational_stopped = 0;
    latched_stopped = 0;
    emergency_stopped = 0;
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
    return (uint8_t)(operational_stopped || latched_stopped || emergency_stopped);
}

uint8_t StopController_IsLatched(void)
{
    return (uint8_t)(latched_stopped || emergency_stopped);
}

uint8_t StopController_IsEmergency(void)
{
    return emergency_stopped;
}
