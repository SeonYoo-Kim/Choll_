#ifndef MOTOR_H
#define MOTOR_H

#include "main.h"

/* =========================================================
 * Motor1
 * - PWM     : TIM3 CH1 / CH2
 * - Encoder : TIM2
 * - Enable  : PB8 / PB9
 *
 * Motor2
 * - PWM     : TIM4 CH1 / CH2
 * - Encoder : TIM8
 * - Enable  : PA9 / PA8
 * ========================================================= */

/* =========================================================
 * Motor1 Encoder Variables
 * - TIM2 엔코더의 현재값, 변화량, 누적값을 저장
 * ========================================================= */
extern volatile uint16_t motor1_encoder_raw;
extern volatile uint16_t motor1_previous_count;
extern volatile int16_t  motor1_encoder_delta;
extern volatile int32_t  motor1_encoder_total;

/* =========================================================
 * Motor2 Encoder Variables
 * - TIM8 엔코더의 현재값, 변화량, 누적값을 저장
 * ========================================================= */
extern volatile uint16_t motor2_encoder_raw;
extern volatile uint16_t motor2_previous_count;
extern volatile int16_t  motor2_encoder_delta;
extern volatile int32_t  motor2_encoder_total;

/* =========================================================
 * Stall Detection
 * - 좌/우 중 어느 쪽이 원인인지 진단/외부 알림(FAULT Packet)을 위해 비트
 *   플래그로 보존한다. Motor_ResetSpeedController() 등 기존 정지 상태와는
 *   별도로 Motor_ClearStall()이 호출되기 전까지 래치된다.
 * ========================================================= */
typedef enum
{
    MOTOR_STALL_NONE  = 0,
    MOTOR_STALL_LEFT  = (1u << 0),
    MOTOR_STALL_RIGHT = (1u << 1),
    MOTOR_STALL_BOTH  = (MOTOR_STALL_LEFT | MOTOR_STALL_RIGHT)
} MotorStallCause_t;

/* =========================================================
 * Motor Public API
 * ========================================================= */

/* PWM/엔코더 시작 + BTS7960 Enable + 초기 정지 */
void Motor_Init(void);

/* 기본 주행 함수 */
void Motor_Forward(uint16_t pwm);
void Motor_Backward(uint16_t pwm);
void Motor_TurnRight(uint16_t pwm);
void Motor_TurnLeft(uint16_t pwm);
void Motor_Stop(void);

/* StopController 전용 정지 함수. 서로 독립적이며 상대를 호출하지 않는다. */
void Motor_NormalStop(void);
void Motor_EmergencyStop(void);

/* MotionController 전용. 좌우 요청 바퀴 각속도(rad/s, requested)를 저장한다.
 * 이 값이 그대로 PWM에 반영되지는 않는다 — Motor_Process() 내부에서 Speed
 * Profile(가속/감속 제한 + 방향 전환 보호)을 거친 뒤 Feedforward+PI가 그
 * 결과(limited)를 목표로 PWM에 반영한다(Motor_EnableSpeedControl()로
 * 활성화된 상태일 때만). */
void Motor_SetTargetWheelVelocity(float left_rad_s, float right_rad_s);

/* MotionController 전용. PI Speed Controller를 활성화한다.
 * MotionController_Process()가 StopController_IsStopped() == false일 때만
 * 호출해야 한다(MotionController_RequestWheelVelocity()에서는 호출 금지 —
 * Latched Safe Stop 중에도 SET_WHEEL_VEL이 들어올 수 있어 안전하지 않음).
 * 매 tick 반복 호출해도 안전한 멱등 함수이며, Integral 등 PI 상태는 건드리지
 * 않는다. 비활성화(Integral 리셋 포함)는 Motor_NormalStop()/
 * Motor_EmergencyStop() 내부에서만 수행된다. */
void Motor_EnableSpeedControl(void);

/* Main Loop에서 매 tick 호출: 엔코더 값 갱신 + Actual Wheel Velocity 갱신 +
 * Speed Profile 전진 + (활성 상태일 때만) Feedforward+PI 기반 최종 PWM 반영
 * (논블로킹) */
void Motor_Process(void);

/* StatusReporter 전용. Feedforward/PI가 실제로 목표로 삼는 현재 좌우 바퀴
 * 각속도(rad/s, limited — Speed Profile 통과 후 값)를 읽는다.
 * Motor_SetTargetWheelVelocity()로 저장한 requested(가공 전 요청값) 그대로가
 * 아니다. */
void Motor_GetTargetWheelVelocity(float *out_left_rad_s, float *out_right_rad_s);

/* StatusReporter 전용. Motor_Process()가 마지막으로 출력한 좌우 PWM
 * (부호 있는 -99~99, MOTOR_PWM_MAX 참고)을 읽는다. */
void Motor_GetLastPwm(int16_t *out_left_pwm, int16_t *out_right_pwm);

/* StatusReporter 전용. 엔코더 실측값으로 계산된 현재 좌우 Actual Wheel
 * Velocity(rad/s)를 읽는다(motor_config.h MOTOR_SAMPLE_PERIOD_SEC 주기 갱신). */
void Motor_GetActualWheelVelocity(float *out_left_rad_s, float *out_right_rad_s);

/* Communication(UART SET_PI_GAINS 명령) 전용. Kp/Ki를 런타임에 갱신한다.
 * motor_config.h의 MOTOR_PI_KP_MIN/MAX, MOTOR_PI_KI_MIN/MAX 범위를 벗어나거나
 * NaN/Infinity면 아무 것도 바꾸지 않고 0을 반환한다. 성공하면 motor_pi_kp/
 * motor_pi_ki를 갱신하고, 새 게인에서 이전 Integral이 그대로 남아 출력이
 * 급변하지 않도록 좌우 PI Integral 상태만 0으로 초기화한다(requested/limited
 * velocity, Speed Profile, Direction Change 상태, Speed Controller
 * Enable/Disable 여부는 건드리지 않는다 — Motor_ResetSpeedController()와는
 * 다르다) 후 1을 반환한다. */
uint8_t Motor_SetPiGains(float kp, float ki);

/* StatusReporter/Communication 전용. 현재 적용 중인 Kp/Ki를 읽는다. */
void Motor_GetPiGains(float *out_kp, float *out_ki);

/* StopController 전용. Motor_UpdateActualVelocity()가 100ms마다 판정하는
 * Stall(motor_config.h MOTOR_STALL_* 참고) 상태를 읽는다. Stall이 확정되면
 * Motor가 스스로 PWM 0 + PI Integral Reset + Speed Controller Disable까지
 * 수행한 뒤(Motor_ResetSpeedController() 재사용) 이 플래그만 Motor_ClearStall()
 * 호출 전까지 래치해 둔다 - Motor는 StopController를 호출하지 않으며(단방향
 * 의존성 유지), StopController가 매 tick 이 함수를 폴링해 자신의 상태에
 * 반영한다. */
uint8_t Motor_IsStalled(void);

/* StopController 전용. 확정된 Stall의 원인(좌/우/양쪽)을 읽는다. Stall이
 * 아니면 MOTOR_STALL_NONE. FAULT Packet(StatusReporter) 조립에 사용된다. */
MotorStallCause_t Motor_GetStallCause(void);

/* StopController 전용(RESET_STALL 처리 경로). Stall 원인/디바운스 타이머
 * 상태를 모두 초기화한다. Speed Controller 재활성화나 target 복원은 전혀
 * 하지 않는다 - 그건 이 함수의 책임이 아니다(호출자가 필요하면 별도로
 * 처리). */
void Motor_ClearStall(void);

#endif /* MOTOR_H */
