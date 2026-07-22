### [Jetson ↔ STM32 통신 및 인터페이스 규격]

1. 하드웨어 및 통신 환경
   - 통신 방식: UART Serial
   - 보레이트(Baud Rate): 115200 bps (또는 460800, 921600 등)
   - 통신 프로토콜: micro-ROS (ROS 2 Humble 기반)

2. 수신 토픽 (Jetson -> STM32)
   - 토픽명: `/wheel_speed_cmd`
   - 메시지 타입: std_msgs/msg/Int32MultiArray
   - 데이터 매핑:
     - data[0]: 좌측 바퀴 목표 RPM (int32)
     - data[1]: 우측 바퀴 목표 RPM (int32)
   - 발행 주기: 10Hz ~ 12Hz

3. STM32에서 구현해야 할 micro-ROS 흐름
   - STM32CubeMX에서 UART 인터럽트/DMA 활성화
   - micro_ros_stm32_cubemx 라이브러리 포팅
   - `std_msgs__msg__Int32MultiArray` 구조체 구독자(Subscriber) 생성
   - 콜백 함수 안에서 data[0], data[1] 값을 파싱하여 모터 PID 제어 루프에 입력
