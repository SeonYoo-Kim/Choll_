# 기술 스택

> 개발 기간 중 노션에서 관리하던 기술 스택 문서의 이관본. 팀원은 담당 역할로 표기.

## FE (프런트엔드·디자인)

| 항목 | 스택 |
|---|---|
| 코어 | React 18 + TypeScript + Vite |
| 상태관리 | TanStack Query + Zustand |
| 스타일링 | SCSS + CSS Modules |
| 패키지 매니저 | pnpm |
| UI 컴포넌트 | Ant Design + Storybook |
| API 모킹 | MSW + orval |
| E2E 테스트 | Playwright |

## BE (백엔드)

Java 21, Spring Boot 4.1.0, Spring Data JPA, Gradle, JUnit 5 / Mockito,
Swagger (springdoc-openapi), MySQL 8.4, Eclipse Paho (MQTT), Spring WebSocket

## AI

- 런타임: Jetson Orin Nano 8GB, JetPack 6.2, TensorRT, CUDA 12.6, Python 3.10, ROS2 Humble
- Detection: YOLOv10s (TensorRT 엔진 변환, NMS-free)
- Tracking: ByteTrack
- Re-ID: OSNet_x1_0 (512-D feature) + Online Memory Bank

### YOLO 모델 선정 벤치마크 (Jetson 실측, 7 images)

| model | inference(ms) | postprocess(ms) | total(ms) | FPS est. | avg conf |
|---|---|---|---|---|---|
| yolov8n | 10.81 | 4.49 | 21.52 | 46.5 | 0.527 |
| yolov8s | 17.34 | 4.67 | 28.21 | 35.4 | 0.545 |
| yolov8m | 32.69 | 6.01 | 44.96 | 22.2 | 0.571 |
| yolo11n | 11.60 | 4.38 | 21.92 | 45.6 | 0.526 |
| yolo11s | 17.65 | 4.47 | 28.26 | 35.4 | 0.535 |
| yolo11m | 30.26 | 5.86 | 42.02 | 23.8 | 0.560 |
| yolov10n | 11.45 | **1.94** | 19.41 | 51.5 | 0.560 |
| **yolov10s** | 18.81 | **2.02** | 26.84 | 37.3 | **0.579** |
| yolov10m | 30.61 | 2.86 | 39.52 | 25.3 | 0.582 |

NMS-free 구조인 YOLOv10 계열의 후처리 시간이 절반 이하 — 정확도(conf)와 속도의 균형으로 **yolov10s 선정**.

## EM (SLAM·자율주행 / 모터제어 / LED·RFID)

- MCU: STM32 (NUCLEO-F446RE), BTS7960 모터 드라이버, DC 모터(PM36-3657-2465E) + AB 엔코더
- LiDAR: YDLIDAR X4Pro
- SLAM/Nav: ROS2 Humble, slam_toolbox, AMCL, Nav2, robot_localization(EKF), rf2o(레이저 오도메트리)
- RFID/LED: Raspberry Pi, RC522 리더 5기, WS2812B LED, paho-mqtt
- OS: Ubuntu 22.04.5 LTS

## INFRA

AWS EC2, Docker (compose), Jenkins (main 브랜치 웹훅 CI/CD), Mosquitto (MQTT broker), MySQL
