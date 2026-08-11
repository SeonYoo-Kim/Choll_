# Project Charter

## Vision

사서를 따라다니며 구역별 도서 정리를 돕는 ROS2 기반 자율주행 북카트.
최초 등록 후 한 명의 사서를 지속 추종하고(AI), 적재된 도서의 정리 구역을 안내하며(RFID·LED·웹),
지도에서 지정한 위치로 자율 이동한다(SLAM·Nav2).

## Goal (파트별)

| 파트 | 목표 |
|---|---|
| AI | 한 명의 사서를 등록부터 종료까지 추적, 1 m 거리 유지, 가림 후 재식별(Re-ID), Jetson 실시간 구동 |
| EM (SLAM·자율주행) | 실내 지도 작성·localization, 목적지 자율주행, 장애물 회피 |
| EM (모터·RFID·LED) | STM32 PI 속도 제어와 4단계 안전 정지, 슬롯별 RFID 인식과 LED 안내 |
| BE | 카트↔웹 허브 (MQTT↔WS 중계, 좌표 변환, 구역 판정, 정리 작업 관리) |
| FE | 사서용 실시간 관제 웹 (슬롯 보드, 지도, 추종 제어, 진행률) |

## Out of Scope

- Face Recognition
- Voice Recognition
- Human Pose Estimation
- Crowd Analysis
- 다중 카트 (단일 카트 전제 — MQTT 토픽에 cartId 미포함)
- 사서 계정·인증 (로그인 없음)

## Target Platform

- Jetson Orin Nano 8GB · ROS2 Humble · Python 3.10 · TensorRT
- STM32 NUCLEO-F446RE · Raspberry Pi
- Java 21 + Spring Boot · React 18 + TypeScript

## Constraints

- AI: 추가 데이터셋 수집 금지, fine-tuning 금지, TensorRT 추론 전용
- 임베디드 배포 (카트 위 실시간 동작)
- 5인 팀 · 7주 (기획~시연)

## Success Criteria — 최종 판정 (2026-08-11)

| 기준 | 판정 | 비고 |
|---|---|---|
| 10 FPS 이상 (LiDAR ~10 Hz 기준) | ✅ | Jetson 실측 |
| 1 m 거리 유지 추종 | ✅ | PID 레거시 경로로 시연 |
| 가림 후 타겟 재식별 | ✅ | 시연에서 방해자 테스트 재현 |
| 안정적인 ROS2 통신 | ✅ | |
| RFID 인식 → 웹 실시간 반영 → 구역 LED 안내 | ✅ | 실물 하드웨어로 시연 |
| SLAM 매핑·정합 | ✅ | 벽거리 median 0.031 m |
| Nav2 자율주행 (지도 클릭 이동·장애물 회피) | ❌ | P2P 도달은 성공, 회피 미성립·localization 불안정으로 시연 제외 — [RETROSPECTIVE.md](RETROSPECTIVE.md) |
| Demo-ready | ✅ | 사전 설계된 폴백(런북 시나리오 C)으로 시연 완료 |
