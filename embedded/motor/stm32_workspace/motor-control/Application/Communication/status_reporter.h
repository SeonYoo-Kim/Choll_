#ifndef STATUS_REPORTER_H
#define STATUS_REPORTER_H

#include "motor.h"

/* =========================================================
 * StatusReporter
 * - UART Protocol v1(docs/serial_protocol.md)의 STM -> PC STATUS Packet을
 *   일정 주기로 USART2(USB Serial)에 송신한다.
 * - 형식: STATUS,<LT>,<LA>,<RT>,<RA>,<LPWM>,<RPWM>,<LE>,<RE>\r\n
 * - Left/Right Actual(rad/s)은 Motor_GetActualWheelVelocity()가 엔코더
 *   실측값으로 계산한 값이다(Wheel Velocity PID는 아직 미구현이라 제어에는
 *   쓰이지 않고 텔레메트리 용도로만 사용됨).
 * - huart2 기반 STM -> PC 송신을 담당하는 유일한 모듈이라, 주기 송신인 STATUS
 *   Packet뿐 아니라 SET_PI_GAINS/RESET_STALL에 대한 ACK/ERROR, Stall
 *   FAULT / FAULT_CLEARED 같은 1회성 알림도 여기서 함께 보낸다(아래
 *   StatusReporter_SendPiGains* / StatusReporter_SendStall* / SendResetStall*).
 * ========================================================= */

void StatusReporter_Init(void);

/* Main Loop에서 매 tick 호출. STATUS_REPORTER_INTERVAL_MS 주기가 지났을 때만
 * STATUS Packet을 조립해 송신하고, 그 외에는 즉시 return한다(논블로킹 tick 검사). */
void StatusReporter_Process(void);

/* Communication(SET_PI_GAINS 처리) 전용. Motor_SetPiGains()가 성공했을 때
 * PC로 "PI_GAINS,<kp>,<ki>\r\n"(소수점 넷째 자리까지)을 즉시(블로킹) 송신한다.
 * STATUS Packet과 달리 주기 송신이 아니라 명령에 대한 1회성 응답이다. */
void StatusReporter_SendPiGainsAck(float kp, float ki);

/* Communication(SET_PI_GAINS 처리) 전용. 검증 실패 시 PC로
 * "ERROR,SET_PI_GAINS,<reason>\r\n"을 즉시(블로킹) 송신한다.
 * reason 예: "INVALID_FORMAT"(형식 오류), "OUT_OF_RANGE"(허용 범위 초과). */
void StatusReporter_SendPiGainsError(const char *reason);

/* StopController(StopController_Process()) 전용. Stall이 새로 확정된 그
 * tick에 PC로 "FAULT,STALL,<cause>\r\n"을 1회 송신한다(cause: LEFT/RIGHT/
 * BOTH). 호출부가 rising edge(!stall_stopped)에서만 부르므로 이 함수
 * 자체는 중복 송신을 막지 않는다 - 그 책임은 호출부에 있다. */
void StatusReporter_SendStallFault(MotorStallCause_t cause);

/* StopController(StopController_ClearStall() 성공 경로) 전용. Stall Fault가
 * 실제로 해제된 순간 PC로 "FAULT_CLEARED,STALL\r\n"을 1회 송신한다. */
void StatusReporter_SendStallCleared(void);

/* Communication(RESET_STALL 처리) 전용. StopController_ClearStall()이 성공
 * (STOP_CONTROLLER_STALL_RESET_OK)했을 때 PC로 "STALL_RESET,OK\r\n"을
 * 즉시(블로킹) 송신한다. 이 응답은 "Fault는 해제됐지만 모터는 여전히
 * 정지 상태(target 0)"를 의미하며, 재출발을 뜻하지 않는다
 * (motor/docs/serial_protocol.md RESET_STALL 절 참고). */
void StatusReporter_SendResetStallAck(void);

/* Communication(RESET_STALL 처리) 전용. StopController_ClearStall()이 실패했을
 * 때 PC로 "ERROR,RESET_STALL,<reason>\r\n"을 즉시(블로킹) 송신한다.
 * reason: "ESTOP_ACTIVE" / "LATCHED_SAFE_ACTIVE" / "NO_STALL". */
void StatusReporter_SendResetStallError(const char *reason);

#endif /* STATUS_REPORTER_H */
