#ifndef STOP_CONTROLLER_H
#define STOP_CONTROLLER_H

#include <stdint.h>

/* =========================================================
 * StopController
 * - 네 가지 독립적인 정지 레벨을 관리한다.
 *   1) Operational Stop : USB STOP, 통신 Timeout. 새 SET_WHEEL_VEL로 해제 가능.
 *   2) Latched Safe Stop : B1 버튼. 재부팅 전까지 해제되지 않음.
 *   3) Emergency Stop    : USB ESTOP. 즉시 Motor 전원 차단, 재부팅 전까지 해제되지 않음.
 *   4) Stall Fault       : Motor가 자체 감지(motor_config.h MOTOR_STALL_*).
 *                          UART RESET_STALL로만 해제 가능(자동 해제 없음).
 * - 우선순위는 Emergency > Latched Safe > Operational이며, 상위 레벨이
 *   요청되면 대기 중인 하위 레벨 요청은 폐기된다. Stall Fault는 이 셋과
 *   별개의 독립 플래그이며 요청 경합에 참여하지 않는다(Motor가 이미 래치한
 *   상태를 StopController가 매 tick 폴링해 반영할 뿐).
 * - 입력은 Request 함수만 호출하고, 실제 Motor 호출은
 *   StopController_Process()에서만 수행한다.
 * ========================================================= */

/* StopController_ClearStall()의 결과. RESET_STALL UART 명령 처리부
 * (communication.c)가 이 값을 보고 ACK/ERROR를 결정한다. */
typedef enum
{
    STOP_CONTROLLER_STALL_RESET_OK = 0,               /* Stall Fault 해제 성공 */
    STOP_CONTROLLER_STALL_RESET_ESTOP_ACTIVE,         /* Emergency Stop이 걸려 있어 거부 */
    STOP_CONTROLLER_STALL_RESET_LATCHED_SAFE_ACTIVE,  /* Latched Safe Stop이 걸려 있어 거부 */
    STOP_CONTROLLER_STALL_RESET_NO_STALL              /* 해제할 Stall이 애초에 없음 */
} StopControllerStallResetResult_t;

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

/* UART RESET_STALL 명령 전용(communication.c에서 직접 호출, AppEventQueue를
 * 거치지 않음 - SET_PI_GAINS와 동일한 이유: 1회성 명령에 확정적인 ACK/ERROR가
 * 필요해 큐 드롭 위험을 피한다). Stall Fault만 해제하며, Emergency Stop이나
 * Latched Safe Stop이 걸려 있으면 그 상태를 그대로 유지한 채 거부한다(뒷문으로
 * 풀리지 않음). 성공해도 모터가 다시 움직이지는 않는다 - Speed Controller
 * 재활성화나 target 복원은 전혀 하지 않으며, 호출자(communication.c)가
 * MotionController_ResetTarget()을 함께 호출해 이전 목표 속도가 남아
 * 자동으로 재출발하지 않도록 해야 한다. */
StopControllerStallResetResult_t StopController_ClearStall(void);

#endif /* STOP_CONTROLLER_H */
