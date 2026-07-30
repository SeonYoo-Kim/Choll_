# CLAUDE.md — embedded/
이 문서는 **임베디드 파트의 공통 규칙**을 설명합니다.
모듈별 구현 및 상세 내용은 각 하위 디렉토리의 `CLAUDE.md`를 우선합니다.
프로젝트 전체 개요는 [루트 CLAUDE.md](../CLAUDE.md)를 참고하세요.
Jetson ↔ STM32 인터페이스는 [docs/JETSON_TO_STM.md](../docs/JETSON_TO_STM.md)를 참고하세요.


## 역할
임베디드 파트는 카트의 하드웨어 제어를 담당합니다.
주요 구성은 다음과 같습니다.
- STM32 기반 모터 제어
- RFID 기반 도서 인식
- LED 제어
- Jetson과의 데이터 송수신
- 하드웨어 입출력(GPIO, PWM, UART 등)


## 디렉토리
| 경로 | 내용 |
|------|------|
| `motor/` | STM32 기반 모터 제어 |
| `rfid/` | RFID 인식 |
| `led/` | LED 제어 |


## 참고 문서
- 기능 명세서 > Embedded: https://app.notion.com/p/3a6135971f3c80c0a360d88ddfcf4e67
- 임베디드 워크플로우 (Excalidraw): https://excalidraw.com/#room=REDACTED 