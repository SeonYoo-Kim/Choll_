# CLAUDE.md — frontend/

쫄래쫄래 프로젝트의 **사서용 카트 관리 웹**입니다.
프로젝트 전체 맥락은 [루트 CLAUDE.md](../CLAUDE.md), 협업 규칙은 [docs/GIT_CONVENTION.md](../docs/GIT_CONVENTION.md)를 먼저 읽으세요.

## 서비스 정의

사서가 사용하는 웹 화면. 핵심 기능(기능 명세서 우선순위 "상" 기준):

- 슬롯 상태 보드: 각 슬롯의 비어 있음/책 있음/인식 실패, 슬롯별 책 정보(제목·구역·id)
- 지도: SLAM 지도 위 카트 위치 표시, 사용자 목적지 지정, 현재 구역 진입/도착 알림
- 정리 작업: 현재 구역에 꽂을 책이 있는 슬롯 표시·카운트, 전체 진행률(남은/완료 책 수)
- 카트 제어: 호출, 이동 취소(정지), 추종 시작/종료, 카트 상태(정지/운행) 표시
- 추종 대상 선택: WebRTC 영상 위에 AI가 탐지한 사람 후보를 표시하고 사서를 선택
- (우선순위 하) 사서 로그인, RFID 재인식 요청, 도서 검색

## 기술 스택

| 항목          | 값                                                   |
| ------------- | ---------------------------------------------------- |
| 코어          | React 18 + TypeScript + Vite                         |
| 상태관리      | TanStack Query(서버 상태) + Zustand(클라이언트 상태) |
| 스타일링      | SCSS + CSS Modules                                   |
| 패키지 매니저 | pnpm                                                 |
| UI 컴포넌트   | Ant Design + Storybook                               |
| API 모킹      | MSW + orval (OpenAPI 기반 클라이언트 생성)           |
| E2E 테스트    | Playwright                                           |

## BE 통신 계약

- **REST**: `/api/carts/{cartId}/...` — 카트·슬롯·지도·작업·이동·추종 조회/명령. 정본: API 명세서(노션)
- **WebSocket**: `/ws/carts/{cartId}` — 카트 관리 화면 진입 시 연결, JSON, BE→FE 단방향 이벤트
  (CART_POSITION_UPDATE, SLOT_UPDATED, FOLLOW_TARGETS_UPDATED 등 13종 — API 명세서 참조)
- **WebRTC**: 추종 대상 선택 시 카트 카메라 영상 수신 (시그널링은 BE 중계)
- 재연결 시 REST 재조회로 상태 복구 (BE-WS-03)

## 참고 문서

- API 명세서: https://app.notion.com/p/API-3a3135971f3c804c8c56e68e492e3990
- 기능 명세서 > 프론트: https://app.notion.com/p/3a3135971f3c80468d7ccd220a2a35e0
- Figma 웹 목업: https://www.figma.com/make/emuvioahRJ0y7fL1ssnWMn/웹-페이지-목업-ver.2
- Figma 유저 플로우: https://www.figma.com/board/9oo8WXRlcKIb90MP3qH9r9/유저-플로우

## 디렉토리 구조 (feature 기반)

```
src/
  app/        # 엔트리 조립: App, router, 전역 프로바이더(QueryClient, antd ConfigProvider)
  pages/      # 라우트 단위 페이지 (features를 조립)
  features/   # 도메인 기능: slot-board, cart-control, (예정) cart-map, sorting-task, follow-target
    <name>/ui/     # 컴포넌트 + *.module.scss + *.stories.tsx + *.test.tsx
    <name>/model/  # zustand 스토어, 로직 + *.test.ts
  shared/
    api/generated/ # orval 생성물 — 직접 수정 금지, openapi.yaml 수정 후 pnpm api:gen
    api/mocks/     # MSW 워커·핸들러 (고정 픽스처는 handlers.ts)
    api/ws/        # CartSocket (WS 재연결 래퍼)
    api/http.ts    # axios 인스턴스 + orval mutator (인증 헤더는 여기)
    styles/        # globals.scss, _variables.scss (디자인 토큰)
  test/       # vitest setup
openapi/openapi.yaml  # API 스펙 초안 — 정본은 노션, BE Swagger 나오면 교체
e2e/          # Playwright 테스트 (MSW로 BE 없이 동작)
```

## 자주 쓰는 명령

```bash
pnpm dev            # 개발 서버 (기본 MSW 모킹, .env.development의 VITE_ENABLE_MSW)
pnpm build          # tsc 타입체크 + 프로덕션 빌드
pnpm lint           # ESLint
pnpm format         # Prettier
pnpm test           # Vitest 단위 테스트
pnpm test:e2e       # Playwright E2E (dev 서버 자동 기동)
pnpm api:gen        # openapi/openapi.yaml → shared/api/generated 재생성
pnpm storybook      # Storybook (포트 6006)
```

## 이 디렉토리에서 지켜야 할 것

- 커밋 메시지 `[type] subject`, 브랜치는 `develop`에서 `feature/*` 분기 → [GIT_CONVENTION.md](../docs/GIT_CONVENTION.md)
- `node_modules/`, `dist/`, Storybook/Playwright 산출물은 커밋 금지 (`.gitignore` 유지)
- API 타입은 orval로 OpenAPI(Swagger)에서 생성 — 손으로 중복 정의하지 말 것
- 토픽/이벤트 계약 변경은 FE 단독으로 결정하지 말고 BE와 API 명세서를 먼저 갱신
