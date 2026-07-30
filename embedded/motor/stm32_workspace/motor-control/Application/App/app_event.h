#ifndef APP_EVENT_H
#define APP_EVENT_H

#include <stdint.h>

/* =========================================================
 * AppEvent
 * - 모든 입력(B1, USB Serial, ROS, RFID, Battery, Sensor, Timeout,
 *   Watchdog 등)이 Controller로 전달하는 공통 이벤트 형식.
 * - 입력은 이 이벤트를 Push/PushFromISR로 큐에 넣기만 하고,
 *   실제 Controller 호출은 App_ProcessEvents()에서만 수행한다.
 * - 새 입력이 추가될 때는 이 enum에 항목만 추가하면 된다.
 * ========================================================= */
typedef enum
{
    APP_EVENT_NONE = 0,

    APP_EVENT_LATCHED_SAFE_STOP,     /* B1: 재부팅 전까지 유지되는 안전 정지 */
    APP_EVENT_EMERGENCY_STOP,        /* USB ESTOP: 즉시 정지 + 재부팅 전까지 래치 */
    APP_EVENT_OPERATIONAL_STOP,      /* USB STOP: 재이동 가능한 일반 정지 */
    APP_EVENT_SET_WHEEL_VELOCITY,    /* USB SET_WHEEL_VEL: 목표 좌우 바퀴 각속도(rad/s) */
    APP_EVENT_COMMUNICATION_TIMEOUT, /* 내부 안전: 300ms 이상 유효 SET_WHEEL_VEL 미수신 */

    APP_EVENT_TYPE_COUNT
} AppEventType_t;

/* SET_WHEEL_VELOCITY 이벤트 payload */
typedef struct
{
    float left_rad_s;
    float right_rad_s;
} AppWheelVelocity_t;

typedef struct
{
    AppEventType_t type;

    /* type == APP_EVENT_SET_WHEEL_VELOCITY 일 때만 유효 */
    union
    {
        AppWheelVelocity_t wheel_velocity;
    } data;
} AppEvent_t;

/* =========================================================
 * AppEventQueue
 * - 크기 16의 Ring Buffer. 여러 입력(Push/PushFromISR)이 동시에
 *   써도 안전하며, Pop은 App_ProcessEvents() 한 곳에서만 호출된다.
 * - APP_EVENT_SET_WHEEL_VELOCITY는 큐에 이미 대기 중인 동일 타입
 *   이벤트가 있으면 새 슬롯을 늘리지 않고 그 값을 최신 값으로
 *   덮어쓴다(coalescing). 20~30Hz로 반복 수신되는 이 이벤트가
 *   STOP/ESTOP 등 다른 이벤트의 큐 슬롯을 잠식하지 않도록 하기
 *   위함이며, 그 외 이벤트 타입은 일반 Ring Buffer 정책(가득 차면
 *   실패)을 따른다.
 * ========================================================= */

void AppEventQueue_Init(void);

/* 일반 컨텍스트(main loop 등)에서 호출. 큐가 가득 차면 0(실패) 반환 */
uint8_t AppEventQueue_Push(const AppEvent_t *event);

/* ISR 컨텍스트 전용 호출부. 매우 짧게 끝나며 큐가 가득 차면 0(실패) 반환 */
uint8_t AppEventQueue_PushFromISR(const AppEvent_t *event);

/* 큐에서 이벤트 하나를 꺼낸다. 성공 시 1과 함께 out_event에 기록, 비어있으면 0 */
uint8_t AppEventQueue_Pop(AppEvent_t *out_event);

#endif /* APP_EVENT_H */
