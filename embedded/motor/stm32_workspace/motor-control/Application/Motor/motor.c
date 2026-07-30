#include "motor.h"

/* CubeMX가 main.c에 생성한 타이머 핸들 (Motor_Init 순서 그대로 사용) */
extern TIM_HandleTypeDef htim2;
extern TIM_HandleTypeDef htim3;
extern TIM_HandleTypeDef htim4;
extern TIM_HandleTypeDef htim8;

/* =========================================================
 * Motor1 Encoder Variables
 * - TIM2 엔코더의 현재값, 변화량, 누적값을 저장
 * ========================================================= */
volatile uint16_t motor1_encoder_raw = 0;
volatile uint16_t motor1_previous_count = 0;
volatile int16_t  motor1_encoder_delta = 0;
volatile int32_t  motor1_encoder_total = 0;


/* =========================================================
 * Motor2 Encoder Variables
 * - TIM8 엔코더의 현재값, 변화량, 누적값을 저장
 * ========================================================= */
volatile uint16_t motor2_encoder_raw = 0;
volatile uint16_t motor2_previous_count = 0;
volatile int16_t  motor2_encoder_delta = 0;
volatile int32_t  motor2_encoder_total = 0;


/* =========================================================
 * Wheel Velocity Target (rad/s)
 * - MotionController가 저장한 목표값. 아직 Wheel Velocity PID가 없으므로
 *   Motor_Process()는 이 값을 참조하지 않는다. 향후 PID 구현 시 이
 *   값과 엔코더 값을 사용해 폐루프 제어를 수행할 위치이다.
 * ========================================================= */
static volatile float motor_target_left_rad_s  = 0.0f;
static volatile float motor_target_right_rad_s = 0.0f;


/**
 * @brief PWM 값을 TIM3/TIM4의 범위인 0~99로 제한
 */
static uint16_t Motor_LimitPwm(uint16_t pwm)
{
    if (pwm > 99)
    {
        pwm = 99;
    }

    return pwm;
}


/**
 * @brief 로봇 전진
 *
 * 왼쪽 모터:
 * - TIM3 CH2를 사용해야 차체 기준 전진
 *
 * 오른쪽 모터:
 * - TIM4 CH1을 사용해야 차체 기준 전진
 */
void Motor_Forward(uint16_t pwm)
{
    pwm = Motor_LimitPwm(pwm);

    /* Motor1: 왼쪽 모터 전진 */
    __HAL_TIM_SET_COMPARE(&htim3, TIM_CHANNEL_1, 0);
    __HAL_TIM_SET_COMPARE(&htim3, TIM_CHANNEL_2, pwm);

    /* Motor2: 오른쪽 모터 전진 */
    __HAL_TIM_SET_COMPARE(&htim4, TIM_CHANNEL_1, pwm);
    __HAL_TIM_SET_COMPARE(&htim4, TIM_CHANNEL_2, 0);
}


/**
 * @brief 로봇 후진
 *
 * 왼쪽과 오른쪽 모터를 전진의 반대 방향으로 회전
 */
void Motor_Backward(uint16_t pwm)
{
    pwm = Motor_LimitPwm(pwm);

    /* Motor1: 왼쪽 모터 후진 */
    __HAL_TIM_SET_COMPARE(&htim3, TIM_CHANNEL_1, pwm);
    __HAL_TIM_SET_COMPARE(&htim3, TIM_CHANNEL_2, 0);

    /* Motor2: 오른쪽 모터 후진 */
    __HAL_TIM_SET_COMPARE(&htim4, TIM_CHANNEL_1, 0);
    __HAL_TIM_SET_COMPARE(&htim4, TIM_CHANNEL_2, pwm);
}


/**
 * @brief 제자리 우회전
 *
 * 왼쪽 바퀴는 전진하고 오른쪽 바퀴는 후진
 */
void Motor_TurnRight(uint16_t pwm)
{
    pwm = Motor_LimitPwm(pwm);

    /* Motor1: 왼쪽 모터 전진 */
    __HAL_TIM_SET_COMPARE(&htim3, TIM_CHANNEL_1, 0);
    __HAL_TIM_SET_COMPARE(&htim3, TIM_CHANNEL_2, pwm);

    /* Motor2: 오른쪽 모터 후진 */
    __HAL_TIM_SET_COMPARE(&htim4, TIM_CHANNEL_1, 0);
    __HAL_TIM_SET_COMPARE(&htim4, TIM_CHANNEL_2, pwm);
}


/**
 * @brief 제자리 좌회전
 *
 * 왼쪽 바퀴는 후진하고 오른쪽 바퀴는 전진
 */
void Motor_TurnLeft(uint16_t pwm)
{
    pwm = Motor_LimitPwm(pwm);

    /* Motor1: 왼쪽 모터 후진 */
    __HAL_TIM_SET_COMPARE(&htim3, TIM_CHANNEL_1, pwm);
    __HAL_TIM_SET_COMPARE(&htim3, TIM_CHANNEL_2, 0);

    /* Motor2: 오른쪽 모터 전진 */
    __HAL_TIM_SET_COMPARE(&htim4, TIM_CHANNEL_1, pwm);
    __HAL_TIM_SET_COMPARE(&htim4, TIM_CHANNEL_2, 0);
}


/**
 * @brief 좌우 모터 즉시 정지
 */
void Motor_Stop(void)
{
    /* Motor1: 왼쪽 모터 정지 */
    __HAL_TIM_SET_COMPARE(&htim3, TIM_CHANNEL_1, 0);
    __HAL_TIM_SET_COMPARE(&htim3, TIM_CHANNEL_2, 0);

    /* Motor2: 오른쪽 모터 정지 */
    __HAL_TIM_SET_COMPARE(&htim4, TIM_CHANNEL_1, 0);
    __HAL_TIM_SET_COMPARE(&htim4, TIM_CHANNEL_2, 0);
}


/**
 * @brief StopController 전용 일반 정지
 *
 * PWM duty만 0으로 만들고 BTS7960 Enable은 유지한다.
 * Motor_EmergencyStop()과는 서로 독립적이며 호출하지 않는다.
 */
void Motor_NormalStop(void)
{
    /* Motor1: 왼쪽 모터 정지 */
    __HAL_TIM_SET_COMPARE(&htim3, TIM_CHANNEL_1, 0);
    __HAL_TIM_SET_COMPARE(&htim3, TIM_CHANNEL_2, 0);

    /* Motor2: 오른쪽 모터 정지 */
    __HAL_TIM_SET_COMPARE(&htim4, TIM_CHANNEL_1, 0);
    __HAL_TIM_SET_COMPARE(&htim4, TIM_CHANNEL_2, 0);
}


/**
 * @brief StopController 전용 비상 정지
 *
 * PWM duty를 0으로 만드는 것에 더해 BTS7960 Enable 핀까지 즉시
 * Low로 내려 모터 구동 전류 자체를 차단한다.
 * Motor_NormalStop()과는 서로 독립적이며 호출하지 않는다.
 */
void Motor_EmergencyStop(void)
{
    /* Motor1: 왼쪽 모터 정지 */
    __HAL_TIM_SET_COMPARE(&htim3, TIM_CHANNEL_1, 0);
    __HAL_TIM_SET_COMPARE(&htim3, TIM_CHANNEL_2, 0);

    /* Motor2: 오른쪽 모터 정지 */
    __HAL_TIM_SET_COMPARE(&htim4, TIM_CHANNEL_1, 0);
    __HAL_TIM_SET_COMPARE(&htim4, TIM_CHANNEL_2, 0);

    /* Motor1 BTS7960 Disable: PB8/PB9 */
    HAL_GPIO_WritePin(GPIOB, GPIO_PIN_8, GPIO_PIN_RESET);
    HAL_GPIO_WritePin(GPIOB, GPIO_PIN_9, GPIO_PIN_RESET);

    /* Motor2 BTS7960 Disable: PA9/PA8 */
    HAL_GPIO_WritePin(GPIOA, GPIO_PIN_9, GPIO_PIN_RESET);
    HAL_GPIO_WritePin(GPIOA, GPIO_PIN_8, GPIO_PIN_RESET);
}


/**
 * @brief 좌우 목표 바퀴 각속도(rad/s) 저장
 *
 * 아직 Wheel Velocity PID가 구현되지 않았으므로 목표값을 저장만 하고
 * PWM에는 반영하지 않는다. 실제 폐루프 제어는 이 값과 엔코더 값을
 * 사용하는 PID 루프가 추가된 뒤 Motor_Process()에 연결한다.
 */
void Motor_SetTargetWheelVelocity(float left_rad_s, float right_rad_s)
{
    motor_target_left_rad_s  = left_rad_s;
    motor_target_right_rad_s = right_rad_s;
}


/**
 * @brief 엔코더 값 갱신 (Main Loop에서 매 tick 호출)
 *
 * 이전에는 Motor_WaitAndUpdateEncoder()가 지정된 시간만큼 블로킹하며
 * 10ms마다 이 갱신을 수행했으나, Main Loop가 논블로킹 구조로 바뀌면서
 * 매 tick 한 번씩 호출되는 것으로 대체되었다.
 */
void Motor_Process(void)
{
    /* ================================================
     * Motor1: 왼쪽 모터 엔코더 갱신
     * - TIM2 사용
     * ================================================ */
    motor1_encoder_raw =
        (uint16_t)__HAL_TIM_GET_COUNTER(&htim2);

    motor1_encoder_delta =
        (int16_t)(motor1_encoder_raw -
                  motor1_previous_count);

    motor1_previous_count =
        motor1_encoder_raw;

    motor1_encoder_total +=
        motor1_encoder_delta;


    /* ================================================
     * Motor2: 오른쪽 모터 엔코더 갱신
     * - TIM8 사용
     * ================================================ */
    motor2_encoder_raw =
        (uint16_t)__HAL_TIM_GET_COUNTER(&htim8);

    motor2_encoder_delta =
        (int16_t)(motor2_encoder_raw -
                  motor2_previous_count);

    motor2_previous_count =
        motor2_encoder_raw;

    motor2_encoder_total +=
        motor2_encoder_delta;
}


/**
 * @brief 모터 PWM/엔코더 시작, BTS7960 Enable, 초기 정지
 *
 * main()의 USER CODE BEGIN 2에서 수행하던 초기화 시퀀스를
 * 순서 변경 없이 그대로 옮긴 것.
 */
void Motor_Init(void)
{
    /* =========================================================
     * Motor1 PWM Start
     * - TIM3 CH1: Motor1 RPWM
     * - TIM3 CH2: Motor1 LPWM
     * ========================================================= */
    HAL_TIM_PWM_Start(&htim3, TIM_CHANNEL_1);
    HAL_TIM_PWM_Start(&htim3, TIM_CHANNEL_2);


    /* =========================================================
     * Motor2 PWM Start
     * - TIM4 CH1: Motor2 RPWM
     * - TIM4 CH2: Motor2 LPWM
     * ========================================================= */
    HAL_TIM_PWM_Start(&htim4, TIM_CHANNEL_1);
    HAL_TIM_PWM_Start(&htim4, TIM_CHANNEL_2);


    /* =========================================================
     * Motor1 Encoder Start
     * - TIM2 CH1/CH2를 Encoder Mode로 시작
     * ========================================================= */
    HAL_TIM_Encoder_Start(&htim2, TIM_CHANNEL_ALL);


    /* =========================================================
     * Motor2 Encoder Start
     * - TIM8 CH1/CH2를 Encoder Mode로 시작
     * ========================================================= */
    HAL_TIM_Encoder_Start(&htim8, TIM_CHANNEL_ALL);


    /* =========================================================
     * Motor1 Encoder Initialization
     * - TIM2 카운터 및 소프트웨어 누적 변수를 0으로 초기화
     * ========================================================= */
    __HAL_TIM_SET_COUNTER(&htim2, 0);

    motor1_encoder_raw = 0;
    motor1_previous_count = 0;
    motor1_encoder_delta = 0;
    motor1_encoder_total = 0;


    /* =========================================================
     * Motor2 Encoder Initialization
     * - TIM8 카운터 및 소프트웨어 누적 변수를 0으로 초기화
     * ========================================================= */
    __HAL_TIM_SET_COUNTER(&htim8, 0);

    motor2_encoder_raw = 0;
    motor2_previous_count = 0;
    motor2_encoder_delta = 0;
    motor2_encoder_total = 0;


    /* =========================================================
     * Motor1 BTS7960 Enable
     * - PB8: R_EN
     * - PB9: L_EN
     * ========================================================= */
    HAL_GPIO_WritePin(GPIOB, GPIO_PIN_8, GPIO_PIN_SET);
    HAL_GPIO_WritePin(GPIOB, GPIO_PIN_9, GPIO_PIN_SET);


    /* =========================================================
     * Motor2 BTS7960 Enable
     * - PA9: R_EN
     * - PA8: L_EN
     * ========================================================= */
    HAL_GPIO_WritePin(GPIOA, GPIO_PIN_9, GPIO_PIN_SET);
    HAL_GPIO_WritePin(GPIOA, GPIO_PIN_8, GPIO_PIN_SET);


    /* =========================================================
     * Motor1 Initial Stop
     * - RPWM과 LPWM을 모두 0으로 설정
     * ========================================================= */
    __HAL_TIM_SET_COMPARE(&htim3, TIM_CHANNEL_1, 0);
    __HAL_TIM_SET_COMPARE(&htim3, TIM_CHANNEL_2, 0);


    /* =========================================================
     * Motor2 Initial Stop
     * - RPWM과 LPWM을 모두 0으로 설정
     * ========================================================= */
    __HAL_TIM_SET_COMPARE(&htim4, TIM_CHANNEL_1, 0);
    __HAL_TIM_SET_COMPARE(&htim4, TIM_CHANNEL_2, 0);
}
