#ifndef MOTION_CONTROLLER_H
#define MOTION_CONTROLLER_H

/* =========================================================
 * MotionController
 * - USB SET_WHEEL_VEL 명령으로 들어온 좌우 목표 바퀴 각속도(rad/s)를
 *   저장하고, StopController 상태에 따라 Motor에 전달할지 결정한다.
 * - Emergency Stop 상태에서는 새 목표값 수신 자체를 무시한다(래치 유지).
 * - Operational Stop / Latched Safe Stop 상태에서는 목표값은 저장하되
 *   Motor에는 항상 0을 전달한다(정지 유지).
 * - 300ms 이상 유효 SET_WHEEL_VEL을 받지 못하면 통신 Timeout으로 보고
 *   AppEventQueue에 APP_EVENT_COMMUNICATION_TIMEOUT을 1회만 발행한다.
 * - 아직 Wheel Velocity PID가 없으므로 Motor에는 목표값만 전달되고,
 *   실제 폐루프 속도 제어는 이루어지지 않는다.
 * ========================================================= */

void MotionController_Init(void);

/* 목표 좌우 바퀴 각속도(rad/s) 요청. Emergency Stop 상태이면 무시된다.
 * Operational Stop 상태였다면 새 요청으로 자동 해제된다. */
void MotionController_RequestWheelVelocity(float left_rad_s, float right_rad_s);

/* Main Loop에서 매 tick 호출: 통신 Timeout 검사 + StopController 상태를
 * 반영해 Motor에 목표값 전달 */
void MotionController_Process(void);

#endif /* MOTION_CONTROLLER_H */
