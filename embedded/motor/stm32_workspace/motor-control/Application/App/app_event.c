#include "app_event.h"
#include "main.h"

#define APP_EVENT_QUEUE_SIZE 16u

static AppEvent_t       queue_buffer[APP_EVENT_QUEUE_SIZE];
static volatile uint8_t queue_head  = 0; /* 다음 Pop 위치 */
static volatile uint8_t queue_tail  = 0; /* 다음 Push 위치 */
static volatile uint8_t queue_count = 0; /* 현재 저장된 이벤트 수 */

/* Push/Pop이 서로 다른 컨텍스트(ISR/main loop)에서 동시에 호출되어도
 * head/tail/count가 일관되게 유지되도록 짧게 인터럽트를 막는다.
 * PRIMASK를 저장/복원하므로 이미 인터럽트가 막혀있는 중첩 호출에도 안전하다. */
static uint32_t AppEventQueue_EnterCritical(void)
{
    uint32_t primask = __get_PRIMASK();
    __disable_irq();
    return primask;
}

static void AppEventQueue_ExitCritical(uint32_t primask)
{
    if (!primask)
    {
        __enable_irq();
    }
}

/* 큐에 대기 중인 동일 타입 이벤트의 인덱스를 찾는다. 없으면 APP_EVENT_QUEUE_SIZE를
 * 반환한다. 반드시 Critical Section 안에서 호출해야 한다. */
static uint8_t AppEventQueue_FindPendingIndex(AppEventType_t type)
{
    for (uint8_t i = 0; i < queue_count; i++)
    {
        uint8_t idx = (uint8_t)((queue_head + i) % APP_EVENT_QUEUE_SIZE);

        if (queue_buffer[idx].type == type)
        {
            return idx;
        }
    }

    return APP_EVENT_QUEUE_SIZE;
}

static uint8_t AppEventQueue_PushInternal(const AppEvent_t *event)
{
    uint8_t result = 0;
    uint32_t primask = AppEventQueue_EnterCritical();

    /* SET_WHEEL_VELOCITY는 대기 중인 이전 값을 최신 값으로 덮어쓴다(coalescing) */
    if (event->type == APP_EVENT_SET_WHEEL_VELOCITY)
    {
        uint8_t pending_idx = AppEventQueue_FindPendingIndex(APP_EVENT_SET_WHEEL_VELOCITY);

        if (pending_idx < APP_EVENT_QUEUE_SIZE)
        {
            queue_buffer[pending_idx] = *event;
            AppEventQueue_ExitCritical(primask);
            return 1;
        }
    }

    if (queue_count < APP_EVENT_QUEUE_SIZE)
    {
        queue_buffer[queue_tail] = *event;
        queue_tail = (uint8_t)((queue_tail + 1u) % APP_EVENT_QUEUE_SIZE);
        queue_count++;
        result = 1;
    }

    AppEventQueue_ExitCritical(primask);

    return result;
}

void AppEventQueue_Init(void)
{
    queue_head  = 0;
    queue_tail  = 0;
    queue_count = 0;
}

uint8_t AppEventQueue_Push(const AppEvent_t *event)
{
    return AppEventQueue_PushInternal(event);
}

uint8_t AppEventQueue_PushFromISR(const AppEvent_t *event)
{
    return AppEventQueue_PushInternal(event);
}

uint8_t AppEventQueue_Pop(AppEvent_t *out_event)
{
    uint8_t result = 0;
    uint32_t primask = AppEventQueue_EnterCritical();

    if (queue_count > 0u)
    {
        *out_event = queue_buffer[queue_head];
        queue_head = (uint8_t)((queue_head + 1u) % APP_EVENT_QUEUE_SIZE);
        queue_count--;
        result = 1;
    }

    AppEventQueue_ExitCritical(primask);

    return result;
}
