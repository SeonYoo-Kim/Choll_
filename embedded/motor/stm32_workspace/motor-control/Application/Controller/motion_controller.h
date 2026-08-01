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

/* UART RESET_STALL 처리 전용(communication.c, StopController_ClearStall()
 * 성공 시에만 이어서 호출됨). 저장된 목표 좌우 바퀴 각속도를 0으로
 * 초기화한다 - 그렇지 않으면 Stall Fault 해제 직후 StopController_IsStopped()
 * 가 false가 되는 순간 MotionController_Process()가 Stall 이전의 오래된
 * target을 그대로 Motor에 전달해 자동으로 재출발할 수 있다. Speed
 * Controller/Motor 상태는 건드리지 않는다(Motor_ResetSpeedController()가
 * 이미 정리했음) - 오직 MotionController 자신이 들고 있는 저장값만
 * 정리한다. 재출발은 이후 별도의 새 SET_WHEEL_VEL(=MotionController_
 * RequestWheelVelocity() 호출)로만 이뤄진다. */
void MotionController_ResetTarget(void);

#endif /* MOTION_CONTROLLER_H */
