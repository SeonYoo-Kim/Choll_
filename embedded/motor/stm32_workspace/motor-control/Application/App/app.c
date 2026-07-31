#include "app.h"
#include "app_event.h"
#include "motor.h"
#include "stop_controller.h"
#include "motion_controller.h"
#include "communication.h"

/* =========================================================
 * App Mode
 * - APP_MODE_REMOTE_CONTROL(기본값): USB 명령(SET_WHEEL_VEL/STOP/ESTOP)으로
 *   MotionController를 통해 원격 제어한다.
 * - APP_MODE_SELF_TEST: AppTest_Process()의 자동 Forward/Backward/Turn
 *   시퀀스로 구동한다. Remote Control 모드와 동시에 Motor를 제어하면
 *   MotionController의 명령을 덮어쓰므로 항상 둘 중 하나만 활성화된다.
 * - 빌드 옵션으로 재정의 가능: -DAPP_MODE_CURRENT=APP_MODE_SELF_TEST
 * ========================================================= */
typedef enum
{
    APP_MODE_REMOTE_CONTROL = 0,
    APP_MODE_SELF_TEST
} AppMode_t;

#ifndef APP_MODE_CURRENT
#define APP_MODE_CURRENT APP_MODE_REMOTE_CONTROL
#endif

/* =========================================================
 * AppTest: 모터 구동 테스트 시퀀스 (State Machine)
 * - Forward(10s) -> Stop(2s) -> Backward(10s) -> Stop(2s)
 *   -> TurnRight(10s) -> Stop(2s) -> TurnLeft(10s) -> Idle
 * - 각 State는 HAL_GetTick() 기준 경과 시간만 확인하고 즉시 return한다.
 * - APP_MODE_CURRENT가 APP_MODE_SELF_TEST일 때만 동작한다.
 * - Latched Safe Stop(B1) 또는 Emergency Stop(ESTOP)이 한 번이라도
 *   수행되면 즉시 Idle로 전환된다.
 * ========================================================= */

#define APP_TEST_PWM_PERCENT       40u
#define APP_TEST_MOVE_DURATION_MS  10000u
#define APP_TEST_STOP_DURATION_MS  2000u

typedef enum
{
    APP_TEST_STATE_FORWARD = 0,
    APP_TEST_STATE_STOP_AFTER_FORWARD,
    APP_TEST_STATE_BACKWARD,
    APP_TEST_STATE_STOP_AFTER_BACKWARD,
    APP_TEST_STATE_TURN_RIGHT,
    APP_TEST_STATE_STOP_AFTER_TURN_RIGHT,
    APP_TEST_STATE_TURN_LEFT,
    APP_TEST_STATE_IDLE
} AppTestState_t;

static AppTestState_t app_test_state       = APP_TEST_STATE_FORWARD;
static uint32_t       app_test_entry_tick  = 0;
static uint8_t        app_test_entered     = 0; /* 현재 State의 1회성 진입 동작 수행 여부 */

/* State 전환 + 진입 시각 기록. 진입 동작은 다음 AppTest_Process()에서 1회 수행된다. */
static void AppTest_EnterState(AppTestState_t next_state)
{
    app_test_state      = next_state;
    app_test_entry_tick = HAL_GetTick();
    app_test_entered     = 0;
}

static uint8_t AppTest_IsElapsed(uint32_t duration_ms)
{
    return ((HAL_GetTick() - app_test_entry_tick) >= duration_ms) ? 1u : 0u;
}

/**
 * @brief 모터 테스트 시퀀스 State Machine. Main Loop에서 매 tick 호출된다.
 *
 * 블로킹 없이 즉시 return하며, 각 State는 경과 시간만 확인한다.
 */
static void AppTest_Process(void)
{
    if (APP_MODE_CURRENT != APP_MODE_SELF_TEST)
    {
        return;
    }

    /* Latched Safe Stop/Emergency Stop이 한 번이라도 수행되면 테스트
     * 시퀀스를 즉시 종료하고 Idle 고정 */
    if (StopController_IsLatched() && (app_test_state != APP_TEST_STATE_IDLE))
    {
        AppTest_EnterState(APP_TEST_STATE_IDLE);
    }

    switch (app_test_state)
    {
    case APP_TEST_STATE_FORWARD:
        if (!app_test_entered)
        {
            Motor_Forward(APP_TEST_PWM_PERCENT);
            app_test_entered = 1;
        }
        if (AppTest_IsElapsed(APP_TEST_MOVE_DURATION_MS))
        {
            AppTest_EnterState(APP_TEST_STATE_STOP_AFTER_FORWARD);
        }
        break;

    case APP_TEST_STATE_STOP_AFTER_FORWARD:
        if (!app_test_entered)
        {
            Motor_Stop();
            app_test_entered = 1;
        }
        if (AppTest_IsElapsed(APP_TEST_STOP_DURATION_MS))
        {
            AppTest_EnterState(APP_TEST_STATE_BACKWARD);
        }
        break;

    case APP_TEST_STATE_BACKWARD:
        if (!app_test_entered)
        {
            Motor_Backward(APP_TEST_PWM_PERCENT);
            app_test_entered = 1;
        }
        if (AppTest_IsElapsed(APP_TEST_MOVE_DURATION_MS))
        {
            AppTest_EnterState(APP_TEST_STATE_STOP_AFTER_BACKWARD);
        }
        break;

    case APP_TEST_STATE_STOP_AFTER_BACKWARD:
        if (!app_test_entered)
        {
            Motor_Stop();
            app_test_entered = 1;
        }
        if (AppTest_IsElapsed(APP_TEST_STOP_DURATION_MS))
        {
            AppTest_EnterState(APP_TEST_STATE_TURN_RIGHT);
        }
        break;

    case APP_TEST_STATE_TURN_RIGHT:
        if (!app_test_entered)
        {
            Motor_TurnRight(APP_TEST_PWM_PERCENT);
            app_test_entered = 1;
        }
        if (AppTest_IsElapsed(APP_TEST_MOVE_DURATION_MS))
        {
            AppTest_EnterState(APP_TEST_STATE_STOP_AFTER_TURN_RIGHT);
        }
        break;

    case APP_TEST_STATE_STOP_AFTER_TURN_RIGHT:
        if (!app_test_entered)
        {
            Motor_Stop();
            app_test_entered = 1;
        }
        if (AppTest_IsElapsed(APP_TEST_STOP_DURATION_MS))
        {
            AppTest_EnterState(APP_TEST_STATE_TURN_LEFT);
        }
        break;

    case APP_TEST_STATE_TURN_LEFT:
        if (!app_test_entered)
        {
            Motor_TurnLeft(APP_TEST_PWM_PERCENT);
            app_test_entered = 1;
        }
        if (AppTest_IsElapsed(APP_TEST_MOVE_DURATION_MS))
        {
            AppTest_EnterState(APP_TEST_STATE_IDLE);
        }
        break;

    case APP_TEST_STATE_IDLE:
    default:
        if (!app_test_entered)
        {
            Motor_Stop();
            app_test_entered = 1;
        }
        break;
    }
}

/**
 * @brief AppEventQueue에 쌓인 이벤트를 모두 소비하여 Controller로 전달
 *
 * B1/USB Serial/ROS/RFID/Battery/Sensor/Timeout 등 모든 입력은 이 함수를
 * 통해서만 StopController/MotionController(또는 향후 추가될 다른
 * Controller)에 도달한다.
 * 큐 크기가 16으로 고정되어 있으므로 while 루프는 항상 유한 시간 안에 끝난다.
 */
static void App_ProcessEvents(void)
{
    AppEvent_t event;

    while (AppEventQueue_Pop(&event))
    {
        switch (event.type)
        {
        case APP_EVENT_LATCHED_SAFE_STOP:
            StopController_RequestLatchedSafeStop();
            break;

        case APP_EVENT_EMERGENCY_STOP:
            StopController_RequestEmergencyStop();
            break;

        case APP_EVENT_OPERATIONAL_STOP:
            StopController_RequestOperationalStop();
            break;

        case APP_EVENT_SET_WHEEL_VELOCITY:
            MotionController_RequestWheelVelocity(event.data.wheel_velocity.left_rad_s,
                                                    event.data.wheel_velocity.right_rad_s);
            break;

        case APP_EVENT_COMMUNICATION_TIMEOUT:
            StopController_RequestOperationalStop();
            break;

        default:
            break;
        }
    }
}

void App_Init(void)
{
    AppEventQueue_Init();
    Motor_Init();
    StopController_Init();
    MotionController_Init();
    Communication_Init();
}

void App_Run(void)
{
    Communication_Process();
    App_ProcessEvents();

    StopController_Process();
    MotionController_Process();
    Motor_Process();

    AppTest_Process();
}
