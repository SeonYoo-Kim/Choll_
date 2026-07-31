#ifndef STOP_CONTROLLER_H
#define STOP_CONTROLLER_H

#include <stdint.h>

/* =========================================================
 * StopController
 * - 세 가지 독립적인 정지 레벨을 관리한다.
 *   1) Operational Stop : USB STOP, 통신 Timeout. 새 SET_WHEEL_VEL로 해제 가능.
 *   2) Latched Safe Stop : B1 버튼. 재부팅 전까지 해제되지 않음.
 *   3) Emergency Stop    : USB ESTOP. 즉시 Motor 전원 차단, 재부팅 전까지 해제되지 않음.
 * - 우선순위는 Emergency > Latched Safe > Operational이며, 상위 레벨이
 *   요청되면 대기 중인 하위 레벨 요청은 폐기된다.
 * - 입력은 Request 함수만 호출하고, 실제 Motor 호출은
 *   StopController_Process()에서만 수행한다.
 * ========================================================= */

void StopController_Init(void);

/* 정지 요청 등록 (짧게 끝남) */
void StopController_RequestOperationalStop(void);
void StopController_RequestLatchedSafeStop(void);
void StopController_RequestEmergencyStop(void);

/* 새로운 유효 SET_WHEEL_VEL 수신 시 호출: Operational Stop만 해제한다.
 * Latched Safe Stop과 Emergency Stop 상태에서는 아무 효과가 없다. */
void StopController_ClearOperationalStop(void);

/* Main Loop에서 주기적으로 호출: 등록된 요청을 실제 Motor 정지로 처리 */
void StopController_Process(void);

/* 세 레벨 중 하나라도 정지 중이면 1 */
uint8_t StopController_IsStopped(void);

/* Latched Safe Stop 또는 Emergency Stop(영구 정지, Resume 불가)이면 1 */
uint8_t StopController_IsLatched(void);

/* Emergency Stop 상태이면 1. MotionController가 이동 명령 무시 여부를 판단할 때 사용 */
uint8_t StopController_IsEmergency(void);

#endif /* STOP_CONTROLLER_H */
