#include "motor.h"
/* motor_config.h는 Application/Config에 있으며, 다른 Application 하위 모듈
 * 헤더(motor.h, communication.h 등)와 동일하게 CubeIDE Include Path(-I)에
 * 등록된 폴더의 파일명만으로 include한다. */
#include "motor_config.h"
#include <math.h>

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
 * Wheel Velocity Requested / Limited (rad/s)
 * - requested: MotionController가 Motor_SetTargetWheelVelocity()로 저장한,
 *   가공되지 않은 요청값. Speed Profile 입력.
 * - limited: Motor_AdvanceSpeedProfile()이 requested를 가속/감속 제한 +
 *   방향 전환 보호를 거쳐 천천히 따라가게 만든 값. Feedforward/PI는 이제
 *   requested가 아니라 이 limited를 목표로 삼는다.
 * ========================================================= */
static volatile float motor_requested_left_rad_s  = 0.0f;
static volatile float motor_requested_right_rad_s = 0.0f;

static volatile float motor_limited_left_rad_s  = 0.0f;
static volatile float motor_limited_right_rad_s = 0.0f;

/* Speed Profile 방향 전환 보호 상태 머신 (좌/우 독립).
 * NORMAL         : 일반 가속/감속 리미터로 limited를 requested 쪽으로 이동.
 * ZEROING        : requested가 limited와 반대 부호로 바뀐 것을 감지, requested를
 *                  무시하고 MOTOR_DIRECTION_CHANGE_DECEL_RAD_S2로 limited를
 *                  0으로 감속하는 중(아직 limited != 0).
 * ZEROED_WAITING : limited가 0에 도달했지만 Actual이 아직
 *                  MOTOR_DIRECTION_ZERO_THRESHOLD_RAD_S 밖이라 대기 중.
 * HOLDING        : limited==0 + Actual도 0 근접 확인 후, MOTOR_DIRECTION_CHANGE_HOLD_MS
 *                  동안 0에 고정. 이후 NORMAL로 돌아가 그 시점의 requested를
 *                  다시 따라간다.
 * 한 번 시작된 ZEROING/ZEROED_WAITING/HOLDING 시퀀스는 중간에 requested가
 * 바뀌어도 끝까지 진행한다(중간 취소는 또 다른 급반전 경로가 될 수 있어 배제).
 *
 * ZEROED_WAITING/HOLDING 상태에서는 Motor_Process()가 Feedforward/PI 계산
 * 결과와 무관하게 좌/우 PWM을 강제로 0으로 만들고(아래 참고), 같은 두
 * 상태에서는 Motor_UpdateActualVelocity()도 PI Integral 누적을 멈춘다.
 * limited==0이라 Feedforward는 이미 0이지만, PI(Kp*error 또는 이전에 쌓인
 * Integral)는 Actual이 아직 0이 아닌 동안 0이 아닌 값을 낼 수 있어서 —
 * Actual과 반대 방향(제동 방향) PWM이 Hold가 끝나기 전에 새어나가는 것을
 * 막기 위한 명시적 안전장치다. */
typedef enum
{
    MOTOR_DIR_STATE_NORMAL = 0,
    MOTOR_DIR_STATE_ZEROING,
    MOTOR_DIR_STATE_ZEROED_WAITING,
    MOTOR_DIR_STATE_HOLDING
} MotorDirectionChangeState_t;

static MotorDirectionChangeState_t motor_dir_state_left  = MOTOR_DIR_STATE_NORMAL;
static MotorDirectionChangeState_t motor_dir_state_right = MOTOR_DIR_STATE_NORMAL;

/* HOLDING 진입 시각(HAL_GetTick()). motor_velocity_last_sample_tick과 같은
 * 이유로 ISR에서 접근하지 않아 volatile 불필요. */
static uint32_t motor_dir_hold_start_tick_left  = 0;
static uint32_t motor_dir_hold_start_tick_right = 0;

/* Motor_Process()가 마지막으로 출력한 PWM. StatusReporter가 텔레메트리로
 * 읽어가는 용도로만 사용하며, 제어 로직에는 관여하지 않는다. */
static volatile int16_t motor_last_left_pwm  = 0;
static volatile int16_t motor_last_right_pwm = 0;

/* Actual Wheel Velocity(rad/s). Motor_UpdateActualVelocity()가
 * MOTOR_SAMPLE_PERIOD_MS(motor_config.h)마다 엔코더 델타로부터 갱신한다.
 * StopController/목표값과 무관하게 오직 엔코더 실측값만 반영하므로, 정지
 * 명령 중에도 바퀴를 손으로 돌리면 이 값이 변한다. */
static volatile float motor_actual_left_rad_s  = 0.0f;
static volatile float motor_actual_right_rad_s = 0.0f;

/* Motor_UpdateActualVelocity()가 직전 샘플 시점의 tick과 누적 Encoder Count를
 * 저장해두는 상태. ΔEncoder Count = 현재 total - 이 값. */
static uint32_t motor_velocity_last_sample_tick  = 0;
static int32_t  motor_velocity_last_left_total   = 0;
static int32_t  motor_velocity_last_right_total  = 0;

/* PI Speed Controller 활성화 상태.
 * - Motor_NormalStop()/Motor_EmergencyStop() 내부에서 0으로 설정된다(모든
 *   정지 경로가 이 두 함수로 수렴하므로 여기 한 곳만 손보면 충분하다).
 * - Motor_EnableSpeedControl()로만 1로 설정되며, 이 함수는 MotionController가
 *   StopController_IsStopped() == false일 때만 호출한다. Motor는 StopController를
 *   직접 참조하지 않는다(Controller -> Motor 단방향 의존성 유지).
 * - 0이면 Motor_Process()가 Feedforward/PI 계산을 모두 건너뛰고 PWM을 0으로
 *   유지한다. 엔코더 갱신과 Actual Wheel Velocity 계산은 이 값과 무관하게
 *   항상 수행된다. */
static volatile uint8_t motor_speed_control_enabled = 0;

/* PI Integral. Ki가 이미 곱해진 PWM 단위로 누적/저장한다(그래서 clamp 한계값을
 * MOTOR_PWM_MAX와 같은 단위로 직접 비교/튜닝할 수 있다). Motor_NormalStop()/
 * Motor_EmergencyStop()에서 0으로 리셋되고, Motor_UpdateActualVelocity()가
 * MOTOR_SAMPLE_PERIOD_MS 주기로(그리고 speed_control_enabled일 때만) 누적한다. */
static volatile float motor_pi_integral_left_pwm  = 0.0f;
static volatile float motor_pi_integral_right_pwm = 0.0f;

/* Stall Detection 상태 (motor_config.h MOTOR_STALL_* 참고).
 * - timing_left/right: 1이면 좌/우 각각 "조건 3개(PWM/Target/Actual)를 계속
 *   만족 중"이라 디바운스 타이머가 진행 중이라는 뜻. 조건이 한 번이라도
 *   깨지면 0으로 리셋되고 start_tick도 다음 재시작 때 새로 기록된다(누적이
 *   아니라 연속 유지 조건 - 요구사항: 일시적 부하로 오검출 금지).
 * - cause: 확정된 Stall의 원인(좌/우/양쪽). NONE이 아니면 Motor_ClearStall()
 *   호출 전까지 다시 판정하지 않는다(최초 원인 보존). StopController가
 *   Motor_IsStalled()/Motor_GetStallCause()로 폴링한다. */
static uint8_t  motor_stall_timing_left   = 0;
static uint8_t  motor_stall_timing_right  = 0;
static uint32_t motor_stall_start_tick_left  = 0;
static uint32_t motor_stall_start_tick_right = 0;
static MotorStallCause_t motor_stall_cause = MOTOR_STALL_NONE;


/* MOTOR_OPEN_LOOP_PWM_PER_RAD_S / MOTOR_TARGET_DEADBAND_RAD_S / 좌우 PWM·엔코더
 * 방향 보정 매크로는 motor_config.h로 이동했다(값 변경 없음, 위치만 이동). */

/* RPM -> rad/s 변환에 사용하는 1회전당 라디안. libm의 M_PI 매크로는 이식성이
 * 보장되지 않아(POSIX 확장) 직접 상수로 둔다. */
#define MOTOR_RADIANS_PER_REV (2.0f * 3.14159265358979323846f)

/* Stall Detection(Motor_UpdateActualVelocity() 내부)이 확정 즉시 PWM을 0으로
 * 만들고 나머지 상태를 리셋하기 위해, 파일 뒤쪽에 정의된 함수를 앞당겨
 * 선언한다(다른 함수는 재배치하지 않는다 - 최소 변경). */
static void Motor_SetLeftPwm(int16_t pwm);
static void Motor_SetRightPwm(int16_t pwm);
static void Motor_ResetSpeedController(void);


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
 * @brief 목표 각속도(rad/s)를 Open-loop PWM으로 임시 변환
 *
 * Wheel Velocity PID가 구현되기 전까지 사용하는 단순 비례 변환이다.
 * deadband 이내의 목표값은 0으로 처리하고, 변환된 값은 MOTOR_PWM_MAX
 * 범위로 saturation한다. 추후 PID로 교체될 때 이 함수만 대체하면 된다.
 */
static int16_t Motor_TargetVelocityToPwm(float target_rad_s)
{
    float pwm_f;

    if (fabsf(target_rad_s) < MOTOR_TARGET_DEADBAND_RAD_S)
    {
        return 0;
    }

    pwm_f = target_rad_s * MOTOR_OPEN_LOOP_PWM_PER_RAD_S;

    if (pwm_f > (float)MOTOR_PWM_MAX)
    {
        pwm_f = (float)MOTOR_PWM_MAX;
    }
    else if (pwm_f < -(float)MOTOR_PWM_MAX)
    {
        pwm_f = -(float)MOTOR_PWM_MAX;
    }

    return (int16_t)pwm_f;
}


/**
 * @brief Feedforward(Motor_TargetVelocityToPwm) 위에 더할 PI 보정치 계산
 *
 * PI는 target/actual만 이용해 "보정 PWM"만 계산하며, Feedforward가 어떻게
 * 계산됐는지는 전혀 모른다(최종 PWM = Feedforward + 이 함수의 반환값).
 * Integral은 이미 Ki가 곱해진 PWM 단위로 *integral_pwm에 누적되어 있으므로
 * 여기서는 그 값을 읽기만 하고(P항만 매 호출 새로 계산), Integral 누적 자체는
 * Motor_UpdateActualVelocity()가 MOTOR_SAMPLE_PERIOD_MS 주기로 별도 수행한다
 * (그래야 Ki 적분 시간 기준이 어긋나지 않는다). 그 덕분에 이 함수는 Motor_Process()에서
 * 매 tick 호출해도 되고, Target이 바뀌면 다음 tick에 바로 반영된다.
 * 좌/우 각각 독립된 integral_pwm(포인터)로 호출되므로 로직은 하나만 존재한다.
 */
static float Motor_ComputePiCorrection(float target_rad_s, float actual_rad_s, volatile float *integral_pwm)
{
    float error_rad_s = target_rad_s - actual_rad_s;

    return (motor_pi_kp * error_rad_s) + *integral_pwm;
}


/**
 * @brief requested를 가속/감속 제한 + 방향 전환 보호를 거쳐 limited에 반영
 *
 * 좌/우 각각 독립된 state(limited_rad_s/integral_pwm/dir_state/hold_start_tick
 * 포인터)로 호출되므로 로직은 하나만 존재한다(Motor_ComputePiCorrection()과
 * 동일한 패턴). 호출부(Motor_UpdateActualVelocity())의 100ms 게이트 안에서만
 * 호출되며, 그 게이트에서 이미 계산된 elapsed_sec/now를 그대로 받아 쓴다 —
 * 매 tick 호출하면 dt가 일정하지 않아 rad/s^2 단위의 가감속 제한이
 * 부정확해지기 때문이다(Integral 누적과 동일한 이유).
 *
 * 상태 전이는 함수 상단의 typedef 주석 참고. ZEROING/ZEROED_WAITING/HOLDING
 * 중에는 requested를 참조하지 않는다(진행 중인 정지/대기 시퀀스를 requested
 * 변화로 중간에 바꾸지 않기 위함).
 */
static void Motor_AdvanceSpeedProfile(float requested_rad_s, float actual_rad_s,
                                       float elapsed_sec, uint32_t now,
                                       volatile float *limited_rad_s,
                                       volatile float *integral_pwm,
                                       MotorDirectionChangeState_t *dir_state,
                                       uint32_t *hold_start_tick)
{
    float max_delta;
    float delta;

    if (*dir_state == MOTOR_DIR_STATE_NORMAL)
    {
        /* limited와 requested가 정반대 부호이고 둘 다 0이 아니면 방향 전환으로
         * 판단한다. limited==0(정지 상태에서 출발)이면 곱이 0이 되어 여기 걸리지
         * 않고, 아래 NORMAL 가속 로직이 그냥 새 방향으로 가속을 시작한다. */
        if ((*limited_rad_s * requested_rad_s) < 0.0f)
        {
            *dir_state = MOTOR_DIR_STATE_ZEROING;

            /* 진행 중이던 Integral을 여기서 리셋한다 - 그렇지 않으면 이전
             * 방향으로 누적된 낡은 보정값이 감속 구간/대기 구간까지 그대로
             * 이어져, limited가 0에 도달한 뒤에도 0이 아닌 PI 출력을 만들
             * 수 있다. */
            *integral_pwm = 0.0f;
        }
    }

    if (*dir_state == MOTOR_DIR_STATE_ZEROING)
    {
        max_delta = MOTOR_DIRECTION_CHANGE_DECEL_RAD_S2 * elapsed_sec;

        delta = 0.0f - *limited_rad_s;
        if (delta > max_delta)
        {
            delta = max_delta;
        }
        else if (delta < -max_delta)
        {
            delta = -max_delta;
        }
        *limited_rad_s += delta;

        if (*limited_rad_s != 0.0f)
        {
            return;
        }

        *dir_state = MOTOR_DIR_STATE_ZEROED_WAITING;
        /* limited가 이번 호출에 막 0이 됐으므로, 한 tick 낭비하지 않고
         * 아래 ZEROED_WAITING 블록으로 바로 이어서 Actual까지 확인한다. */
    }

    if (*dir_state == MOTOR_DIR_STATE_ZEROED_WAITING)
    {
        /* limited는 이미 0이므로 여기서는 건드리지 않는다. Actual(엔코더
         * 실측값)이 threshold 이내로 들어와야만 다음 단계로 넘어간다 —
         * limited==0만으로는 "물리적으로 멈췄다"를 보장하지 못한다. */
        if (fabsf(actual_rad_s) < MOTOR_DIRECTION_ZERO_THRESHOLD_RAD_S)
        {
            *dir_state = MOTOR_DIR_STATE_HOLDING;
            *hold_start_tick = now;
        }

        return;
    }

    if (*dir_state == MOTOR_DIR_STATE_HOLDING)
    {
        if ((now - *hold_start_tick) < MOTOR_DIRECTION_CHANGE_HOLD_MS)
        {
            return; /* limited는 0에 고정된 채 대기 */
        }

        *dir_state = MOTOR_DIR_STATE_NORMAL; /* Hold 종료: 아래 NORMAL 로직으로 바로 이어서 진행 */
    }

    /* MOTOR_DIR_STATE_NORMAL: 일반 가속/감속 슬루레이트 리미터.
     * |requested|가 |limited|보다 크면(더 빨라지는 방향) 가속, 작으면 감속으로
     * 판단한다 - 이 지점에 도달했다는 것은 이미 같은 부호(또는 limited==0)라는
     * 뜻이므로 부호 비교 없이 크기만 비교하면 된다. */
    if (fabsf(requested_rad_s) > fabsf(*limited_rad_s))
    {
        max_delta = MOTOR_ACCEL_LIMIT_RAD_S2 * elapsed_sec;
    }
    else
    {
        max_delta = MOTOR_DECEL_LIMIT_RAD_S2 * elapsed_sec;
    }

    delta = requested_rad_s - *limited_rad_s;
    if (delta > max_delta)
    {
        delta = max_delta;
    }
    else if (delta < -max_delta)
    {
        delta = -max_delta;
    }

    *limited_rad_s += delta;
}


/**
 * @brief 좌/우 한쪽의 Stall 조건(3개 AND) 연속 유지 시간을 추적하는 디바운스
 *
 * condition_met이 거짓이면(조건 3개 중 하나라도 불충족) 즉시 타이머를 리셋한다
 * (요구사항: 일시적 부하로 오검출 금지 - 누적이 아니라 "연속 유지"만 인정).
 * condition_met이 처음 참이 된 순간에는 시작 시각만 기록하고 아직 미확정을
 * 반환하며, 이후 계속 참인 채로 MOTOR_STALL_DURATION_MS가 지나면 그때부터
 * 매 호출마다 1(확정)을 반환한다 - 호출부(Motor_UpdateActualVelocity())가
 * cause가 이미 NONE이 아닐 때는 이 함수 자체를 다시 호출하지 않으므로,
 * 확정 이후 반복 호출로 인한 재확정 여부는 문제되지 않는다.
 */
static uint8_t Motor_UpdateStallTimer(uint8_t condition_met, uint32_t now,
                                       uint8_t *timing, uint32_t *start_tick)
{
    if (!condition_met)
    {
        *timing = 0;
        return 0;
    }

    if (!*timing)
    {
        *timing = 1;
        *start_tick = now;
        return 0;
    }

    return ((now - *start_tick) >= MOTOR_STALL_DURATION_MS) ? 1u : 0u;
}


/**
 * @brief ΔEncoder Count -> RPM -> rad/s 순으로 Actual Wheel Velocity 갱신 +
 *        (활성 상태일 때만) Speed Profile 전진 + PI Integral 누적
 *
 * Motor_Process()가 매 tick 호출되는 것과 달리, 이 함수는 내부적으로
 * MOTOR_SAMPLE_PERIOD_MS(motor_config.h)가 지났을 때만 실제로 계산한다.
 * 매 tick(수 ms 미만 간격)마다 계산하면 그 사이 ΔEncoder Count가 너무 작아
 * 양자화 오차가 결과를 지배하게 되므로, StatusReporter와 동일한 tick-gating
 * 패턴으로 별도 주기를 둔다. Speed Profile(가감속 제한)도 rad/s^2 단위 제한을
 * 정확히 적용하려면 이 일정한 dt가 필요해 같은 게이트를 공유한다.
 *
 * Actual Wheel Velocity 갱신은 StopController/목표 속도와 무관하게 항상
 * 수행된다(엔코더 실측값이므로). Speed Profile 전진과 Integral 누적은 그
 * 결과(방금 갱신된 limited/error)와 이번에 실제로 흐른 시간(elapsed_sec)을
 * 그대로 재사용하되, motor_speed_control_enabled일 때만 수행한다 —
 * Motor_NormalStop()/Motor_EmergencyStop()이 정지 시 limited/Integral을 모두
 * 0으로 리셋해 두므로, 비활성 상태에서 이 블록을 건너뛰는 것만으로 두 값이
 * 계속 0에 머무른다(별도 초기화 로직 불필요).
 */
static void Motor_UpdateActualVelocity(void)
{
    uint32_t now = HAL_GetTick();
    uint32_t elapsed_ms = now - motor_velocity_last_sample_tick;
    int32_t  delta_left_count;
    int32_t  delta_right_count;
    float    elapsed_sec;
    float    left_rev_per_sec;
    float    right_rev_per_sec;
    float    left_rpm;
    float    right_rpm;

    if (elapsed_ms < MOTOR_SAMPLE_PERIOD_MS)
    {
        return;
    }

    /* ΔEncoder Count = 현재 누적값 - 직전 샘플 시점 누적값 */
    delta_left_count  = motor1_encoder_total - motor_velocity_last_left_total;
    delta_right_count = motor2_encoder_total - motor_velocity_last_right_total;

    elapsed_sec = (float)elapsed_ms / 1000.0f;

    /* ΔEncoder Count -> 회전수(rev) -> RPM */
    left_rev_per_sec  = ((float)delta_left_count  / MOTOR_ENCODER_COUNTS_PER_WHEEL_REV) / elapsed_sec;
    right_rev_per_sec = ((float)delta_right_count / MOTOR_ENCODER_COUNTS_PER_WHEEL_REV) / elapsed_sec;

    left_rpm  = left_rev_per_sec  * 60.0f;
    right_rpm = right_rev_per_sec * 60.0f;

    /* RPM -> rad/s (1rev = MOTOR_RADIANS_PER_REV, 1min = 60s) + 엔코더 방향 보정 */
    motor_actual_left_rad_s  = (left_rpm  / 60.0f) * MOTOR_RADIANS_PER_REV * (float)MOTOR_LEFT_ENCODER_DIRECTION_SIGN;
    motor_actual_right_rad_s = (right_rpm / 60.0f) * MOTOR_RADIANS_PER_REV * (float)MOTOR_RIGHT_ENCODER_DIRECTION_SIGN;

    motor_velocity_last_left_total  = motor1_encoder_total;
    motor_velocity_last_right_total = motor2_encoder_total;
    motor_velocity_last_sample_tick = now;

    /* ================================================
     * Speed Profile 전진 (비활성 상태면 건너뛰어 limited를 0에 고정)
     * ================================================ */
    if (motor_speed_control_enabled)
    {
        Motor_AdvanceSpeedProfile(motor_requested_left_rad_s, motor_actual_left_rad_s,
                                   elapsed_sec, now,
                                   &motor_limited_left_rad_s, &motor_pi_integral_left_pwm,
                                   &motor_dir_state_left, &motor_dir_hold_start_tick_left);
        Motor_AdvanceSpeedProfile(motor_requested_right_rad_s, motor_actual_right_rad_s,
                                   elapsed_sec, now,
                                   &motor_limited_right_rad_s, &motor_pi_integral_right_pwm,
                                   &motor_dir_state_right, &motor_dir_hold_start_tick_right);
    }

    /* ================================================
     * PI Integral 누적 (비활성 상태면 건너뛰어 Integral을 0에 고정)
     * - limited(Speed Profile 통과 후 값)를 목표로 오차를 계산한다. requested를
     *   그대로 쓰면 프로파일이 램프 중일 때 Integral이 아직 도달하지 않은 목표를
     *   향해 과도하게 반응하게 된다.
     * - 좌/우 각각 dir_state가 NORMAL 또는 ZEROING(아직 감속 중)일 때만
     *   누적한다. ZEROED_WAITING/HOLDING에서는 멈춘다 — limited==0으로 고정된
     *   상태에서 계속 오차를 쌓아봐야 Hold 종료 후 재가속 시점에 낡은 편향으로만
     *   작용하고, 이 두 상태에서는 Motor_Process()가 어차피 PWM을 강제로 0으로
     *   만들어 Integral을 반영할 곳도 없다.
     * ================================================ */
    if (motor_speed_control_enabled)
    {
        if ((motor_dir_state_left == MOTOR_DIR_STATE_NORMAL) || (motor_dir_state_left == MOTOR_DIR_STATE_ZEROING))
        {
            float error_left_rad_s = motor_limited_left_rad_s - motor_actual_left_rad_s;

            motor_pi_integral_left_pwm += motor_pi_ki * error_left_rad_s * elapsed_sec;

            /* Anti-Windup: Integral 상태 자체를 PWM 단위로 clamp(최종 PWM saturation과는 별개) */
            if (motor_pi_integral_left_pwm > MOTOR_PI_INTEGRAL_PWM_LIMIT)
            {
                motor_pi_integral_left_pwm = MOTOR_PI_INTEGRAL_PWM_LIMIT;
            }
            else if (motor_pi_integral_left_pwm < -MOTOR_PI_INTEGRAL_PWM_LIMIT)
            {
                motor_pi_integral_left_pwm = -MOTOR_PI_INTEGRAL_PWM_LIMIT;
            }
        }

        if ((motor_dir_state_right == MOTOR_DIR_STATE_NORMAL) || (motor_dir_state_right == MOTOR_DIR_STATE_ZEROING))
        {
            float error_right_rad_s = motor_limited_right_rad_s - motor_actual_right_rad_s;

            motor_pi_integral_right_pwm += motor_pi_ki * error_right_rad_s * elapsed_sec;

            if (motor_pi_integral_right_pwm > MOTOR_PI_INTEGRAL_PWM_LIMIT)
            {
                motor_pi_integral_right_pwm = MOTOR_PI_INTEGRAL_PWM_LIMIT;
            }
            else if (motor_pi_integral_right_pwm < -MOTOR_PI_INTEGRAL_PWM_LIMIT)
            {
                motor_pi_integral_right_pwm = -MOTOR_PI_INTEGRAL_PWM_LIMIT;
            }
        }
    }

    /* ================================================
     * Stall Detection (motor_config.h MOTOR_STALL_* 참고)
     * - 이미 확정된 Stall이 있으면(Motor_ClearStall() 전까지) 다시 판정하지
     *   않는다 - 최초 원인을 덮어쓰지 않기 위함이다.
     * - 좌/우 각각 아래 조건을 모두 만족해야 디바운스 타이머가 진행된다:
     *   1) motor_speed_control_enabled(정지/ESTOP 등으로 이미 꺼져 있으면 대상 아님)
     *   2) dir_state가 NORMAL 또는 ZEROING(ZEROED_WAITING/HOLDING은 방향 전환
     *      보호가 의도적으로 0으로 묶어두는 중이라 Stall과 무관 - 오검출 방지)
     *   3) |PWM| >= Threshold, |limited| >= Threshold, |actual| <= Threshold
     * - 좌/우 중 하나라도 이번에 새로 DURATION_MS를 채우면(rising edge) 그
     *   즉시 양쪽 PWM을 0으로 만들고 Motor_ResetSpeedController()로 나머지
     *   상태를 정리한다 - 한쪽만 막혀도 안전을 위해 로봇 전체를 세운다.
     * ================================================ */
    if (motor_stall_cause == MOTOR_STALL_NONE)
    {
        uint8_t left_eligible = motor_speed_control_enabled &&
            ((motor_dir_state_left == MOTOR_DIR_STATE_NORMAL) || (motor_dir_state_left == MOTOR_DIR_STATE_ZEROING));
        uint8_t right_eligible = motor_speed_control_enabled &&
            ((motor_dir_state_right == MOTOR_DIR_STATE_NORMAL) || (motor_dir_state_right == MOTOR_DIR_STATE_ZEROING));

        int16_t abs_left_pwm  = (motor_last_left_pwm  < 0) ? (int16_t)(-motor_last_left_pwm)  : motor_last_left_pwm;
        int16_t abs_right_pwm = (motor_last_right_pwm < 0) ? (int16_t)(-motor_last_right_pwm) : motor_last_right_pwm;

        uint8_t left_condition = left_eligible &&
            (abs_left_pwm >= MOTOR_STALL_PWM_THRESHOLD) &&
            (fabsf(motor_limited_left_rad_s) >= MOTOR_STALL_TARGET_RAD_S) &&
            (fabsf(motor_actual_left_rad_s) <= MOTOR_STALL_ACTUAL_RAD_S);

        uint8_t right_condition = right_eligible &&
            (abs_right_pwm >= MOTOR_STALL_PWM_THRESHOLD) &&
            (fabsf(motor_limited_right_rad_s) >= MOTOR_STALL_TARGET_RAD_S) &&
            (fabsf(motor_actual_right_rad_s) <= MOTOR_STALL_ACTUAL_RAD_S);

        uint8_t left_stalled_now  = Motor_UpdateStallTimer(left_condition, now,
                                                             &motor_stall_timing_left, &motor_stall_start_tick_left);
        uint8_t right_stalled_now = Motor_UpdateStallTimer(right_condition, now,
                                                             &motor_stall_timing_right, &motor_stall_start_tick_right);

        if (left_stalled_now || right_stalled_now)
        {
            /* 하드웨어 PWM을 이 tick 안에서 즉시 0으로(요구사항: "즉시") -
             * Motor_ResetSpeedController()가 speed_control_enabled를 꺼도
             * 그 효과는 다음 Motor_Process() 호출부터 반영되므로, 명시적으로
             * 먼저 0을 써서 지연 없이 보장한다. */
            Motor_SetLeftPwm(0);
            Motor_SetRightPwm(0);

            Motor_ResetSpeedController();

            motor_stall_cause = (MotorStallCause_t)
                ((left_stalled_now  ? (uint32_t)MOTOR_STALL_LEFT  : 0u) |
                 (right_stalled_now ? (uint32_t)MOTOR_STALL_RIGHT : 0u));
        }
    }
}


/**
 * @brief 왼쪽 모터(Motor1, TIM3) PWM 출력
 *
 * pwm > 0: 전진(CH2), pwm < 0: 후진(CH1), pwm == 0: 정지.
 * 반대 방향 채널은 항상 0으로 설정해 두 채널이 동시에 켜지지 않게 한다.
 * 입력값은 MOTOR_PWM_MAX 범위로 saturation한다.
 */
static void Motor_SetLeftPwm(int16_t pwm)
{
    if (pwm > MOTOR_PWM_MAX)
    {
        pwm = MOTOR_PWM_MAX;
    }
    else if (pwm < -MOTOR_PWM_MAX)
    {
        pwm = -MOTOR_PWM_MAX;
    }

    if (pwm > 0)
    {
        __HAL_TIM_SET_COMPARE(&htim3, TIM_CHANNEL_1, 0);
        __HAL_TIM_SET_COMPARE(&htim3, TIM_CHANNEL_2, (uint32_t)pwm);
    }
    else if (pwm < 0)
    {
        __HAL_TIM_SET_COMPARE(&htim3, TIM_CHANNEL_1, (uint32_t)(-pwm));
        __HAL_TIM_SET_COMPARE(&htim3, TIM_CHANNEL_2, 0);
    }
    else
    {
        __HAL_TIM_SET_COMPARE(&htim3, TIM_CHANNEL_1, 0);
        __HAL_TIM_SET_COMPARE(&htim3, TIM_CHANNEL_2, 0);
    }
}


/**
 * @brief 오른쪽 모터(Motor2, TIM4) PWM 출력
 *
 * pwm > 0: 전진(CH1), pwm < 0: 후진(CH2), pwm == 0: 정지.
 * 반대 방향 채널은 항상 0으로 설정해 두 채널이 동시에 켜지지 않게 한다.
 * 입력값은 MOTOR_PWM_MAX 범위로 saturation한다.
 */
static void Motor_SetRightPwm(int16_t pwm)
{
    if (pwm > MOTOR_PWM_MAX)
    {
        pwm = MOTOR_PWM_MAX;
    }
    else if (pwm < -MOTOR_PWM_MAX)
    {
        pwm = -MOTOR_PWM_MAX;
    }

    if (pwm > 0)
    {
        __HAL_TIM_SET_COMPARE(&htim4, TIM_CHANNEL_1, (uint32_t)pwm);
        __HAL_TIM_SET_COMPARE(&htim4, TIM_CHANNEL_2, 0);
    }
    else if (pwm < 0)
    {
        __HAL_TIM_SET_COMPARE(&htim4, TIM_CHANNEL_1, 0);
        __HAL_TIM_SET_COMPARE(&htim4, TIM_CHANNEL_2, (uint32_t)(-pwm));
    }
    else
    {
        __HAL_TIM_SET_COMPARE(&htim4, TIM_CHANNEL_1, 0);
        __HAL_TIM_SET_COMPARE(&htim4, TIM_CHANNEL_2, 0);
    }
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
 * @brief PI Speed Controller 관련 상태를 전부 초기 상태로 리셋 + 비활성화
 *
 * Motor_NormalStop()/Motor_EmergencyStop() 내부에서만 호출된다. Normal Stop/
 * 통신 Timeout/Latched Safe Stop(모두 Motor_NormalStop() 경유)과 Emergency
 * Stop(Motor_EmergencyStop() 경유) 4가지 정지 트리거가 이 두 함수로 수렴하므로,
 * 여기 한 곳만 손보면 StopController 쪽 코드는 전혀 건드릴 필요가 없다.
 * Motor는 StopController를 참조하지 않으며, 이 리셋은 오직 Motor 자신의
 * 내부 상태(정지 동작의 일부)로만 취급한다.
 *
 * requested/limited/Integral/방향 전환 상태/hold tick을 모두 여기서 리셋한다
 * (이 함수 하나만 보고 "정지 시 Speed Profile/PI 상태가 전부 깨끗해진다"는
 * 것을 확인할 수 있어야 한다). requested/hold tick은 현재 호출 순서상
 * (MotionController가 정지 중 매 tick 0을 다시 쓰고, hold tick은 HOLDING
 * 진입 시 항상 새로 쓰임) 리셋 없이도 실제로는 문제가 되지 않지만, 방어적으로
 * 명시한다.
 */
static void Motor_ResetSpeedController(void)
{
    motor_requested_left_rad_s  = 0.0f;
    motor_requested_right_rad_s = 0.0f;

    motor_pi_integral_left_pwm  = 0.0f;
    motor_pi_integral_right_pwm = 0.0f;

    motor_limited_left_rad_s  = 0.0f;
    motor_limited_right_rad_s = 0.0f;

    motor_dir_state_left  = MOTOR_DIR_STATE_NORMAL;
    motor_dir_state_right = MOTOR_DIR_STATE_NORMAL;

    motor_dir_hold_start_tick_left  = 0;
    motor_dir_hold_start_tick_right = 0;

    motor_speed_control_enabled = 0;
}


/**
 * @brief StopController 전용 일반 정지
 *
 * PWM duty만 0으로 만들고 BTS7960 Enable은 유지한다.
 * Motor_EmergencyStop()과는 서로 독립적이며 호출하지 않는다.
 * PI Speed Controller의 Integral 리셋 + 비활성화도 함께 수행한다.
 */
void Motor_NormalStop(void)
{
    /* Motor1: 왼쪽 모터 정지 */
    __HAL_TIM_SET_COMPARE(&htim3, TIM_CHANNEL_1, 0);
    __HAL_TIM_SET_COMPARE(&htim3, TIM_CHANNEL_2, 0);

    /* Motor2: 오른쪽 모터 정지 */
    __HAL_TIM_SET_COMPARE(&htim4, TIM_CHANNEL_1, 0);
    __HAL_TIM_SET_COMPARE(&htim4, TIM_CHANNEL_2, 0);

    Motor_ResetSpeedController();
}


/**
 * @brief StopController 전용 비상 정지
 *
 * PWM duty를 0으로 만드는 것에 더해 BTS7960 Enable 핀까지 즉시
 * Low로 내려 모터 구동 전류 자체를 차단한다.
 * Motor_NormalStop()과는 서로 독립적이며 호출하지 않는다.
 * PI Speed Controller의 Integral 리셋 + 비활성화도 함께 수행한다.
 *
 * BTS7960 Enable 핀은 Motor_Init()에서만 다시 SET되므로(재부팅 시), 이
 * Emergency Stop은 소프트웨어적으로 재활성화되지 않는다 — StopController의
 * "Emergency Stop은 재부팅까지 유지" 정책과 동일하며, PI 도입으로 이 동작이
 * 바뀌지 않는다.
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

    Motor_ResetSpeedController();
}


/**
 * @brief 좌우 요청 바퀴 각속도(rad/s) 저장 (requested)
 *
 * 여기 저장된 값은 그대로 PWM에 반영되지 않는다. Motor_AdvanceSpeedProfile()이
 * 가속/감속 제한 + 방향 전환 보호를 거쳐 만든 limited 값을 Feedforward/PI가
 * 대신 목표로 삼는다(Speed Profile 문서 주석은 motor_requested_* / motor_limited_*
 * 선언부 참고). 이 함수의 시그니처/호출부(MotionController)는 변경되지 않았다.
 */
void Motor_SetTargetWheelVelocity(float left_rad_s, float right_rad_s)
{
    motor_requested_left_rad_s  = left_rad_s;
    motor_requested_right_rad_s = right_rad_s;
}


/**
 * @brief PI Speed Controller 활성화 (MotionController 전용)
 *
 * MotionController_Process()가 StopController_IsStopped() == false일 때만
 * 호출해야 한다(MotionController_RequestWheelVelocity()에서는 호출하지 않음 —
 * Latched Safe Stop 중에도 SET_WHEEL_VEL은 계속 수신될 수 있어, 거기서
 * 호출하면 재부팅 전까지 유지되어야 할 Latched Safe Stop이 매 명령마다
 * 다시 활성화되는 안전 결함이 생긴다).
 *
 * 매 tick 반복 호출되어도 안전하도록 멱등하게 동작한다: 이미 활성화된
 * 상태라면 다시 1을 대입하는 것 외에 아무 부수효과가 없으며, Integral이나
 * 다른 PI 상태는 전혀 건드리지 않는다. Integral 리셋은 오직 정지 시
 * (Motor_NormalStop()/Motor_EmergencyStop())에만 수행된다.
 */
void Motor_EnableSpeedControl(void)
{
    motor_speed_control_enabled = 1;
}


/**
 * @brief 엔코더 값 갱신 + Actual Wheel Velocity 갱신 + Speed Profile 전진 +
 *        Feedforward+PI 기반 최종 PWM 반영 (Main Loop에서 매 tick 호출)
 *
 * 이전에는 Motor_WaitAndUpdateEncoder()가 지정된 시간만큼 블로킹하며
 * 10ms마다 이 갱신을 수행했으나, Main Loop가 논블로킹 구조로 바뀌면서
 * 매 tick 한 번씩 호출되는 것으로 대체되었다.
 *
 * 엔코더 갱신과 Actual Wheel Velocity 갱신(Motor_UpdateActualVelocity(), 내부에서
 * Speed Profile 전진도 함께 수행)은 motor_speed_control_enabled 상태와 무관하게
 * 항상 수행된다. 그 뒤 좌/우 각각 독립적으로:
 * - speed_control_enabled이고 dir_state가 NORMAL/ZEROING이면 Feedforward(기존
 *   Motor_TargetVelocityToPwm(), 변경 없음) + PI 보정(Motor_ComputePiCorrection())을
 *   limited(Speed Profile 통과 후 값) 기준으로 합산해 최종 PWM을 출력한다.
 * - 비활성 상태이거나 dir_state가 ZEROED_WAITING/HOLDING(방향 전환 보호로
 *   0 근처에서 대기 중)이면 Feedforward/PI 계산을 모두 건너뛰고 PWM을 0으로
 *   유지한다 — limited가 0이어도 Actual이 아직 남아있으면 PI가 능동적으로
 *   반대 방향 보정을 걸 수 있으므로, 이 구간에서는 계산 자체를 하지 않는다.
 */
void Motor_Process(void)
{
    int16_t left_pwm;
    int16_t right_pwm;
    float   left_correction_pwm;
    float   right_correction_pwm;
    float   left_pwm_f;
    float   right_pwm_f;

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


    /* ================================================
     * Actual Wheel Velocity 갱신 (MOTOR_SAMPLE_PERIOD_MS 주기, 함수 내부 tick-gating)
     * ================================================ */
    Motor_UpdateActualVelocity();


    /* ================================================
     * Feedforward + PI -> 최종 PWM 반영
     * - 목표값은 requested가 아니라 limited(Speed Profile 통과 후 값)이다.
     * - 좌/우 각각 독립적으로: speed_control_enabled이고 dir_state가 NORMAL
     *   또는 ZEROING(아직 감속 중)일 때만 계산해서 출력한다. ZEROED_WAITING/
     *   HOLDING에서는 PWM을 강제로 0으로 만든다 — limited==0이라 Feedforward는
     *   이미 0이지만, PI(Kp*error 또는 그전에 쌓인 Integral)는 Actual이 아직
     *   0이 아닌 동안 0이 아닌 값을 낼 수 있어서, 그 값이 Hold가 끝나기 전에
     *   PWM으로 새어나가지 않도록 여기서 명시적으로 막는다.
     * ================================================ */
    if (motor_speed_control_enabled &&
        ((motor_dir_state_left == MOTOR_DIR_STATE_NORMAL) || (motor_dir_state_left == MOTOR_DIR_STATE_ZEROING)))
    {
        left_correction_pwm = Motor_ComputePiCorrection(motor_limited_left_rad_s, motor_actual_left_rad_s, &motor_pi_integral_left_pwm);

        /* Feedforward는 기존 Open-loop 변환을 그대로 재사용(변경 없음, 입력만
         * requested에서 limited로 교체). PI 보정에도 동일한 좌우 방향 보정
         * (MOTOR_LEFT_DIRECTION_SIGN)을 적용해 Feedforward와 같은 부호 기준으로
         * 합산한다(그렇지 않으면 방향 보정이 -1인 바퀴에서 PI가 반대로 작동한다). */
        left_pwm_f = (float)(Motor_TargetVelocityToPwm(motor_limited_left_rad_s) * MOTOR_LEFT_DIRECTION_SIGN)
                     + (left_correction_pwm * (float)MOTOR_LEFT_DIRECTION_SIGN);

        /* 최종 PWM Saturation. Motor_UpdateActualVelocity() 내부의 Integral Clamp와는
         * 목적이 다르다 - 여기는 Feedforward+PI 합산 결과가 하드웨어 범위(MOTOR_PWM_MAX)를
         * 넘지 않도록 보장하는 것이고, Integral Clamp는 Anti-Windup이 목적이다. */
        if (left_pwm_f > (float)MOTOR_PWM_MAX)
        {
            left_pwm_f = (float)MOTOR_PWM_MAX;
        }
        else if (left_pwm_f < -(float)MOTOR_PWM_MAX)
        {
            left_pwm_f = -(float)MOTOR_PWM_MAX;
        }

        left_pwm = (int16_t)left_pwm_f;
    }
    else
    {
        /* 비활성 상태 또는 방향 전환 보호의 ZEROED_WAITING/HOLDING 중:
         * Feedforward/PI 계산 자체를 건너뛰고 PWM은 항상 0을 유지한다. */
        left_pwm = 0;
    }

    if (motor_speed_control_enabled &&
        ((motor_dir_state_right == MOTOR_DIR_STATE_NORMAL) || (motor_dir_state_right == MOTOR_DIR_STATE_ZEROING)))
    {
        right_correction_pwm = Motor_ComputePiCorrection(motor_limited_right_rad_s, motor_actual_right_rad_s, &motor_pi_integral_right_pwm);

        right_pwm_f = (float)(Motor_TargetVelocityToPwm(motor_limited_right_rad_s) * MOTOR_RIGHT_DIRECTION_SIGN)
                      + (right_correction_pwm * (float)MOTOR_RIGHT_DIRECTION_SIGN);

        if (right_pwm_f > (float)MOTOR_PWM_MAX)
        {
            right_pwm_f = (float)MOTOR_PWM_MAX;
        }
        else if (right_pwm_f < -(float)MOTOR_PWM_MAX)
        {
            right_pwm_f = -(float)MOTOR_PWM_MAX;
        }

        right_pwm = (int16_t)right_pwm_f;
    }
    else
    {
        right_pwm = 0;
    }

    Motor_SetLeftPwm(left_pwm);
    Motor_SetRightPwm(right_pwm);

    motor_last_left_pwm  = left_pwm;
    motor_last_right_pwm = right_pwm;
}


/**
 * @brief 현재 목표 좌우 바퀴 각속도(rad/s) 조회 (StatusReporter 전용)
 *
 * limited(Speed Profile 통과 후, Feedforward/PI가 실제로 추종하는 값)를
 * 반환한다. requested(가공되지 않은 요청값)가 아니다 — Feedforward/PI의
 * 실제 목표를 반환해야 STATUS Packet의 Target/Actual/Error가 PI 추종
 * 성능을 의미 있게 반영한다(requested를 그대로 노출하면 Speed Profile
 * 램프 중 Error가 프로파일 지연을 반영해 왜곡된다). STATUS Packet의
 * 필드 이름(LT/RT)이나 형식은 바뀌지 않는다.
 */
void Motor_GetTargetWheelVelocity(float *out_left_rad_s, float *out_right_rad_s)
{
    *out_left_rad_s  = motor_limited_left_rad_s;
    *out_right_rad_s = motor_limited_right_rad_s;
}


/**
 * @brief Motor_Process()가 마지막으로 출력한 좌우 PWM 조회 (StatusReporter 전용)
 */
void Motor_GetLastPwm(int16_t *out_left_pwm, int16_t *out_right_pwm)
{
    *out_left_pwm  = motor_last_left_pwm;
    *out_right_pwm = motor_last_right_pwm;
}


/**
 * @brief 엔코더 실측 기반 Actual Wheel Velocity(rad/s) 조회 (StatusReporter 전용)
 *
 * Motor_UpdateActualVelocity()가 MOTOR_SAMPLE_PERIOD_MS 주기로 갱신한 값을
 * 그대로 반환한다. 목표값/PWM과 무관하게 엔코더 실측값이므로, 정지 상태에서
 * 바퀴를 손으로 돌려도 이 값이 변한다.
 */
void Motor_GetActualWheelVelocity(float *out_left_rad_s, float *out_right_rad_s)
{
    *out_left_rad_s  = motor_actual_left_rad_s;
    *out_right_rad_s = motor_actual_right_rad_s;
}


/**
 * @brief PI 게인(Kp/Ki)을 런타임에 갱신 (UART SET_PI_GAINS 명령 전용)
 *
 * motor_config.h의 MOTOR_PI_KP_MIN/MAX, MOTOR_PI_KI_MIN/MAX 범위를 벗어나거나
 * NaN/Infinity면 아무 것도 바꾸지 않고 0을 반환한다(CommandParser_ParseFloat가
 * 이미 NaN/Infinity를 걸러내지만, 이 함수가 유일한 안전 경계가 되도록 여기서도
 * 다시 검증한다).
 *
 * 성공하면 게인을 갱신하고 좌우 PI Integral 상태만 0으로 초기화한다 — 이전
 * 게인으로 누적된 Integral이 새 게인에서 그대로 곱해지면 출력이 급변할 수
 * 있기 때문이다. Motor_ResetSpeedController()와 달리 motor_speed_control_enabled
 * 등 다른 상태는 건드리지 않는다(요청 속도/Speed Profile/Direction Change
 * 상태 유지).
 */
uint8_t Motor_SetPiGains(float kp, float ki)
{
    if (!isfinite(kp) || !isfinite(ki))
    {
        return 0;
    }

    if ((kp < MOTOR_PI_KP_MIN) || (kp > MOTOR_PI_KP_MAX))
    {
        return 0;
    }

    if ((ki < MOTOR_PI_KI_MIN) || (ki > MOTOR_PI_KI_MAX))
    {
        return 0;
    }

    motor_pi_kp = kp;
    motor_pi_ki = ki;

    motor_pi_integral_left_pwm  = 0.0f;
    motor_pi_integral_right_pwm = 0.0f;

    return 1;
}


/**
 * @brief 현재 적용 중인 PI 게인(Kp/Ki) 조회 (StatusReporter/Communication 전용)
 */
void Motor_GetPiGains(float *out_kp, float *out_ki)
{
    *out_kp = motor_pi_kp;
    *out_ki = motor_pi_ki;
}


/**
 * @brief Stall 확정 여부 조회 (StopController 전용, 매 tick 폴링됨)
 */
uint8_t Motor_IsStalled(void)
{
    return (motor_stall_cause != MOTOR_STALL_NONE) ? 1u : 0u;
}


/**
 * @brief 확정된 Stall의 원인(좌/우/양쪽) 조회 (StopController 전용)
 */
MotorStallCause_t Motor_GetStallCause(void)
{
    return motor_stall_cause;
}


/**
 * @brief Stall 원인 래치 + 디바운스 타이머 상태를 초기화 (UART RESET_STALL 전용)
 *
 * Speed Controller 재활성화나 target 복원은 하지 않는다 - Stall이 풀린 뒤에도
 * 모터는 정지 상태(target 0)를 유지해야 하며, 재출발은 이후 별도의 새
 * SET_WHEEL_VEL로만 이뤄져야 한다(motor/docs/serial_protocol.md 참고).
 */
void Motor_ClearStall(void)
{
    motor_stall_cause = MOTOR_STALL_NONE;

    motor_stall_timing_left  = 0;
    motor_stall_timing_right = 0;
    motor_stall_start_tick_left  = 0;
    motor_stall_start_tick_right = 0;
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
     * Actual Wheel Velocity 상태 초기화
     * - 첫 Motor_UpdateActualVelocity() 호출이 부팅 직후의 비정상적으로
     *   긴 경과시간을 기준으로 계산하지 않도록 현재 tick/누적값으로 맞춘다.
     * ========================================================= */
    motor_actual_left_rad_s  = 0.0f;
    motor_actual_right_rad_s = 0.0f;

    motor_velocity_last_sample_tick  = HAL_GetTick();
    motor_velocity_last_left_total   = motor1_encoder_total;
    motor_velocity_last_right_total  = motor2_encoder_total;


    /* =========================================================
     * PI Speed Controller 상태 초기화
     * - 부팅 직후에는 MotionController_Process()가 아직 한 번도 실행되지
     *   않았으므로, 안전하게 비활성 상태로 시작한다. StopController도
     *   이 시점엔 정지 상태가 아니므로(App_Init() 순서상 StopController_Init()
     *   이후), App_Run()의 첫 tick에서 MotionController_Process()가
     *   StopController_IsStopped() == false를 확인하고 즉시
     *   Motor_EnableSpeedControl()을 호출해 활성화된다.
     * ========================================================= */
    motor_speed_control_enabled = 0;

    motor_pi_integral_left_pwm  = 0.0f;
    motor_pi_integral_right_pwm = 0.0f;

    motor_requested_left_rad_s  = 0.0f;
    motor_requested_right_rad_s = 0.0f;

    motor_limited_left_rad_s  = 0.0f;
    motor_limited_right_rad_s = 0.0f;

    motor_dir_state_left  = MOTOR_DIR_STATE_NORMAL;
    motor_dir_state_right = MOTOR_DIR_STATE_NORMAL;

    motor_dir_hold_start_tick_left  = 0;
    motor_dir_hold_start_tick_right = 0;

    motor_stall_cause = MOTOR_STALL_NONE;
    motor_stall_timing_left  = 0;
    motor_stall_timing_right = 0;
    motor_stall_start_tick_left  = 0;
    motor_stall_start_tick_right = 0;


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
