# Development Guide

## 💻 코딩 규칙 및 환경 (Coding Rules)
* **개발 환경**: ROS2 Humble, Python 3.10, Jetson Orin Nano 8GB, TensorRT 환경에서 개발되어야 합니다[cite: 5].
* **AI 스택 규칙**: 파인튜닝(Fine-tuning)을 금지하며, YOLOv10s TensorRT, ByteTrack, OSNet, Online Memory Bank만 사용하여 인퍼런스를 수행해야 합니다[cite: 5].
* **코드 스타일**: PEP8 준수, Type Hint 및 Docstring 작성을 필수로 합니다[cite: 5]. 전역 변수(Global Variables) 사용은 불가하며 예외 처리(Exception Handling)와 로깅(Logging)을 반드시 구현해야 합니다[cite: 5].
* **아키텍처 원칙**: 하나의 ROS2 노드는 단일 책임(Single Responsibility) 원칙을 따릅니다[cite: 5]. 느슨한 결합(Loose Coupling)과 토픽 기반 통신으로 구현하여 유지보수성을 높이고 모듈 재사용성을 극대화합니다[cite: 5].
* **성능 최적화 원칙**: 목표 프레임(10 FPS, LiDAR 스캔 ~10 Hz 기준) 유지를 위해 낮은 CPU 사용량을 지향하며 텐서RT 인퍼런스에 집중합니다[cite: 5]. 안정성을 위해 메모리 점유율은 6GB 미만으로 관리합니다[cite: 5].

## 📅 단계별 개발 일정 및 상태 (TODO)
* **Step 1**
  * YOLO 및 ByteTrack ROS2 노드 연결 및 구성[cite: 6, 9].
  * TensorRT YOLO 연결 완료하기[cite: 9].
  * Bounding Box Publish 구현[cite: 9].
* **Step 2**
  * Re-ID 모델 및 Memory Bank 적용[cite: 6].
  * OSNet 연결 및 Feature Extractor 연동[cite: 9].
  * Cosine Similarity 계산 및 Target Selection 구현[cite: 9].
* **Step 3**
  * LiDAR 센서 연결 및 PID 제어 적용[cite: 6, 9].
  * 코드 및 성능 최적화(Optimization)[cite: 6, 9].
  * Target Lost Recovery(타겟 재탐색) 및 Online Memory Update 구현[cite: 9].
  * 시스템 데모(Demo) 시연[cite: 9].