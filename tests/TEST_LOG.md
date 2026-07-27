# Test Log

테스트 실행 기록입니다. **에이전트(Claude)든 사람이든, 테스트를 돌렸으면 결과를 여기에 남깁니다.**
목적: "테스트 통과했다"는 말을 사람이 눈으로 검증할 수 있게 하는 것.

## 기록 규칙

- **최신 항목이 맨 위** (이 문단 바로 아래에 추가).
- 항목 형식: `## 날짜 시각 — 결과 요약 (실행자)` + 환경·명령·커밋 + 접힌 전체 출력(`<details>`).
- **실패도 기록한다.** 실패 → 수정 → 재실행이면 두 번 다 남겨서 이력이 보이게 한다.
- 원본 출력은 `<details>` 블록에 그대로 붙인다 (요약만 믿지 말고 검증 가능하게).

---

## 2026-07-27 17:07 — ✅ BE 20 tests·UTF-8 전체 재컴파일 통과 (Codex)

- **명령**: `backend/gradlew.bat test --rerun-tasks`
- **환경**: Windows 11, Microsoft OpenJDK 21.0.11
- **브랜치**: `backend/feature/socket_test`
- **결과**: 10 suites, 20 tests, 0 failures, 0 errors
- **검증 범위**: UTF-8 Java 전체 재컴파일, MQTT 활성 상태 애플리케이션 기동,
  메시지 파싱, 카트별 최근 위치 20개 제한, 다각형 구역 판정, 동일 구역 3회
  연속 감지
- **참고**: 구현 중 Paho 의존성 누락으로 컴파일 실패 후 명시적 의존성을
  추가했고, Spring Boot 4의 Jackson 3에 맞게 import를 수정한 뒤 재검증했다.
  샌드박스에서 Gradle 배포 파일 다운로드가 차단된 실행은 기존 캐시를 사용할 수
  있는 환경에서 다시 실행했다.

<details>
<summary>백엔드 Gradle 테스트 최종 출력</summary>

```text
> Task :compileJava UP-TO-DATE
> Task :processResources UP-TO-DATE
> Task :classes UP-TO-DATE
> Task :compileTestJava
> Task :processTestResources NO-SOURCE
> Task :testClasses
> Task :test

BUILD SUCCESSFUL in 29s
4 actionable tasks: 4 executed
```

</details>

## 2026-07-27 15:50 — ✅ BE 10 tests·FE 6 tests·lint·format·build 통과 (Codex)

- **명령**: `backend/gradlew.bat test`, `pnpm test`, `pnpm lint`, `pnpm format:check`, `pnpm build`
- **환경**: Windows 11, Microsoft OpenJDK 21.0.11, pnpm 11.9.0
- **커밋**: `9c70421` ([chore] OpenAPI 프론트 클라이언트 재생성)
- **맥락**: 노션 기준 API 계약, 백엔드 DTO·컨트롤러, springdoc YAML, orval 생성 클라이언트의 최종 정합성 검증.

<details>
<summary>백엔드 Gradle 테스트 전체 출력</summary>

```text
> Task :compileJava UP-TO-DATE
> Task :processResources UP-TO-DATE
> Task :classes UP-TO-DATE
> Task :compileTestJava
> Task :processTestResources NO-SOURCE
> Task :testClasses
OpenJDK 64-Bit Server VM warning: Sharing is only supported for boot loader classes because bootstrap classpath has been appended
> Task :test

BUILD SUCCESSFUL in 13s
4 actionable tasks: 2 executed, 2 up-to-date
```

Gradle XML 결과: 6 suites, 10 tests, 0 failures.

</details>

<details>
<summary>프론트 Vitest 전체 출력</summary>

```text
$ vitest run

 RUN  v4.1.10 C:/ssafy2_1/S15P11C101/frontend

 Test Files  2 passed (2)
      Tests  6 passed (6)
   Start at  15:49:28
   Duration  2.68s (transform 642ms, setup 1.54s, import 724ms, tests 35ms, environment 2.02s)
```

</details>

<details>
<summary>프론트 lint·format·build 전체 출력</summary>

```text
$ eslint .

$ prettier --check .
Checking formatting...
All matched files use Prettier code style!

$ tsc -b && vite build
vite v8.1.5 building client environment for production...
transforming...✓ 3328 modules transformed.
rendering chunks...
computing gzip size...
dist/index.html                     0.82 kB │ gzip:   0.48 kB
dist/assets/logo-CS11PIW0.png   3,392.58 kB
dist/assets/index-wTSF6KgR.css     18.42 kB │ gzip:   4.35 kB
dist/assets/index-BM8F48Jx.js     422.86 kB │ gzip: 142.04 kB

✓ built in 1.29s
```

</details>

## 2026-07-27 15:49 — ❌ 프론트 format 검사 실패 후 수정 (Codex)

- **명령**: `pnpm format:check`
- **환경**: Windows 11, pnpm 11.9.0
- **커밋**: `d22ad30` ([chore] OpenAPI 프론트 클라이언트 재생성, 수정 전)
- **맥락**: Git에서 무시되는 `shared/lib`를 `shared/utils`로 옮긴 직후 import가 재정렬되지 않아 실패. Prettier 적용 후 재검사 통과.

<details>
<summary>실패 출력</summary>

```text
$ prettier --check .
Checking formatting...
[warn] src/features/cart-map/ui/ArrivalModal.tsx
[warn] src/features/slot-board/ui/SlotDetailModal.tsx
[warn] src/features/slot-board/ui/SlotTile.tsx
[warn] src/pages/search/SearchPage.tsx
[warn] Code style issues found in 4 files. Run Prettier with --write to fix.
```

</details>

## 2026-07-27 15:41 — ❌ OpenAPI 재생성 직후 프론트 build 실패 후 수정 (Codex)

- **명령**: `pnpm build`
- **환경**: Windows 11, pnpm 11.9.0
- **커밋**: 미커밋 상태
- **맥락**: 기존 mock·story가 제거된 follow API와 이전 `Book` 타입을 참조하고, 새 nullable/필수 필드를 반영하지 않아 실패. 생성 타입에 맞춰 수정 후 빌드 통과.

<details>
<summary>실패 출력</summary>

```text
$ tsc -b && vite build
src/features/slot-board/ui/SlotTile.stories.tsx: Type 'SlotBook' 필수 필드 누락
src/features/slot-board/ui/SlotTile.test.tsx: 'lastDetectedAt' 필수 필드 누락
src/pages/search/SearchPage.tsx: nullable 'rfidTagId' 처리 누락
src/shared/api/mocks/handlers.ts: 삭제된 follow 모듈과 Book 타입 참조
Command failed with exit code 2.
```

</details>

## 2026-07-27 15:29 — ❌ 백엔드 테스트 컴파일 실패 후 수정 (Codex)

- **명령**: `backend/gradlew.bat test`
- **환경**: Windows 11, Microsoft OpenJDK 21.0.11
- **커밋**: 미커밋 상태
- **맥락**: Cart DTO 테스트 수정 중 `CartConnectionStatus` import 누락. import 복구 후 전체 테스트 통과.

<details>
<summary>실패 출력</summary>

```text
> Task :compileTestJava FAILED
CartServiceTests.java:41: error: cannot find symbol
    when(cart.getConnectionStatus()).thenReturn(CartConnectionStatus.OFFLINE);
                                                ^
  symbol:   variable CartConnectionStatus
  location: class CartServiceTests
1 error

BUILD FAILED in 3s
```

</details>

## 2026-07-24 14:37 — ✅ 12 passed (Claude)

- **명령**: `pytest tests/ -v`
- **환경**: Windows 11 개발 PC, Python 3.12.12 (miniforge base), pytest 9.1.1
- **커밋**: `ee8bab4` ([chore] ros2_ws→ai 잔여 경로 정리 및 구버전 루트 문서 삭제)
- **맥락**: `ros2_ws` → `ai` 디렉토리 이름 변경 후 conftest.py의 노드 import 경로 수정 검증.
  수정 전에는 conftest.py가 존재하지 않는 `ros2_ws/...` 경로를 참조해 테스트 수집이 불가능한 상태였음.
- **함께 실행**: `ruff check .` → 66건 (전부 노드 소스의 기존 이슈 — E501·docstring 등. 이번 변경 파일과 무관)

<details>
<summary>pytest 전체 출력</summary>

```
============================= test session starts =============================
platform win32 -- Python 3.12.12, pytest-9.1.1, pluggy-1.6.0 -- C:\Users\SSAFY\miniforge3\python.exe
cachedir: .pytest_cache
rootdir: C:\SSAFY\workspace\Choll
configfile: pyproject.toml
plugins: anyio-4.14.1
collecting ... collected 12 items

tests/test_control_logic.py::TestNormalizeCenterX::test_image_center_maps_to_zero PASSED [  8%]
tests/test_control_logic.py::TestNormalizeCenterX::test_left_edge_maps_to_minus_one PASSED [ 16%]
tests/test_control_logic.py::TestNormalizeCenterX::test_right_edge_maps_to_plus_one PASSED [ 25%]
tests/test_control_logic.py::TestNormalizeCenterX::test_quarter_position PASSED [ 33%]
tests/test_control_logic.py::TestNormalizeCenterX::test_out_of_frame_is_clamped PASSED [ 41%]
tests/test_control_logic.py::TestNormalizeCenterX::test_non_positive_width_raises PASSED [ 50%]
tests/test_control_logic.py::TestPidReset::test_reset_clears_integral_and_derivative_state PASSED [ 58%]
tests/test_pid.py::test_proportional_term_only PASSED                    [ 66%]
tests/test_pid.py::test_output_is_clamped_to_limit PASSED                [ 75%]
tests/test_pid.py::test_integral_accumulates_over_time PASSED            [ 83%]
tests/test_pid.py::test_derivative_responds_to_error_change PASSED       [ 91%]
tests/test_pid.py::test_zero_dt_disables_derivative PASSED               [100%]

============================= 12 passed in 0.05s ==============================
```

</details>
