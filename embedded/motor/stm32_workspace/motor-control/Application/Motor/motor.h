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

/* MotionController 전용. 좌우 목표 바퀴 각속도(rad/s)를 저장만 한다.
 * Wheel Velocity PID가 아직 없으므로 PWM에는 반영되지 않는다. */
void Motor_SetTargetWheelVelocity(float left_rad_s, float right_rad_s);

/* Main Loop에서 매 tick 호출: 엔코더 값 갱신 (논블로킹) */
void Motor_Process(void);

#endif /* MOTOR_H */
