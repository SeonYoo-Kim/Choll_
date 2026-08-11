# Development Guide

## 💻 코딩 규칙 및 환경 (Coding Rules)

* **개발 환경**: ROS2 Humble, Python 3.10, Jetson Orin Nano 8GB, TensorRT.
* **AI 스택 규칙**: 파인튜닝(Fine-tuning) 금지. YOLOv10s TensorRT, ByteTrack, OSNet, Online Memory Bank만 사용하여 인퍼런스를 수행한다.
* **코드 스타일**: PEP8 준수, Type Hint 및 Docstring 필수. 전역 변수 사용 불가, 예외 처리와 로깅 필수.
* **아키텍처 원칙**: 하나의 ROS2 노드는 단일 책임(SRP)을 따른다. 느슨한 결합과 토픽 기반 통신으로 유지보수성과 모듈 재사용성을 높인다.
* **성능 예산**: 10 FPS+ (LiDAR 스캔 ~10 Hz 기준), 지연 < 100 ms, GPU 메모리 < 6 GB.

## 📅 단계별 개발 이력 (완료)

프로젝트 종료 시점 기준, 계획했던 AI 파트 3단계는 모두 완료됐다.
단계별 상세 진행 기록은 [ai/README.md](../ai/README.md)의 Current Progress,
검증 근거는 [ai/test/TEST_LOG.md](../ai/test/TEST_LOG.md)를 참조.

* **Step 1 — 탐지·추적** ✅: TensorRT YOLO 연결, ByteTrack ROS2 노드 구성, Bounding Box Publish.
* **Step 2 — Re-ID** ✅: OSNet Feature Extractor 연동, Cosine Similarity 기반 Target Selection, Memory Bank 적용.
* **Step 3 — 제어·복구** ✅: LiDAR 연동 PID 제어, Target Lost Recovery(재탐색), Online Memory Update, 시스템 데모.
* **Step 4 — 시스템 통합** (2026-07-31 아키텍처 변경 이후): `/target_position` 발행(AI)과
  SLAM Nav2 주행(EM)의 분리 — 통합 결과와 한계는 [RETROSPECTIVE.md](RETROSPECTIVE.md) 참조.
