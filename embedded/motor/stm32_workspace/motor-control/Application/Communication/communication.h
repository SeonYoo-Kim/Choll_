#ifndef COMMUNICATION_H
#define COMMUNICATION_H

/* =========================================================
 * Communication
 * - SerialRx가 모은 Byte를 소비해 줄 단위 명령 문자열을 조립하고,
 *   CommandParser로 검증/파싱한 뒤 성공한 명령을 AppEventQueue에 등록한다.
 * - Motor나 Controller를 직접 호출하지 않는다.
 * - 비블로킹: 한 tick에 대기 중인 Byte를 모두 소비하고 즉시 return한다.
 * ========================================================= */

void Communication_Init(void);
void Communication_Process(void);

#endif /* COMMUNICATION_H */
