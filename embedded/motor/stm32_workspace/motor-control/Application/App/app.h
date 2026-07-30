#ifndef APP_H
#define APP_H

/**
 * @brief 애플리케이션 초기화
 *
 * main()의 MX_xxx_Init() 이후 한 번 호출된다.
 * 각 모듈의 Init 함수를 이 안에서 순서대로 호출한다.
 * (AppEventQueue_Init(), Motor_Init(), StopController_Init(),
 *  MotionController_Init(), Communication_Init() 호출.
 *  향후 Encoder_Init(), Safety_Init() 등이 추가될 예정)
 */
void App_Init(void);

/**
 * @brief 애플리케이션 실행 (1 tick)
 *
 * main()의 while(1) 안에서 반복 호출된다.
 * Communication_Process() -> App_ProcessEvents() -> StopController_Process()
 * -> MotionController_Process() -> Motor_Process() -> AppTest_Process()
 * 순서로 각 모듈의 Process를 호출한다.
 * 블로킹 없이 즉시 return하므로 매 호출이 매우 짧게 끝난다.
 */
void App_Run(void);

#endif /* APP_H */
