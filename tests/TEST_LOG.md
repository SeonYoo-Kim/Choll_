# Test Log

파트 공통 테스트 실행 기록입니다. **에이전트든 사람이든, 테스트를 돌렸으면 결과를 여기에 남깁니다.**
목적: "테스트 통과했다"는 말을 사람이 눈으로 검증할 수 있게 하는 것.

> **AI 파트 기록은 [ai/test/TEST_LOG.md](../ai/test/TEST_LOG.md)로 이동했습니다.** 여기에는 FE/BE/EM 및
> 여러 파트에 걸친 검증 기록을 남깁니다.

## 기록 규칙

- **최신 항목이 맨 위** (이 문단 바로 아래에 추가).
- 항목 형식: `## 날짜 시각 — 결과 요약 (실행자)` + 환경·명령·커밋 + 접힌 전체 출력(`<details>`).
- **실패도 기록한다.** 실패 → 수정 → 재실행이면 두 번 다 남겨서 이력이 보이게 한다.
- 원본 출력은 `<details>` 블록에 그대로 붙인다 (요약만 믿지 말고 검증 가능하게).

---

## 2026-08-09 — ✅ BE: 위치 yaw 수신·변환·중계 (Claude)

- **배경**: EM ROS2_API.md(2026-08-09 실측)의 🔴 지적 — EM은 `status/position`에 yaw(라디안,
  CCW+)를 실기 발행 중인데 BE `PositionPayload`에 필드가 없어 버려지고, FE에는
  `TEMPORARY_YAW=0`이 나가 마커가 항상 오른쪽을 봤다
- **변경** (`backend/fix/position-yaw`):
  - `PositionPayload`·`PositionSample`에 `yaw` 추가 (없으면 null — 구버전 페이로드 호환)
  - `SlamCoordinateConverter.toImageYaw`: **방향도 좌표와 같은 변환을 적용** — 방향 벡터
    (cos,sin)에 변환 선형부를 곱해 재계산. 아핀 지도는 회전·반전 반영, 기본식 지도는 부호
    반전(-yaw, 세로반전), pixels 모드는 원값 중계
  - `TEMPORARY_YAW` 제거, WS CART_POSITION_UPDATE에 변환된 yaw 실림 (FE는 수정 불요 —
    이미 yaw로 마커 회전)
- **명령·결과**: `gradlew.bat test` → **97개 중 96개 통과, 실패 1**:
  `BackendApplicationTests.contextLoads` — 로컬 MySQL80 서비스가 내려가 있어 DB 연결 실패
  (변경과 무관한 환경 문제, 서비스 기동 후 재확인 필요). 위치 패키지 단위 테스트
  (`mqtt.position.*`, 신규 6 포함)는 전부 통과
- **신규 테스트**: EM 실측 페이로드(yaw 포함) 파싱 / 구버전(yaw 없음) 호환 / pixels 원값 중계 /
  meters 세로반전(-0.5) / 아핀 회전 방향(+90°) / yaw 미수신 시 0

## 2026-08-08 00:30 — ✅ E2E: 실좌표(아핀 초기값)로 전체 사슬 재검증 (Claude)

- **배경**: 사람이 제공한 이미지 3장(RViz 스크린샷 원본 2732×1799 / 좌우반전본 906×645 /
  평면도 1000×600)으로 world→평면도 아핀 초기 계수를 이미지 정합으로 산출
- **정합 방법** (표준 라이브러리+numpy, PNG 디코더 자작):
  1. pgm 장애물(5,649px) ↔ 반전본 벽 마스크를 FFT 상관으로 탐색 —
     **좌우반전 + 회전 -25.85° + 배율 5.550** (겹침 1,568점, 사람 진술과 일치)
  2. 반전본에서 안쪽 벽 크롭 후보 조합 × 서가 특징 잔차 최소화 → 크롭 x[30..812] y[30..643]
  3. 합성 아핀: A=[[-127.74, -61.89],[47.37, -97.77]], t=(834.80, 357.11) —
     행렬식 +15,422 (반전 상쇄로 고유회전, 예측대로), 방 크기 약 7.0×5.5m
  4. 검증 렌더: 평면도 위에 pgm 장애물 투영 — 벽이 캔버스 가장자리에, 정사각 구조물이
     100·000 서가 블록 안에 정확히 안착. 서가 잔차 3~62px(평면도가 도식화된 그림인 한계)
- **적용**: `library-map-affine-initial.sql` → 로컬 DB, BE 재기동(아핀 컬럼 생성),
  가짜 Jetson `--start-world=-0.743,2.096` (START_POSITION의 실좌표)
- **E2E 결과** (모두 실좌표):
  - 위치 상행: SLAM(-0.743, 2.096) → BE 변환 image=(800.00, 116.98) → FE 마커 (80%, 19.5%) —
    목표 START(800,117)와 0.02px 오차
  - 반납 테이블 클릭: BE 하행 `target=(-1.451, 1.538)` = 사전 계산 예측값과 정확히 일치 →
    가짜 Jetson 주행 → 마커 (92.497%, 23%) 정지 + "반납 테이블에 도착했어요"
- **한계·후속**: 이 계수는 **이미지 정합 기반 초기 근사값** (서가 기준 수십 cm 오차 가능).
  시연 장소에서 `calibrate_map_transform.py` 3점 캘리브레이션으로 교체할 것

## 2026-08-07 23:30 — ✅ BE: 지도 아핀 변환 + 캘리브레이션 도구 (Claude)

- **배경**: EM의 실지도(library_map.pgm 366×319, res 0.05, origin [-8.14,-4.75]) 분석 결과
  ① 방이 SLAM 좌표계에서 ~25° 회전, ② FE 평면도는 그 지도를 **좌우반전+회전+크롭**해 제작
  (사람 확인). 반전이 섞이면 world→픽셀 변환의 부호가 뒤집혀 기존 resolution·origin
  (세로반전식)으로는 수학적으로 표현 불가 → 일반 아핀 변환 필요. pgm 특징(서가 클러스터)으로
  초기값 역산을 시도했으나 클러스터 배열이 평면도와 불일치해 **역산 포기, 캘리브레이션 방식 채택**
- **변경** (`backend/feature/navigation-uplink`):
  - `LibraryMap`에 아핀 6계수(affine_a11·a12·a21·a22·tx·ty, nullable) — REST 밖, SQL로만 주입
  - `SlamCoordinateConverter`: 계수가 있으면 픽셀=A·world+t (역변환은 역행렬), 행렬식 0이면
    조용한 오좌표 대신 IllegalStateException. 계수 없으면 기존 방식 폴백 (기존 테스트 무수정 통과)
  - `scripts/calibrate_map_transform.py` 신규 — 대응점 3+개("wx,wy=px,py")로 최소제곱 아핀을
    풀고 잔차와 library_maps UPDATE SQL 출력. 외부 의존 없음(가우스 소거 직접 구현)
- **명령·결과**: `gradlew.bat test` → **92 tests, 0 failures** (신규 3: 아핀 우선 적용 /
  아핀 왕복 ±0.5px / 퇴화 행렬 명시적 실패)
- **스크립트 자가 검증**: 알려진 변환 A=[[50,50],[50,-50]], t=(180,230)의 대응점 4개 입력 →
  정확히 복원, 잔차 0.0px, 행렬식 -5000(반전 포함) 판정 정상
- **남은 것**: 실제 계수 — 시연 장소에서 카트를 아는 지점 3곳에 놓고 SLAM 좌표를 받아
  스크립트 실행(도크스트링에 절차). 그 전 초기 근사값은 FE 디자인 툴의 레이어 배치 정보로 계산 예정

## 2026-08-07 18:20 — ✅ FE+BE: SLAM 실측 평면도 반영, 전 좌표 재측정 (Claude)

- **배경**: SLAM으로 실측해 다시 그린 평면도(1000×600)로 map.png 교체 → 통로·테이블·서가
  배치가 모두 이동. 1px 캔버스 스캔으로 재측정해 FE 좌표와 BE 시드를 동시 갱신
- **실측값** (픽셀 [L,T,R,B]): Z3 [10,128,255,582] / Z2 [450,128,631,582] / Z1 [827,128,989,582],
  서가 800·200 블록 [266,263,439,393](중앙 분할 352) / 100·000 블록 [642,263,815,393](분할 728),
  사서 테이블 [0,0,362,107] / 반납 테이블 [850,0,999,107]
- **변경**:
  - FE: `ZONE_RECTS`·`CORRIDOR_Y`(19.5)·`START_POSITION`·`MAP_LANDMARKS`(테이블 2+서가 4,
    정차점 6개) 갱신. **사서 테이블 정차점(35, 23)이 구역 밖 흰 바닥이 됨** — 자유 좌표
    이동이라 허용하고, 정차점 불변식을 "구역 안"→"장애물 밖"으로 완화
    (서가 정차점 4개는 여전히 해당 통로 안 강제). zoneStore 테스트의 옛 좌표 하드코딩 수정
  - BE 시드: 존 폴리곤 3개 + 책장 4면 좌표(면 중심 y=328) 갱신, 로컬 DB 적용
- **명령·결과**: `pnpm test --run` → **20 files, 138 tests, 0 failures** / `tsc` 0 / `eslint` 0
  (1차 실패 1건: zoneStore.test의 옛 좌표 → 신 좌표로 수정 후 통과)
- **브라우저 검증**:
  - 오버레이 정합(버튼 내부 기대 색 비율): 구역 99.0~99.3%, 서가 93.5~95.5%, 테이블 93.1~97.4%
  - E2E(실 BE+가짜 Jetson): 000 총류 서가 클릭 → 마커 정확히 신 정차점 (87.7%, 54.7%),
    신 폴리곤으로 구역 판정 → "1구역에 도착했어요!" 모달
- **주의**: `library_maps`의 resolution·origin은 여전히 가값(0.01, 0,0) — 실기 연동 시
  SLAM map.yaml 기준으로 평면도가 덮는 범위를 계산해 입력해야 좌표 변환이 맞는다

## 2026-08-07 17:50 — ✅ FE+BE: 자유 좌표 이동 (스냅 제거) + E2E (Claude)

- **배경**: 이동 명령을 2갈래로 확정 — ① 바닥(구역·통로) 아무 좌표나 찍으면 그 지점으로,
  ② 장애물(서가 4면·테이블 2개)을 찍으면 그 앞 고정 정차점으로. 어제 넣은 BE 스냅은
  통로 클릭까지 구역 안으로 끌어당겨 ①과 충돌 → 제거
- **변경**:
  - FE (`frontend/feat/map-landmarks`): `MAP_LANDMARKS`에 서가 4면 추가(클릭 영역=서가 면,
    정차점=그 면이 보는 통로 안 0.5m 여유). 도착 안내를 랜드마크별로 구분 —
    서가행은 구역 정리 모달(`arrival:'zone'`), 테이블·자유 지점은 이름 토스트(`arrival:'toast'`).
    통로 클릭은 "지정한 위치"로 안내
  - BE (`backend/feature/navigation-uplink`): `snapIntoZone` 제거, 클릭 좌표 그대로 하행.
    장애물 회피는 FE 책임 + Nav2 거부(status/nav-result ABORTED·REJECTED→FAILED)가 안전망.
    `PolygonZoneMatcher`는 구역 판정 `contains`만 남김(깨진 폴리곤 관용 파싱은 유지),
    `navigation.snap-margin-meters` 삭제
- **명령·결과**:
  - `frontend: pnpm test --run` → **20 files, 137 tests, 0 failures** / `tsc` 0 / `eslint` 0
  - `backend: gradlew.bat test` → **89 tests, 0 failures** (스냅 테스트 7개 제거)
- **E2E** (BE bootRun + 가짜 Jetson + FE 8081 실연동):
  - 흰색 상단 통로 (50%, 17%) 클릭 → 마커 (49.9%, 17%) 정지 (**스냅이 있었다면 y가
    구역 top 20.2% 안으로 끌려갔을 좌표**), "지정한 위치로/에 …" 토스트, 모달 없음
  - 800 문학 서가 클릭 → 마커 정확히 고정 정차점 (18.6%, 57%),
    "800 문학 서가로 …" 시작 토스트 → 도착 시 "3구역에 도착했어요!" 구역 정리 모달
  - 사서/반납 테이블은 직전 로그에서 검증(도착 토스트, 모달 없음) — 동작 유지
- **삽질 기록**: 가짜 Jetson을 FE 브랜치 체크아웃 상태에서 `scripts/fake_jetson.py`로 실행하면
  파일이 없다(BE 브랜치에만 커밋됨) — `git show`로 꺼내 임시 경로에서 실행

## 2026-08-07 15:25 — ✅ BE: status/nav-result 상행 수신 + E2E 재검증 (Claude)

- **배경**: EM이 ROS2 `/cart/nav_status`(ROS2-16, 7종)를 MQTT `status/nav-result`로 중계해주기로
  확정(2026-08-07). 직전 E2E에서 확인된 공백 — BE가 ARRIVED를 못 보내 도착 안내가 안 뜨고
  `carts.operation_status`가 NAVIGATING에 남던 문제 — 을 메우는 수신부 구현
- **변경**:
  - `MqttNavResultMessageHandler` 신규 — `{"status":"..."}` JSON과 평문 문자열(std_msgs/String
    브리지 대비) 모두 수용, `mqtt.cart-id`로 귀속 (기존 수신 4종과 같은 단일 카트 제약)
  - `NavigationService.applyCartNavResult` — NAVIGATING→WS STARTED / SUCCEEDED→ARRIVED /
    CANCELED→CANCELLED / ABORTED·REJECTED·NAV2_UNAVAILABLE→FAILED(+failReason) / IDLE·미지의 값 무시.
    종료 상태는 세션을 닫고 카트를 IDLE로. **세션이 없으면 이벤트 없이 DB 정리만** —
    REST 취소 직후 카트의 CANCELED 확인 응답이 중복 CANCELLED를 만들지 않게
  - `mqtt.nav-result-topic=status/nav-result` 프로퍼티 + MqttConfig 구독·라우팅
  - `scripts/fake_jetson.py` — MOVE 수락 시 NAVIGATING, 도착 시 SUCCEEDED, 취소 시 CANCELED,
    target 없는 MOVE엔 REJECTED 발행
- **명령·결과**: `gradlew.bat test` → **BUILD SUCCESSFUL, 96 tests 0 failures**
  (신규 4: SUCCEEDED 종결·세션 재사용 / ABORTED 사유 / 세션 없는 CANCELED 무이벤트 정리 / IDLE·미지 값 무시)
- **E2E 재검증** (BE·가짜 Jetson 재기동, FE 8081 실연동):
  - 2구역 클릭 → 마커 점진 이동(80%→68.9→56.9→49.5% 정지) → 토스트 "2구역으로 …" →
    **도착 모달 "2구역에 도착했어요!"** — 직전 로그에서 "안 뜬다"던 공백이 실경로로 메워짐
  - 반납 테이블 클릭 → "반납 테이블로 …" → **"반납 테이블에 도착했어요" 토스트만** (모달 없음),
    마커 정확히 (93.7%, 23%) 정지
  - BE 로그: `[MQTT RECEIVE] topic=status/nav-result {"status":"NAVIGATING"}` → "카트 주행 시작" /
    `{"status":"SUCCEEDED"}` → "카트 주행 종료 status=ARRIVED" (navigationId 1·2 모두)

<details>
<summary>BE 로그 발췌</summary>

```text
이동 명령 접수 cartId=1, navigationId=2, zoneId=1, pixel=(937.0, 138.0), target=Target[x=9.37, y=4.62]
[MQTT RECEIVE] topic=status/nav-result, payload={"status": "NAVIGATING", ...}
카트 주행 시작 cartId=1, navigationId=2
[MQTT RECEIVE] topic=status/nav-result, payload={"status": "SUCCEEDED", ...}
카트 주행 종료 cartId=1, navigationId=2, status=ARRIVED, failReason=null
```

</details>

## 2026-08-07 15:00 — ✅ E2E: FE→BE→MQTT→가짜 Jetson 왕복 실구동 (Claude)

- **목적**: 실물 카트 없이 전체 사슬 검증 — FE 클릭이 MQTT 명령으로 하행하고,
  Jetson(SLAM)의 미터 좌표 위치가 BE에서 png 픽셀로 변환돼 FE 마커를 움직이는지.
  **FE 마커는 낙관 이동 없이 수신 위치만 따라가야 한다**
- **구성** (모두 로컬):
  - MySQL `chollae`에 [test-room-3zones.sql](../backend/src/main/resources/db/test-room-3zones.sql)
    적용 → Z1(id 1)·Z2(id 3)·Z3(id 4), 지도 meta 1000×600·resolution 0.01·origin (0,0)
  - `scripts/fake_jetson.py` 신규 — cmd/move/cart 구독, status/cart 하트비트 5초,
    status/position **SLAM 미터** 발행(이동 5Hz/정지 1Hz), MOVE target으로 0.5m/s 등속 이동
  - BE `bootRun` — 환경변수로 로컬 브로커·`MQTT_POSITION_UNIT=meters` 오버라이드
    (backend/.env은 원격 브로커·옛 토픽명이라 손대지 않음)
  - FE dev 8081, `VITE_ENABLE_MSW=false` (vite proxy → :8080)
- **관측된 사슬** (사서 테이블 클릭 1회):
  1. FE → `POST /navigation {"zoneId":4,"x":225,"y":138}` (Z3 + 고정 정차점)
  2. BE → `cmd/move/cart {"requestId":1,"command":"MOVE","zoneId":4,"target":{"x":2.25,"y":4.62},"pixel":{"x":225.0,"y":138.0}}`
     — 픽셀→미터 역변환 정확 (225×0.01 / (600−138)×0.01)
  3. 가짜 Jetson: target까지 등속 이동하며 미터 좌표 발행
  4. BE: `raw=(2.25, 4.62) → image=(225.00, 138.00), detectedZoneId=4, stable=true` — 미터→픽셀
     복원과 구역 판정(Z3) 모두 정확
  5. FE 마커: 80% → 72.05 → 64.95 → 59.95 → 49.81 → 39.74 → 29.68 → **22.5% 정지** (1초 간격 샘플)
     — 클릭 시점에 점프하지 않고 WS 위치 스트림만 따라 점진 이동, 시작 토스트
     "사서 테이블로 카트가 이동을 시작해요" 확인
- **확인된 공백 (실 BE 경로)**: BE가 `NAVIGATION_STATUS_UPDATED`를 ACCEPTED/CANCELLED만 발행
  (STARTED/ARRIVED는 카트 상행 결과 토픽 미확정) → 도착 토스트·도착 모달이 실서버에서는 뜨지 않고,
  DB `carts.operation_status`도 NAVIGATING에 머문다. FE는 30초 워치독이 상태를 리셋.
  → EM과 상행 결과 토픽(예: status/nav-result) 확정이 다음 과제

<details>
<summary>실측 로그 발췌</summary>

```text
# 가짜 Jetson
명령 수신 cmd/move/cart: {"requestId": 1, "command": "MOVE", "zoneId": 4,
  "target": {"x": 2.25, "y": 4.62}, "pixel": {"x": 225.0, "y": 138.0}}
이동 시작 → SLAM(2.250, 4.620)
위치 발행 {'x': 7.501, 'y': 4.894, ...} ... 도착 x=2.250 y=4.620

# BE
카트 위치 수신 cartId=1, raw=(8.0, 4.92), image=(800.00, 108.00), unit=meters, detectedZoneId=null
카트 위치 수신 cartId=1, raw=(2.25, 4.62), image=(225.00, 138.00), unit=meters, detectedZoneId=4, stable=true

# FE 마커 샘플 (1초 간격, style.left)
80% → 72.05% → 64.95% → 59.95% → 49.81% → 39.74% → 29.68% → 22.5% (이후 고정)
```

</details>

## 2026-08-07 15:05 — ✅ FE: 테이블행 이동의 안내 문구 분리 (Claude)

- **배경**: 사서/반납 테이블 버튼을 눌러도 안내가 "1구역으로 이동을 시작해요 → 1구역에 도착했어요
  (꽂을 책 0권)"로 나왔다. NAV-01·WS-FE-06에는 구역 id만 있어 BE는 테이블행임을 모른다 — FE가 기억해야 한다
- **변경**:
  - `cartMapStore.landmarkDestination` 신규 — `startMove('반납 테이블')`로 기록, 이동 종료
    (ARRIVED·CANCELLED·FAILED·워치독)마다 소거. **테이블행 도착은 구역 정리 모달(arrivalZone)을
    열지 않는다** (테이블에는 꽂을 책이 없어 "0권" 모달이 소음)
  - `useCartMapEvents`: ARRIVED 수신 시 landmarkDestination이 있으면 `"○○에 도착했어요"` 토스트
    (applyNavigation이 값을 지우기 전에 읽는다)
  - `MapPanel`: 테이블 클릭 시 시작 토스트를 `"○○로 카트가 이동을 시작해요"`로. 요청-응답 사이
    이름 전달은 ref (리렌더가 필요 없는 값)
- **명령·결과**: `pnpm test --run` → **20 files, 137 tests, 0 failures** (신규 3: 테이블행 도착이
  모달을 안 여는 것 / 취소 후 구역 이동은 다시 여는 것 / 워치독 소거) / `tsc` 0 / `eslint` 0
- **브라우저 검증** (dev 8081, MSW on, MutationObserver로 토스트 수집):
  사서 테이블 클릭 → `"사서 테이블로 카트가 이동을 시작해요"` → `"사서 테이블에 도착했어요"`,
  ARRIVAL NOTICE 모달 미표시 확인. 구역(통로) 클릭은 기존대로 "N구역…" 안내 유지

<details>
<summary>브라우저 관찰 원본</summary>

```json
{
 "toasts": [
  "반납 테이블에 도착했어요",
  "사서 테이블로 카트가 이동을 시작해요",
  "사서 테이블에 도착했어요"
 ],
 "zoneModalOpen": false
}
```

(첫 줄 "반납 테이블에…"은 같은 시각 사람이 직접 누른 클릭의 도착 토스트)

</details>

## 2026-08-07 14:20 — ✅ FE: 새 평면도(1000×600) 좌표 실측 교정 + 브라우저 검증 (Claude)

- **배경**: 사람이 `assets/map.png`를 1000×600 신판으로 교체. 어제 눈짐작으로 넣은 좌표를
  실측으로 교정하고 브라우저에서 동작 확인
- **측정 방법**: dev 서버(MSW on)에서 지도 페이지의 `<img>`를 canvas에 그려 **1px 픽셀 스캔** —
  색 분류(청록=통로, 노랑·주황=테이블, 진회색=서가)로 각 영역의 정확한 바운딩 박스를 얻음
- **교정** (0.1~0.5% 오차):
  - `ZONE_RECTS`: Z1 left 75.6→75.5, Z2 39.0→38.9, Z3 2.5→2.4, top 20.3→20.2, height 74.2→73.8
  - `MAP_LANDMARKS`: 사서 width 25.8→25.7, 반납 left 87.5→87.4·width 12.5→12.6
  - SQL 폴리곤: 실측 픽셀 [755·389·24, 121~564]로, 책장 y 343→342
- **오버레이 정합 검증** (버튼 rect 내부 픽셀 중 기대 색 비율): Z1~Z3 **99.1~99.2%**,
  사서 테이블 96%, 반납 테이블 91.4% (모서리 라운딩·글자 픽셀 제외하면 사실상 전면 일치, ≤1px)
- **기능 검증** (XHR 후킹으로 NAV-01 페이로드 확인):
  - 사서 테이블 클릭 → `{"zoneId":3,"x":225,"y":138}` = Z3 + 고정 정차점 (22.5%, 23%) ✓
  - 반납 테이블 클릭 → `{"zoneId":1,"x":937,"y":138}` = Z1 + 고정 정차점 (93.7%, 23%) ✓
  - 화면: "3구역에 도착했어요"(800번대 책 2권 표시) / "1구역에 도착했어요" + 카트 마커가
    반납 테이블 바로 아래 정차, Z1 활성 테두리 (스크린샷은 세션 대화에 있음)
- **단위 테스트 재실행**: `pnpm test --run` → **20 files, 134 tests, 0 failures**
- 검증용으로 잠깐 켠 `.env.development.local`의 `VITE_ENABLE_MSW`는 false로 원복

<details>
<summary>실측 원본 (canvas 1px 스캔, % = px/10 · px/6)</summary>

```json
{"Z3":{"px":[24,121,236,564],"pct":[2.4,20.2,23.6,94]},
 "Z2":{"px":[389,121,601,564],"pct":[38.9,20.2,60.1,94]},
 "Z1":{"px":[755,121,967,564],"pct":[75.5,20.2,96.7,94]},
 "shelves_800_200":{"px":[249,231,375,453]},
 "shelves_100_000":{"px":[615,231,741,453]},
 "librarian":{"px":[0,0,257,90],"pct":[0,0,25.7,15]},
 "return":{"px":[874,0,999,90],"pct":[87.4,0,99.9,15]}}
```

NAV-01 실측 페이로드:

```json
[{"method":"POST","url":"/api/carts/1/navigation","body":{"zoneId":3,"x":225,"y":138}},
 {"method":"POST","url":"/api/carts/1/navigation","body":{"zoneId":1,"x":937,"y":138}}]
```

</details>

## 2026-08-07 13:45 — ✅ FE+BE: 테이블 고정 정차점 + 평면도 1000×600 교체 (Claude)

- **변경** (`backend/feature/navigation-goal-snap` 이어서):
  - 스냅 여유 기본값 0.3 → **0.5 m** (사람이 정한 값)
  - `zones.ts`: 새 평면도(1000×600) 기준으로 `ZONE_RECTS`·`CORRIDOR_Y`·`START_POSITION` 재측정,
    `MAP_LANDMARKS` 신규 — 사서/반납 테이블의 클릭 영역 + 고정 정차점
  - `MapPanel`: 테이블 버튼 2개 (클릭 지점이 아니라 `landmark.stop`을 보낸다)
  - `floorPlanImage.ts` `FLOOR_PLAN_SIZE` 1707×921 → 1000×600, scss `aspect-ratio` 동반 수정
  - `test-room-3zones.sql`: 존 폴리곤·책장 좌표를 평면도 격자에서 측정해 채움
- **정차점 불변식**: 정차점이 구역 밖이면 BE `snapIntoZone`이 조용히 옮겨버리므로,
  "정차점은 반드시 어느 `ZONE_RECTS` 안"을 단위 테스트로 고정했다 (`zones.test.ts`)
- **명령·결과**:
  - `frontend: pnpm test --run` → **20 files, 134 tests, 0 failures** (신규 5)
  - `frontend: tsc --noEmit` 0 / `eslint` 0
  - `backend: gradlew.bat test` → **24 classes, 92 tests, 0 failures**
    (스냅 여유 0.5m 반영: 기대값 6.0px → 10.0px)
- **⚠️ 브라우저 확인은 못 했다.** `frontend/src/assets/map.png`가 아직 옛 그림(1707×921)이다.
  새 1000×600 파일로 교체하기 전 스크린샷은 클릭 영역이 어긋난 모습이라 검증 가치가 없다 —
  파일 교체 후 지도 화면에서 테이블 버튼 위치와 정차 지점을 눈으로 확인해야 한다

<details>
<summary>전체 출력</summary>

```text
$ pnpm test --run
 Test Files  20 passed (20)
      Tests  134 passed (134)
   Duration  28.22s

$ pnpm exec tsc --noEmit
(출력 없음)

$ pnpm lint
> eslint .
(출력 없음)

$ gradlew.bat test
BUILD SUCCESSFUL in 30s

$ awk 집계 (build/test-results/test/*.xml)
classes=24 tests=92 skipped=0 failures=0 errors=0
```

</details>

## 2026-08-07 12:14 — ✅ BE: 구역 밖 클릭 목적지 스냅 (Claude)

- **배경**: FE가 지도 전체 자유 클릭으로 바뀌면서(`897a9b6`) 서가·테이블 위 좌표도 목적지로
  올라온다. `MapPanel.tsx:90` 주석은 "BE가 가장 가까운 이동 가능 지점으로 스냅한다"고 적었지만
  **BE에 그 로직이 없었다** — 장애물 안이 그대로 nav goal로 하행되던 상태
- **변경** (`backend/feature/navigation-goal-snap`, 베이스 `d8f4deb`):
  - `PolygonZoneMatcher.closestPointInside(polygonJson, x, y, margin)` 신규 — 폴리곤 안이면
    그대로, 밖이면 경계 최근접점을 구해 중심 쪽으로 margin만큼 당긴다. 오목 폴리곤에서 당긴 점이
    다시 밖으로 나가면 중심으로 폴백. 폴리곤 파싱을 `vertices()`로 모으고 null·빈 문자열·깨진
    꼭짓점을 예외 대신 빈 목록으로 다루도록 정리(기존 `contains`는 꼭짓점이 깨지면 예외를 던졌다)
  - `NavigationService.snapIntoZone` — 클릭 좌표를 **요청에 실린 구역** 안으로 스냅.
    다른 구역으로 튀지 않게 한 이유: FE가 이미 가장 가까운 구역을 zoneId로 보내고 그 이름으로
    사서에게 안내하므로 목적지가 다른 구역이면 안내와 어긋난다
  - 여유는 `navigation.snap-margin-meters`(기본 0.3) → 구역이 속한 지도의 resolution으로 픽셀 환산
  - 하행 픽셀을 소수 2자리로 정리 — `0.3 / 0.05 = 5.999999999999999`가 MQTT에 실리던 것
- **명령**: `backend/gradlew.bat test`
- **환경**: Windows 11, Microsoft OpenJDK 21, Gradle 9.5.1
- **결과**: **24 classes, 92 tests, 0 failures** (신규 8: 폴리곤 스냅 5 + NAV 스냅 3)
- **1차 실패 → 수정**: `snapsClickOutsideZoneToNearestPointInsideZone`가
  `pixel=Pixel[x=5.999999999999999, y=50.0]`로 실패. 테스트를 느슨하게 고치는 대신 하행 값
  자체를 픽셀 2자리로 반올림(`roundPixel`) — EM이 읽는 페이로드에 부동소수점 노이즈를 남기지 않는다

<details>
<summary>1차 실패 출력</summary>

```text
NavigationServiceTest > snapsClickOutsideZoneToNearestPointInsideZone() FAILED
    java.lang.AssertionError at NavigationServiceTest.java:186

Expecting actual:
  "MoveCommand[requestId=1, command=MOVE, zoneId=7, target=null, pixel=Pixel[x=5.999999999999999, y=50.0]]"
to contain:
  "pixel=Pixel[x=6.0, y=50.0]"

37 tests completed, 1 failed
BUILD FAILED in 59s
```

</details>

<details>
<summary>수정 후 전체 출력</summary>

```text
> Task :compileJava
> Task :processResources
> Task :classes
> Task :compileTestJava
> Task :testClasses
> Task :test

BUILD SUCCESSFUL in 46s
4 actionable tasks: 4 executed

$ awk 집계 (build/test-results/test/*.xml, 24 files)
tests=92 skipped=0 failures=0 errors=0
```

</details>

## 2026-08-07 00:24 — ✅ FE: 슬롯 만적 알림 팝업 추가 (Claude)

- **배경**: 시연 카트는 RFID 리더가 5개만 달려 실물 슬롯이 5칸이다. 다 차면 사서에게
  "북카트를 정리해달라"고 알려줄 화면이 없었다
- **변경** (`frontend/feat/map`, 베이스 `494b8ec`):
  - `PHYSICAL_SLOT_COUNT = 5` (shared/config/cart.ts) — DB 슬롯 12개 중 리더가 달린 범위
  - `slotCapacity.ts` 신규: `physicalSlots`·`isCartFull`. EMPTY가 아니면 찬 것으로 센다
    (RECOGNIZING·RECOGNITION_FAILED도 책이 물리적으로 올라가 있어 더 담을 수 없다).
    실물 슬롯을 다 받지 못한 부분 응답은 만적으로 보지 않는다
  - `SlotFullModal` 신규 + AppLayout에 마운트 — 슬롯 목록은 WS SLOT_UPDATED로 갱신되는
    쿼리 캐시에서 오므로 마지막 책이 얹히는 순간 열리고 한 권 꺼내면 닫힌다
- **막혔던 것 2가지**:
  1. `react-hooks/set-state-in-effect` — "자리가 생기면 닫음 표시 리셋"을 useEffect + setState로
     짰다가 린트에서 걸렸다. 조건이 풀리면 안쪽 컴포넌트가 **언마운트되며 상태가 버려지는**
     구조로 바꿔 해결 (ArrivalModal과 같은 방식, 이펙트 0개)
  2. 테스트에서 `setQueryData` 후 리렌더가 안 일어남 — TanStack v5가 구독자 알림을
     `setTimeout(0)`으로 미루기 때문. 관찰용 컴포넌트로 "캐시는 바뀌었는데 렌더 값은 그대로"인
     것을 확인한 뒤, act 안에서 매크로태스크까지 흘려보내 해결 (`await`만으로는 부족)
- **결과**: **21 files, 129 tests, 0 failures** (신규 12: 만적 판정 8 + 팝업 6 중 일부) /
  `tsc --noEmit` 0 / `eslint` 0
- **스크린샷** (Playwright + 실행 중 dev 서버 5173, MSW on — 데스크톱/근접/모바일/이동 후 4장):
  `01-slot-full-desktop.png` · `02-slot-full-closeup.png` · `03-after-confirm-slots.png` ·
  `04-slot-full-mobile.png`
- **알아둘 것**: MSW 픽스처의 1~5번 슬롯이 모두 OCCUPIED라 모킹 모드에서 앱을 열면 팝업이
  바로 뜬다. 픽스처 데이터를 정확히 렌더한 결과이지만, 개발 중 거슬리면 픽스처를 실물 5칸
  기준으로 손보는 별도 작업이 필요하다

## 2026-08-07 00:00 — ✅ FE: 구역 진입 토스트 제거 (Claude)

- **배경**: "카트가 N구역에 진입했어요" 토스트는 구역 단위라 정보가 거칠고, 지도의 구역
  하이라이트·홈/지도의 현재 위치 카드가 같은 사실을 이미 보여준다. 기획상 원했던 것은
  **책장 단위 근접 안내**인데 그건 미구현(책장 좌표를 주는 BE 엔드포인트가 없다)
- **변경** (`frontend/feat/map`, 베이스 `7d9fd10`): `useCartMapEvents`의 토스트 2곳 제거.
  이 토스트만을 위해 존재했던 반환값도 함께 정리 — `applyPosition`은 `PositionApplied`
  객체 대신 `moved` 불리언만, `applyZone`은 `void`. 안 쓰이게 된 `zoneLabel` import 제거
- **남긴 것**: 이동 명령 접수 토스트("N구역으로 카트가 이동을 시작해요")와 도착 모달 —
  사서가 누른 행동에 대한 응답이라 성격이 다르다
- **결과**: **19 files, 115 tests, 0 failures** / `tsc --noEmit` 0 / `eslint` 0
- **브라우저 확인** (dev + MSW): 3구역으로 이동 → 진입 토스트 없음, 구역 하이라이트는 정상.
  `toastsSeen: ["3구역으로 카트가 이동을 시작해요", "3구역에 도착했어요!"]` — 진입 토스트만 사라짐

## 2026-08-06 23:33 — ✅ FE: 지도 바탕을 번들 평면도로 교체 + 클릭 좌표 전송 검증 (Claude)

- **배경**: BE가 주는 SLAM 지도 그림(`MapInfo.imageUrl` = `/maps/test-room.png`)은 (a) 저장소·
  배포본 어디에도 파일이 없어 nginx/vite가 `index.html`을 200으로 돌려주고 `<img>` 디코드가 실패,
  (b) 점유격자 렌더 자체가 사서가 읽기 어려운 그림. FE가 그린 평면도(`assets/map.png`,
  1707×921, 3통로)로 바탕을 바꾸고 구역 기하도 그 그림 기준으로 다시 잡음
- **변경** (작업 트리, 브랜치 미분기 — `develop` 위에서 검증):
  - `floorPlanImage.ts` 신규 (번들 그림 + 원본 크기 + "같은 바닥 범위" 전제 문서화)
  - `zones.ts` 구역 기하 재작성 (7구역 2행 → 3통로), `zoneStore.ts`는 서버 구역을 **코드로 조인해
    id만** 채움 (`applyServerZones`) — 위치·이름은 평면도가 정본
  - `shelfZoneBoundary.ts`(+테스트) 삭제 — 서버 폴리곤을 그림 좌표로 쓰던 경로 제거
  - `MapPanel.tsx`: 좌표 기준 사각형을 테두리 있는 `.canvas` → `<img>` 로 교정 (1px 테두리 때문에
    클릭 기준 박스가 그림보다 2px 컸음, 구역 버튼 %는 패딩 박스 기준이라 서로 어긋났다)
- **좌표 계약은 그대로**: NAV-01 `x`·`y`와 WS 위치는 여전히 BE 지도 이미지 픽셀
- **결과**: **19 files, 115 tests, 0 failures** / `tsc --noEmit` 0 / `eslint` 0
  (`prettier --check`는 `src/pages/search/SearchPage.tsx` 1건 경고 — 이번 변경과 무관한 기존 이슈)
- **명령**: `pnpm --dir frontend test` · `npx tsc --noEmit` · `npx eslint .`
- **브라우저 검증** (dev 서버 + MSW, DOM/네트워크 계측 — Browser 패널 미표시로 스크린샷 불가):
  그림 로드·비율 일치, 구역 버튼 3개가 측정 좌표대로 배치, 통로 클릭 → NAV-01 본문이 기대 픽셀과
  정확히 일치, 서가·테이블 클릭 → 요청 없이 안내 토스트

<details>
<summary>원본 출력 (vitest 집계 + 브라우저 계측)</summary>

```
$ npx vitest run
 Test Files  19 passed (19)
      Tests  115 passed (115)
   Duration  6.32s

$ npx tsc --noEmit        # 출력 없음 (exit 0)
$ npx eslint .            # 출력 없음 (exit 0)

# 브라우저 계측 1 — 그림·구역 배치 (http://localhost:5173/map, MSW on)
{
  "imageSrc": "/src/assets/map.png", "imageLoaded": true, "naturalSize": "1707x921",
  "canvasAspect": 1.8535, "imageAspect": 1.8534,
  "zones": [
    { "label": "1구역 총류로 카트 이동",        "left": 70,  "top": 20.6, "width": 16.1, "height": 73.4 },
    { "label": "2구역 철학·사회과학로 카트 이동", "left": 37,  "top": 20.6, "width": 17,   "height": 73.4 },
    { "label": "3구역 문학·역사로 카트 이동",    "left": 4.2, "top": 20.6, "width": 16.8, "height": 73.4 }
  ],
  "cartCenterPct": { "x": 92.9, "y": 16.2 }     # START_POSITION(93, 16)
}

# 브라우저 계측 2 — 테두리 교정 전: 클릭 기준 박스가 그림보다 2px 큼
{ "canvasRect": { "left": 308, "top": 182, "w": 647, "h": 349.08 },
  "imageRect":  { "left": 309, "top": 183, "w": 645, "h": 347.08 },
  "borderWidth": "1px / 1px" }

# 브라우저 계측 3 — 교정 후: 클릭 지점 → NAV-01 본문이 기대 픽셀과 일치
{ "imageRect": { "left": 309, "top": 187.5, "w": 645, "h": 347.08 },
  "expected": { "x": 741, "y": 665 },
  "sent": ["{\"zoneId\":2,\"x\":741,\"y\":665}"] }

# 브라우저 계측 4 — 통로 밖(서가) 클릭
{ "navRequestsSent": [], "toastLike": ["카트가 갈 수 있는 통로를 눌러주세요", ...] }
```

</details>

## 2026-08-04 09:55 — ✅ BE: TRACKS_UPDATED 중계를 영상 시청자 있을 때만으로 게이트 (Claude)

- **배경**: AI가 status/target을 5Hz 상시 발행 → BE가 무조건 WS 중계 → FE 콘솔에
  TRACKS_UPDATED 스팸 (선택 모달 밖에서도). FE는 선택 모달을 열 때만 영상 WS 시청자로
  붙으므로(명세 그대로), **시청자 존재 여부를 게이트**로 사용 — FE 수정 불필요
- **변경** (브랜치 `backend/feature/tracks-relay-gating`):
  - `VideoRelayHandler.hasViewers(cartId)` 신규
  - `MqttTracksMessageHandler`: 시청자 없으면 파싱 전에 조기 리턴 (중계·로그 없음)
- **결과**: 23 suites, **82 tests, 0 failures** (신규 1: 시청자 없으면 미중계.
  기존 4개는 시청자 있음 스텁으로 갱신)
- **명령**: `backend/gradlew.bat -p backend test --console=plain`

## 2026-08-04 09:35 — 🐛→✅ 배포 후 실기 연동: 추종 시작 400 원인 분석 + 재시작 잔재 상태 버그 수정 (Claude)

- **증상**: 배포 서버에서 FE 추종 시작 → 사서 선택 시 `POST /follow` 400.
  젯슨 로그엔 영상 WS 502 Bad Gateway 1회.
- **진단** (배포 서버 읽기 전용 프로브):
  - 400 본문 = "목적지 이동 중에는 추종을 시작할 수 없습니다" — 카트 상태 MOVING(=NAVIGATING)
  - `DELETE /navigation`이 204인데 상태가 안 풀림 → **배포 재시작으로 인메모리 이동 세션은
    사라졌는데 DB operationStatus만 NAVIGATING으로 남은 고아 상태** (cancel이 세션 없으면
    상태 청소 없이 무시하는 버그). `POST /navigation`(202, navigationId=1로 재시작 확인) 후
    `DELETE`로 응급 복구 → IDLE 확인
  - 영상 502는 배포 재시작 순간의 일시 현상 — 뷰어 접속 검증 결과 **3초에 33프레임(≈11fps)
    정상 스트리밍**, fe_bridge 자동 재접속 성공. SELECT_TARGET → `/select_target` 변환도 정상
- **수정** (브랜치 `backend/fix/stale-operation-status`):
  - `NavigationService.cancel` / `FollowControlService.stop`: 세션이 없어도 DB 상태가
    NAVIGATING/FOLLOWING이면 IDLE로 청소 (MQTT·WS 발행 없이)
  - `CartOperationStatusReconciler` 신규 (ApplicationRunner): **기동 시** NAVIGATING/FOLLOWING
    잔재를 일괄 IDLE 리셋 — 기동 직후엔 어떤 인메모리 세션도 존재할 수 없으므로 안전
- **결과**: 24 suites, **84 tests, 0 failures** (신규 3: cancel 고아 정리, stop 고아 정리,
  기동 리컨실러)

<details>
<summary>배포 서버 프로브 원본 + gradle 집계</summary>

```
GET /api/carts/1 -> {"status":"MOVING","online":true,...}
POST /follow -> 400 "목적지 이동 중에는 추종을 시작할 수 없습니다..."
DELETE /navigation -> 204 (상태 그대로 MOVING — 버그)
POST /navigation {"zoneId":1} -> 202 {"navigationId":1,...}  # id=1 → 재시작 후 첫 세션
DELETE /navigation -> 204
GET /api/carts/1 -> {"status":"IDLE",...}  # 복구 확인
ws://.../ws/carts/1/video -> frames received in ~3s: 33
```

```
# build/test-results/test/*.xml 집계
suites=24 tests=84 failures=0 errors=0
```

</details>

## 2026-08-03 22:00 — ✅ BE 로컬 E2E: 추종·이동 명령 전 시나리오 통과 (가짜 카트로 실브로커 검증) (Claude)

- **목적**: main 배포 전에 FOLLOW-01/02/04 + MOVE 페이로드 개편을 실제 브로커·WS로 검증
  (Jetson·RPi 부재 — 카트는 파이썬 가짜 카트로 대체)
- **환경**: 로컬 BE(bootRun, localhost:8080) + 로컬 MySQL + **EC2 실브로커**(your-server:1883).
  가짜 카트 = paho-mqtt(하트비트 5초 발행 + `cmd/move/cart` 구독), WS = websocket-client(`/ws/carts/1`)
- **커밋**: develop `3756f6a` (MR 머지 후)
- **결과**: 12 케이스 전부 기대값과 일치
  | 케이스 | 결과 |
  |---|---|
  | 405 프로브 (GET /follow/pause) | ✅ 405 |
  | 가짜 하트비트 → 카트 ONLINE 전환 | ✅ online:true (MQTT→BE→DB) |
  | 추종 시작 | ✅ 202 FOLLOWING + MQTT FOLLOW_START + WS FOLLOWING |
  | 중복 시작 | ✅ 400 "이미 추종 중" (발행 없음) |
  | 일시정지 | ✅ 202 PAUSED + MQTT FOLLOW_PAUSE + WS PAUSED |
  | 일시정지 멱등 | ✅ 202, MQTT 재발행 없음 |
  | 재개 | ✅ 202, 같은 followId로 FOLLOW_START 재발행 |
  | 종료 / 종료 멱등 | ✅ 204 + FOLLOW_STOP + WS STOPPED / 204 발행 없음 |
  | 무세션 일시정지 | ✅ 400 |
  | 이동 중 추종 시작 | ✅ 400 "목적지 이동 중" (취소 후 재시도 가능) |
  | MOVE 페이로드 | ✅ 구역 중심 `pixel:{225,75}` / 클릭 픽셀 `{612.5,431}` 전달, `target:null`(pixels 모드 정상), CANCEL 좌표 null |
  | 하트비트 중단 → 워치독 OFFLINE → 추종 시작 | ✅ ~18초 뒤 OFFLINE + WS CART_CONNECTION_UPDATED, 400 "오프라인" |
- **미검증**: `target` 미터 변환 실값(지도 메타 입력 후), EM·AI의 FOLLOW_*/MOVE 수신(수신측 미구현),
  FE 버튼 통합(BE 로컬 서버 살려둠 — FE dev 서버 붙여서 확인 가능)
- **참고**: EC2 공용 브로커라 가짜 하트비트를 배포 BE도 수신 — 테스트 동안 배포 환경 카트가
  잠시 ONLINE으로 표시됨 (중단 후 15초 뒤 OFFLINE 복귀, 실카트 전원 꺼짐 상태라 무해)

<details>
<summary>REST 응답 · MQTT 수신 · WS 수신 원본</summary>

```
GET  /api/carts/1/follow/pause -> 405 Method Not Allowed
POST /api/carts/1/follow -> 202 {"followId":1,"status":"FOLLOWING"}
POST /api/carts/1/follow -> 400 "이미 추종 중입니다."
POST /api/carts/1/follow/pause -> 202 {"followId":1,"status":"PAUSED"}
POST /api/carts/1/follow/pause -> 202 {"followId":1,"status":"PAUSED"}
POST /api/carts/1/follow -> 202 {"followId":1,"status":"FOLLOWING"}
DELETE /api/carts/1/follow -> 204
DELETE /api/carts/1/follow -> 204
POST /api/carts/1/follow/pause -> 400 "진행 중인 추종이 없어 일시정지할 수 없습니다."
POST /api/carts/1/navigation {"zoneId":1} -> 202 {"navigationId":1,"status":"ACCEPTED",...}
POST /api/carts/1/follow -> 400 "목적지 이동 중에는 추종을 시작할 수 없습니다..."
DELETE /api/carts/1/navigation -> 204
POST /api/carts/1/navigation {"zoneId":1,"x":612.5,"y":431.0} -> 202
DELETE /api/carts/1/navigation -> 204
(하트비트 중단, 워치독 전환 후)
POST /api/carts/1/follow -> 400 "카트가 오프라인 상태라 추종을 시작할 수 없습니다."
```

```
# cmd/move/cart 수신 (가짜 카트, EC2 브로커 경유)
{"requestId":1,"command":"FOLLOW_START"}
{"requestId":1,"command":"FOLLOW_PAUSE"}
{"requestId":1,"command":"FOLLOW_START"}
{"requestId":1,"command":"FOLLOW_STOP"}
{"requestId":1,"command":"MOVE","zoneId":1,"target":null,"pixel":{"x":225.0,"y":75.0}}
{"requestId":1,"command":"CANCEL","zoneId":1,"target":null,"pixel":null}
{"requestId":2,"command":"MOVE","zoneId":1,"target":null,"pixel":{"x":612.5,"y":431.0}}
{"requestId":2,"command":"CANCEL","zoneId":1,"target":null,"pixel":null}
```

```
# /ws/carts/1 수신
{"type":"FOLLOW_STATUS_UPDATED","payload":{"followId":1,"status":"FOLLOWING","failReason":null}}
{"type":"FOLLOW_STATUS_UPDATED","payload":{"followId":1,"status":"PAUSED","failReason":null}}
{"type":"FOLLOW_STATUS_UPDATED","payload":{"followId":1,"status":"FOLLOWING","failReason":null}}
{"type":"FOLLOW_STATUS_UPDATED","payload":{"followId":1,"status":"STOPPED","failReason":null}}
{"type":"NAVIGATION_STATUS_UPDATED","payload":{"navigationId":1,"status":"ACCEPTED",...}}
{"type":"NAVIGATION_STATUS_UPDATED","payload":{"navigationId":1,"status":"CANCELLED",...}}
{"type":"NAVIGATION_STATUS_UPDATED","payload":{"navigationId":2,"status":"ACCEPTED",...}}
{"type":"NAVIGATION_STATUS_UPDATED","payload":{"navigationId":2,"status":"CANCELLED",...}}
{"type":"CART_CONNECTION_UPDATED","payload":{"online":false,"lastSeenAt":"2026-08-03T21:57:03.29962"}}
```

</details>


## 2026-08-03 21:33 — ✅ BE: MOVE 하행에 SLAM 미터 target 추가 + NAV-01 픽셀 클릭 지원 (Claude)

- **명령**: `backend/gradlew.bat -p backend test --console=plain`
- **환경**: Windows 11, OpenJDK 21. 단위 테스트만 (외부 의존 모킹)
- **커밋**: 브랜치 `backend/feature/follow-control` (d27affe 위에 추가)
- **변경**:
  - `SlamCoordinateConverter.toSlamMeters()` 신규 — 픽셀→미터 역변환 (세로축 뒤집기 포함)
  - `MoveCommand` 페이로드 개편: `{"requestId","command":"MOVE","zoneId","target":{x,y},"pixel":{x,y}}`
    — target은 SLAM 미터(EM nav goal). `mqtt.position-unit=meters`일 때만 변환·포함,
    pixels 모드(지도 메타 미입력)에선 null. pixel은 항상 포함(참고용)
  - NAV-01 요청에 선택 필드 x·y(지도 픽셀) 추가 — 주면 클릭 지점, 없으면 구역 bbox 중심 (기존 FE 무영향)
  - FOLLOW_* 명령은 좌표를 싣지 않기로 확정 — 사서 좌표는 로봇 내부에서 AI `/target_position`이
    데이터 플레인 (BE 경유 왕복은 지연만 추가)
- **결과**: 23 suites, **81 tests, 0 failures, 0 errors** (신규 4: 픽셀→미터 변환/왕복,
  meters 모드 target 포함, 클릭 픽셀 우선. 기존 MOVE 테스트는 target=null(pixels 모드) 검증으로 갱신)
- **미검증**: 실지도 메타 기반 변환 정확도 — EM이 map.yaml 값(`library_maps` id=2) 입력 후
  실기 좌표로 재검증 필요

<details>
<summary>gradle test 출력 + JUnit XML 집계</summary>

```
> Task :compileJava
> Task :classes
> Task :compileTestJava
> Task :testClasses
> Task :test

BUILD SUCCESSFUL in 32s
```

```
# build/test-results/test/*.xml 집계
suites=23 tests=81 failures=0 errors=0
```

</details>

## 2026-08-03 20:22 — ✅ BE: 추종 시작·일시정지·종료(FOLLOW-01/02/04) 단위 테스트 통과 (Claude)

- **명령**: `backend/gradlew.bat test --console=plain` (backend/ 에서)
- **환경**: Windows 11, OpenJDK 21. 브로커·DB 실연동 없이 단위 테스트만 (외부 의존 Mockito 모킹)
- **커밋**: develop `4751ba4` 기준 — 브랜치 `backend/feature/follow-control`
- **신규 기능**: FE가 완료해 둔 추종 제어 3종의 BE 구현
  - `FollowControlService` 신규 — `POST /follow`(FOLLOW-04, 202)·`POST /follow/pause`(FOLLOW-01, 202)·
    `DELETE /follow`(FOLLOW-02, 204·멱등). NavigationService 패턴 준용 (인메모리 세션, 카트당 1건)
  - MQTT `cmd/move/cart`로 `{"requestId","command":"FOLLOW_START|FOLLOW_PAUSE|FOLLOW_STOP"}` 하행
    — ⚠️ **EM·AI 수신측 미구현, 임시 계약** (API 명세서 MQTT-04 데이터란에 반영)
  - WS `FOLLOW_STATUS_UPDATED`(WS-FE-07) 발행 — FOLLOWING/PAUSED/STOPPED (REST 접수 기준.
    대상 인식 여부·거리·대상 상실은 카트 상행 결과 토픽 확정 후)
  - 가드: 오프라인 400, NAVIGATING 중 시작 400, 중복 시작 400. 일시정지 재시작은 같은 followId 재개.
    일시정지 중 카트 동작 상태는 FOLLOWING 유지, 종료 시 IDLE 복귀
- **결과**: 23 suites, **77 tests, 0 failures, 0 errors** (신규 11: FollowControlServiceTest —
  시작/오프라인 거부/이동 중 거부/중복 거부/재개/일시정지/일시정지 멱등/무세션 일시정지 거부/종료/종료 멱등/MQTT 부재)
- **미검증**: 브로커 실연동, EM·AI의 FOLLOW_* 명령 수신 (수신측 코드 자체가 아직 없음)

<details>
<summary>gradle test 출력 + JUnit XML 집계</summary>

```
> Task :compileJava
> Task :processResources UP-TO-DATE
> Task :classes
> Task :compileTestJava
> Task :testClasses
> Task :test

BUILD SUCCESSFUL in 33s
```

```
# build/test-results/test/*.xml 집계
suites=23 tests=77 failures=0 errors=0
```

</details>

## 2026-08-03 16:05 — ✅ main 승격 리허설: 로컬 가상 머지 + Jenkins Test 단계 재현 통과 (Claude)

- **목적**: develop(+슬롯 LED 브랜치)을 main에 머지·배포했을 때 파이프라인이 깨지는지 사전 확인
- **방법**: 임시 worktree에서 `origin/main`(c9b54d6) ← `backend/feature/slot-led-command`(d7d795f,
  develop 1fb0dba 포함) 가상 머지 → Jenkinsfile Backend Test 단계와 동일 조건으로 테스트
  (`MQTT_ENABLED=false`, `WS_POSITION_TEST_ENABLED=false`, DB 자격증명만 주입)
- **결과**:
  - 가상 머지: **충돌 없음 (clean merge)**
  - BE: `gradlew test` BUILD SUCCESSFUL — **22 suites, 66 tests, 0 failures** (contextLoads 포함)
  - AI: `pytest ai/test/` **114 passed**
  - FE: main 대비 `frontend/` **변경 0** — 지난 성공 배포와 동일 소스로 이미지 빌드
  - 이미지 빌드 단계(docker build)는 로컬에 docker가 없어 미검증 — BE는 컴파일 검증됨, FE는 무변경이라 잔여 위험 낮음
- **⚠️ 파이프라인은 통과해도, 배포 직후 카트 연동이 끊긴다 (코드가 아니라 운영 이슈)**:
  1. **RPi 실카트가 아직 옛 토픽 발행** (`choll/cart/rfid`, `carts/status`) — 새 BE는 `status/slot`·
     `status/cart` 구독이라 하트비트 15초 뒤 카트 OFFLINE, RFID 이벤트 유실. **RPi 반영과 동시 배포 필수.**
  2. **Jenkins 시크릿 `choll-app-env`가 compose `env_file`로 통째 주입됨** — 그 안에
     `MQTT_POSITION_TOPIC=carts/+/telemetry/position` 같은 옛 값이 남아 있으면 새 코드 기본값을
     **덮어써서 토픽 개편이 서버에서 무효화**된다 (과거 MQTT_POSITION_TEST.md가 .env에 넣도록 안내했었음).
     → main 머지 전 시크릿 파일에서 `MQTT_*_TOPIC` 라인 제거 또는 신값 갱신 필수.
  3. Jetson도 pull + colcon 재빌드 전까지 옛 `choll/cart/tracks` 발행 → TRACKS_UPDATED·타겟 선택 단절.
- **배포 후 확인 절차**: 405 프로브 + `mosquitto_sub -t 'status/#' -v`(EC2 브로커)로 신토픽 수신 확인
- **[추기 16:20] 위 운영 리스크 3종 해소 확인** (사용자 확인, 2026-08-03):
  - ① ③: RPi·Jetson 모두 실기에서 신토픽 코드로 구동 중
  - ②: 배포용 시크릿 .env 내용 확인 — `MQTT_*_TOPIC` 핀 없음 (DB_*, MQTT_ENABLED/BROKER_URL/계정,
    WS_POSITION_TEST_ENABLED뿐) → 코드 기본값이 그대로 적용됨. **수정 불필요, main 머지 가능 상태.**
  - 남은 조건부 1건: EM이 SLAM 미터 좌표 발행을 시작하면 `MQTT_POSITION_UNIT=meters` 추가
    + `library_maps` id=2에 실제 map.yaml 값 입력 (그 전까지 기본 pixels가 맞음)

- **명령**: `backend/gradlew.bat -p backend test --console=plain`
- **환경**: Windows 11, OpenJDK 21, MySQL(EC2 Docker). 브로커 없이 단위 테스트만
- **커밋**: `1fb0dba`(develop, MR !58 머지 후) 기준 — 브랜치 `backend/feature/slot-led-command`
- **신규 기능**: 카트의 **구역이 바뀔 때** 그 구역에서 내려놓을 슬롯 번호를 MQTT `cmd/lit/led`로 발행.
  페이로드 `{"slot_id":[1,3,5]}` — 그 시점에 켜져 있어야 할 슬롯 전체 (카트 1대 가정, cartId 없음).
  **BE 범위는 발행까지** — 구독·점등 제어는 라즈베리파이(EM) 몫
  - `SlotLedService` 신규 — 대상 조회 + 발행. MQTT 비활성이면 경고 후 무시
  - `SlotService.findTargetSlotNumbers()` 신규 — 기존 `isTarget`(책의 서가 구역 == 카트 현재 구역) 재사용
  - `CartPositionTelemetryService`에 **구역 전이 감지**(`zoneChanged`) 추가 — 갱신 전
    `cart.getCurrentZone()`과 비교. 같은 구역 유지면 발행하지 않음
  - `MqttCommandPublisher.publishLed()` 추가 — 토픽별 발행을 `publishTo(topic, payload)`로 분리
    (기존 `publish()` 호출처 NavigationService·FollowTargetService는 무영향)
  - 설정: `mqtt.led-topic`(기본 `cmd/lit/led`)
- **발행 규칙** (2026-08-03 협의):
  - 구역 진입/구역 간 이동 → 새 구역의 대상 목록 발행
  - **구역 이탈 → 빈 목록 `[]` 발행(소등)** — 책을 남기고 나가도 LED가 켜진 채 남지 않도록
  - 구역 밖 → 대상 없는 구역: 켤 것도 끌 것도 없어 미발행
  - 책이 빠졌을 때(RFID REMOVED)의 소등은 라즈베리파이 몫 — BE는 재발행하지 않음
- **결과**: 22 suites, **66 tests, 0 failures, 0 errors** (신규 7: SlotLedServiceTest 4 —
  점등/이탈 시 빈 목록/미발행/MQTT 비활성, CartPositionTelemetryServiceTest 3 — 진입/동일 구역 유지/이탈)
- **슬롯 번호 범위**: DB는 1~12번이지만 실물 RFID 리더는 5개만 설치(재정상). RFID 없는 슬롯은
  책이 인식되지 않아 `isTarget`이 될 수 없으므로 `slot_id`에도 나오지 않는다 — 불일치 아님
- **미검증**: 브로커 실연동 미실시. 라즈베리파이 구독·점등부는 EM 담당

<details>
<summary>gradle test 출력 + JUnit XML 집계</summary>

```
BUILD SUCCESSFUL
```

```
# build/test-results/test/*.xml 집계
tests=66 failures=0 errors=0 suites=22
```

</details>

## 2026-08-03 — ⚠️ EM 실기: 엔코더 count/rev 실측 → 감속비 100:1 오기재 정정(51:1), 12.1% 차이 원인 미확정 (relu 실측 / Claude 반영)

- **대상**: `embedded/motor/stm32_workspace/motor-control/Application/Config/motor_config.h`
- **실측자**: relu (출력축 수동 회전, 실기). **STM 펌웨어 재빌드·재플래시는 아직 하지 않았다.**
- **방법**: 바퀴(출력축)를 손으로 정해진 횟수만큼 돌리고 `encoder_total` 누적값 변화를 읽음
  (모터 구동 없음). ROS2 Bridge의 `/stm/encoder_total`로 관측.

### 실측 원본 수치

| 대상 | 구간 | 시작 → 끝 | 변화량 |
|---|---|---|---|
| Left | 1회전 | 136320 → 205017 | 68697 |
| Left | 추가 3회전 | 205071 → 408805 | 203734 |
| Right | 1회전 | 138 → 68603 | 68465 |
| Right | 추가 3회전 | 68931 → 273335 | 204404 |

- Left 4회전 평균: **68107.75** count/rev
- Right 4회전 평균: **68217.25** count/rev
- **좌우 전체 8회전 평균: 68162.5 count/wheel-rev**
- 좌우 차이 약 **0.16%** — 매우 일관적

### 판정 및 코드 변경

구매 사양 확인 결과 감속비 옵션은 **51:1**이었고, 코드에 적혀 있던 **100:1은 오기재**였다.

```
MOTOR_GEAR_RATIO   100.0f → 51.0f          (변경)
MOTOR_ENCODER_CPR                380.0f    (유지)
MOTOR_ENCODER_QUADRATURE_MULTIPLIER 4.0f   (유지)
MOTOR_ENCODER_COUNTS_PER_WHEEL_REV         (파생식 유지: CPR × Gear × Quadrature)
  → 380 × 51 × 4 = 77520 count/wheel-rev  (기존 152000에서 변경)
```

- 명목값 77520 vs 실측 68162.5 → **약 -12.1%** (실측이 더 작음)
- ⚠️ **실측값 68162.5를 별도 상수로 강제 적용하지 않았다.** 파생식을 그대로 유지했다.
- ⚠️ **감속비를 1:45로 확정한 것이 아니다.** 구매 사양은 1:51이다.
  (참고로 380×45×4 = 68400으로 실측과 -0.35%까지 근접하지만, 근거 없이 45로 바꾸지 않았다.)
- ⚠️ **12.1% 차이의 원인은 미확정**이다. 아래 중 어느 것인지 이 데이터만으로 구분할 수 없다:
  CPR 380의 정의(채널당 라인 수 vs 이미 quadrature 적용) / Quadrature 배율(TI12 = x4 가정) /
  타이머 입력 필터(`IC1Filter`/`IC2Filter` = 8)로 인한 edge 누락 / 실제 하드웨어 사양이 구매 사양과 다름.
  실측을 정확히 맞추려면 유효 감속비 약 44.84:1 또는 유효 CPR 약 334.1이 필요하다.

### 영향 범위 (코드 분석 결과)

`MOTOR_ENCODER_COUNTS_PER_WHEEL_REV`는 `motor.c:406-407`
(`Motor_UpdateActualVelocity()`) **한 곳에서만** 쓰이지만, 결과인 `motor_actual_*_rad_s`가
STATUS의 LA/RA, PI 오차 입력(`:450,467,918,951`), Speed Profile(`:425,429`),
Stall 판정(`:508,513`)으로 흘러간다.

- 같은 회전에서 보고되는 `actual_rad_s`가 **약 1.9608배 커진다**
  (실제 대비 2.23배 과소 → 1.14배 과소로 개선, 여전히 약 12% 과소)
- PI 게인이 기본 `0.0f`이므로 **제어 동작 변화는 지금 당장 없다**
- Stall 판정(`|actual| <= 0.1f`)은 actual이 커지므로 **오검출 가능성이 줄어드는 방향**.
  실제 정지 시 actual≈0이므로 검출 능력 자체는 유지

### 검증 결과

- **STM32 펌웨어 빌드: 이 환경에서 수행 불가** — `arm-none-eabi-gcc`가 설치되어 있지 않다.
  **CubeIDE에서 사용자가 빌드·플래시해야 한다.** 문법 검증은 `gcc -fsyntax-only`로만 확인.
- ROS2 Serial Bridge 회귀: `python3 -m pytest src/stm_serial_bridge/test/ -q` → **298 passed**
  (이번 변경은 STM 펌웨어 상수뿐이라 브리지 코드·테스트에 영향 없음)

### 후속 필요 (미완료)

1. **CubeIDE 재빌드 → 재플래시 → `actual_rad_s` 재검증** — 변경이 반영된 펌웨어로 실기 확인이 아직 없다
2. 12.1% 차이의 **원인 규명** (IC Filter 낮춰 재측정 / 모터축 1회전 카운트 측정 / 데이터시트 재확인)
3. 원인 확정 후 해당 매크로 **하나만** 정정
4. ~~`serial_protocol.md`의 하드웨어 상수 표가 아직 옛 값~~ → **같은 날 정정 완료**:
   `MOTOR_GEAR_RATIO` 51, 명목 `COUNTS_PER_WHEEL_REV` 77520, 실측 68162.5·원인 미확정 기록으로
   교체했고, `152000 vs 38000`으로 Quadrature를 판정하던 과거 기준도 폐기했다.
   `ros2_ws/CLAUDE.md`의 "엔코더 1회전당 Count 미측정" 서술도 "실측 완료 / 원인 미확정"으로 분리했다.

### ⚠️ 이 기록의 한계

- 실측 원본 수치는 사용자 보고값이며, **콘솔 원본 출력은 확보되지 않았다**
- 회전 각도 정밀도(손으로 정확히 1회전을 맞췄는지)는 정량화되지 않았다 —
  좌우 0.16% 일관성은 이 오차가 크지 않다는 간접 근거일 뿐이다
- 모터축(감속 전) 카운트는 측정하지 않았으므로 감속비 자체를 독립 검증하지 못했다

## 2026-08-03 14:52 — ✅ MQTT 토픽 개편, develop 리베이스 후 BE 59 tests 통과 (Claude)

- **명령**: `backend/gradlew.bat -p backend test --console=plain`
- **환경**: Windows 11, OpenJDK 21, MySQL(EC2 Docker). 브로커 없이 단위 테스트만
- **커밋**: `d6ab80c`(develop) 위로 리베이스 — 브랜치 `refactor/mqtt-topic-rename`
  (SLAM 미터→픽셀 변환이 먼저 develop에 머지돼 `application.properties`·`backend/CLAUDE.md`·
  이 로그에서 충돌 → 양쪽 다 살려 해결. `mqtt.position-unit`·`mqtt.map-id`는 그대로 두고
  토픽 값만 교체)
- **변경**: MQTT 토픽 전면 개편 (`ai/`·`backend/` 양쪽 동시 적용).
  네이밍 규칙 = **상행(카트·AI→BE) `status/*`, 하행(BE→카트) `cmd/*`** (선행 슬래시 없음)

  | 구 토픽 | 신 토픽 | 방향 |
  |---------|---------|------|
  | `carts/{cartId}/telemetry/position` | `status/position` | 카트→BE |
  | `carts/status` | `status/cart` | 카트→BE (하트비트) |
  | `choll/cart/rfid` | `status/slot` | 카트→BE |
  | `choll/cart/cmd` | `cmd/move/cart` | BE→카트 (MOVE/CANCEL/SELECT_TARGET) |
  | `choll/cart/tracks` | `status/target` | AI→BE (추종 후보 트랙) |

- **구조 변경(주의)**: 새 위치 토픽에 cartId가 없어, `MqttPositionMessageHandler`가
  토픽 정규식(`^carts/(\d+)/telemetry/position$`)에서 cartId를 뽑던 방식을 폐기하고
  하트비트·RFID·tracks와 동일하게 `mqtt.cart-id`(기본 1)로 귀속하도록 변경.
  토픽 검증은 주입된 `mqtt.position-topic`과 정확 비교. **이제 수신 4종 모두 cartId가
  토픽에 없으므로 다중 카트 도입 시 EM과 재협의 필요.**
- **결과**: 21 suites, **59 tests, 0 failures, 0 errors**
  (내 변경으로 늘어난 테스트는 없음 — 토픽 상수만 갱신. 59는 develop의 SLAM 변환 테스트 4개 포함)
- **적용 범위**: `ai/`·`backend/`와 공용 E2E 도구(`tests/tools/fake_jetson.py`의 트랙 발행).
  FE(`frontend/`)·`docs/`에는 MQTT 토픽 문자열이 없어 변경 없음.
  **EM 파트(`embedded/`)는 이 MR에서 제외** — 실카트 코드는 EM 담당자가 별도 반영 예정.
  TEST_LOG의 과거 기록은 실행 증거라 옛 토픽명 그대로 보존.
- **미검증 / ⚠️ 배포 시 주의**: 브로커 실연동 E2E는 돌리지 않음 (단위 테스트만).
  - **EM 반영 전까지 실카트↔BE 통신 단절** — `embedded/rfid/rfid_mqtt.py`가 아직 옛 토픽
    (`choll/cart/rfid`, `carts/status`)으로 발행하므로, BE만 먼저 배포하면 슬롯·하트비트를 못 받는다.
    **BE 배포와 EM 반영은 함께 나가야 한다.**
  - EC2 브로커에 남은 옛 `carts/status` retained LWT도 새 `status/cart`로 자동 이관되지 않음.
- **AI 파트 기록**: [ai/test/TEST_LOG.md](../ai/test/TEST_LOG.md) 2026-08-03 항목

<details>
<summary>gradle test 출력 (마지막 부분) + JUnit XML 집계</summary>

```
BUILD SUCCESSFUL in 19s
```

```
# build/test-results/test/*.xml 집계
tests=59 failures=0 errors=0 suites=21
```

</details>

## 2026-08-03 — ✅ EM+ROS2 실기: STM32 STATUS → Serial Bridge → ROS2 수신 확인 + 좌우 매핑 실측 확정 (relu, 실기)

- **대상 커밋**: `d6bbe29` "[feat] STM STATUS 수신 및 ROS2 상태 토픽 발행" (`em/feature/motor-control`)
- **대상 코드**: `ros2_ws/src/stm_serial_bridge` (STM32 펌웨어는 변경 없음, UART Protocol v1 그대로)
- **환경**: Ubuntu + ROS2 Humble, 실제 STM32 USB Serial 연결, `serial_port=/dev/ttyACM0`, `baud_rate=115200`
- **⚠️ 바퀴를 공중에 띄운 상태에서 진행 — 바닥 주행 아님**
- **`/cmd_vel` 발행 수단**: `ros2 topic pub` (`teleop_twist_keyboard` 미사용 — 키보드 teleop은 여전히 미완료 항목)
- **Bridge 파라미터**: `dry_run=false`, `rx_poll_hz=50.0`, `status_timeout_sec=0.5`,
  `max_wheel_rad_s=2.0`, `tx_rate_hz=20.0`, `cmd_vel_timeout_sec=0.5`,
  `wheel_radius_m=0.065`, `wheel_separation_m=0.30`
- **실행자**: relu (사람이 직접 실기 수행). 이 항목은 사용자 보고를 받아 Claude가 대신 기록함.

### 결과: 수신 경로(STM32 → Bridge → ROS2) 실기 연동 완료

| # | 확인 항목 | 결과 |
|---|---|---|
| 1 | STM STATUS 패킷이 USB Serial로 Bridge에 수신 | ✅ |
| 2 | Bridge 로그의 `STATUS #N` 번호가 계속 증가 | ✅ |
| 3 | `STM → SerialLink → LineDecoder → parse_packet() → Publisher` 전 구간 동작 | ✅ |
| 4 | `/stm/connected` = `true` | ✅ |
| 5 | connected가 **포트 open이 아니라 유효 STATUS 수신** 기준임을 확인 | ✅ |
| 6 | `/stm/fault` 초기값 = `NONE` | ✅ |
| 7 | STATUS 주기 (`ros2 topic hz /stm/wheel_actual_rad_s`) | ✅ **약 9.995~9.999 Hz** |
| 8 | 펌웨어 STATUS 10Hz 설정과 일치 | ✅ |
| 9 | `in_waiting` 기반 `read_available()`이 실제 `/dev/ttyACM0`에서 동작 | ✅ |
| 10 | `/stm/encoder_total`로 양쪽 누적값 수신 | ✅ |
| 11 | `/stm/wheel_actual_rad_s`로 양쪽 실제 속도 수신 | ✅ |
| 12 | `ros2 topic pub --once` 후 약 0.5초에 watchdog 자동 정지(`0.000,0.000`) | ✅ |
| 13 | 송신 경로(ROS2 → STM) 재확인 | ✅ |

7번은 PTY에서만 확인됐던 `in_waiting` 폴링이 실제 USB CDC 드라이버에서도 정상 동작함을
보여준다 — 이전 기록에서 "실기에서 확인 필요"로 남겨둔 위험이 해소됐다.

### ★ 좌우 매핑 실측 확정

그동안 "코드 주석 기준이며 실측 미확정"으로 남아 있던 항목이 이번에 확정됐다.

```
물리 왼쪽  바퀴 ↔ STM 논리 Left  ↔ /stm/encoder_total[0] ↔ /stm/wheel_actual_rad_s[0]
물리 오른쪽 바퀴 ↔ STM 논리 Right ↔ /stm/encoder_total[1] ↔ /stm/wheel_actual_rad_s[1]
```

| 조작 | 관측 |
|---|---|
| 물리 왼쪽 바퀴를 돌림 | `encoder_total[0]`만 변화 |
| 물리 오른쪽 바퀴를 돌림 | `encoder_total[1]`만 변화 |
| `SET_WHEEL_VEL,2.000,0.000` (`linear.x=0.065, angular.z=-0.433333`) | 물리 왼쪽만 회전, `encoder_total[0]`만 변화 |
| `SET_WHEEL_VEL,0.000,2.000` (`linear.x=0.065, angular.z=+0.433333`) | 물리 오른쪽만 회전, `encoder_total[1]`만 변화 |
| 왼쪽만 전진 | `wheel_actual_rad_s` = `[양수, 0 근처]` |
| 오른쪽만 전진 | `[0 근처, 양수]` |
| 왼쪽만 후진 | `[음수, 0 근처]` |
| 오른쪽만 후진 | `[0 근처, 음수]` |

→ **PWM 출력 채널과 엔코더 입력 채널의 좌우 짝이 정상**이다. 이전에 우려했던
"엔코더만 교차되어 Left PI가 오른쪽 실측값을 오차 입력으로 쓰는" 상태가 **아님**을 확인했다.
전진 양수 / 후진 음수 부호도 좌우 모두 정상.

### 실기 중 발견하고 해결한 사항 (하드웨어)

- SSAFY로 장비를 이동하는 과정에서 일부 배선이 빠져 있었다.
- 초기에는 왼쪽 모터 또는 왼쪽 엔코더가 동작하지 않는 현상이 나타났다.
- 배선을 재확인·재연결한 뒤 재시험하여 양쪽 모터 구동, 양쪽 엔코더 값, 좌우 매핑 모두 정상 확인.
- **코드 결함이 아니라 이동 과정의 하드웨어 배선 문제였다.**

### 아직 검증하지 않은 것

1. STATUS 중단 후 `/stm/connected=false` 전환 및 재연결 복귀
2. USB 강제 분리 시 RX fatal error 처리(종료 코드 1, TX/RX 타이머 취소)
3. 실제 Stall 발생과 `/stm/fault` 전이(`STALL_LEFT`/`STALL_RIGHT`/`STALL_BOTH`)
4. `FAULT_CLEARED,STALL` 수신
5. `RESET_STALL` 송신 (브리지 미구현)
6. 엔코더 1회전당 정확한 카운트 수 및 `MOTOR_ENCODER_QUADRATURE_MULTIPLIER`(현재 4.0f) 검증
7. 실제 바닥 주행
8. `wheel_separation_m=0.30` 실측 확정 (여전히 플레이스홀더)
9. STATUS 수신이 끊겼을 때 주행 명령을 강제로 0으로 만드는 추가 안전 정책

### ⚠️ 이 기록의 한계

이 저장소 규칙은 원본 출력을 `<details>`로 남겨 검증 가능하게 하는 것인데, 이번 실기도
**콘솔 원본 출력이 확보되지 않았다.** 위 수치 중 근거가 있는 것은 사용자가 보고한
STATUS 주기(약 9.995~9.999Hz)뿐이며, 아래는 **관측되지 않았으므로 기록하지 않는다**:

- 각 토픽의 구체적 target/actual/pwm/encoder 수치
- watchdog 정지까지의 정확한 경과 시간(로그 타임스탬프 차)
- 손 회전 시 엔코더 카운트 절댓값(→ quadrature 배율 검증에 필요했던 값)
- 실행 호스트(Jetson / 개발 PC)

다음 실기에서는 노드 콘솔 출력(`STATUS #N ...`, `TX tx#N ...`, `watchdog state: ...`)을
`tee`로 파일에 남겨 함께 첨부할 것.

### 참고: 같은 커밋의 자동화 테스트 결과 (2026-08-03, Claude, PTY/단위 테스트)

실기와 별개로 하드웨어 없이 돌린 결과다.

- `colcon build --symlink-install` — 경고·에러 0
- `python3 -m pytest src/stm_serial_bridge/test/ -q` — **298 passed**
  (차동구동 9 + 프로토콜 10 + SerialLink 53 + watchdog 26 + limiter 28 + 패킷파서 96 +
  라인디코더 34 + RX 노드 42)
- PTY 통합: `master → read_available() → feed() → parse_packet() → Publisher` 경로 확인
- `connected` 경계값(정확히 `status_timeout_sec`)에서 false 전환, 비STATUS 패킷은
  timeout을 갱신하지 않음, `STALL_RESET,OK` 단독으로 fault가 NONE이 되지 않음 등 확인

## 2026-08-03 — ✅ BE 59 tests, SLAM 미터→이미지 픽셀 변환 추가 (Claude)

- **명령**: `backend/gradlew.bat test`
- **환경**: Windows 11, Microsoft OpenJDK 21.0.12, MySQL(EC2 Docker)
- **결과**: BUILD SUCCESSFUL, 59 tests, 0 failures (신규 4: SlamCoordinateConverterTest 3, 텔레메트리 meters 모드 1)
- **변경**: EM 협의(위치는 SLAM 미터로 발행, BE가 변환)에 따라 `SlamCoordinateConverter` 신설.
  `픽셀x=(x-originX)/resolution`, `픽셀y=height-(y-originY)/resolution` (ROS 규약 세로축 뒤집기).
  `mqtt.position-unit`(기본 pixels)·`mqtt.map-id`(기본 2)로 제어 — EM 발행 시작 시 meters 전환
- **활성화 전제**: `library_maps` id=2 행에 EM의 실제 map.yaml 값(resolution·origin)과
  FE가 쓰는 지도 이미지 크기가 정확히 들어가야 함

## 2026-08-02 — ✅ EM+ROS2 실기: `/cmd_vel` → Serial Bridge → STM32 → 모터 구동 확인 (relu, 실기)

- **대상 커밋**: `b4293b0` "[feat] ROS2 <-> STM serial Bridge 추가." (`em/feature/motor-control`)
- **대상 코드**: `ros2_ws/src/stm_serial_bridge` (STM32 펌웨어는 변경 없음, UART Protocol v1 그대로)
- **하드웨어**: STM32 NUCLEO-F446RE + BTS7960 + DC 모터 2개(엔코더), USB Serial(USART2/ST-LINK VCP, 115200 8N1)
- **실행자**: relu (사람이 직접 실기 수행). 이 항목은 사용자 보고를 받아 Claude가 대신 기록함.
- **`/cmd_vel` 발행 수단**: `ros2 topic pub` (`teleop_twist_keyboard`는 사용하지 않음 — 키보드
  teleop 실기는 여전히 미완료 항목)

### 결과: 송신 경로(ROS2 → Bridge → STM32 → Motor) 실기 연동 완료

| # | 확인 항목 | 결과 |
|---|---|---|
| 1 | ROS2 `/cmd_vel` 토픽 발행 | ✅ |
| 2 | `stm_serial_bridge` 노드의 `/cmd_vel` 수신 | ✅ |
| 3 | 차동구동 계산 → 좌우 바퀴 각속도 변환 | ✅ |
| 4 | `SET_WHEEL_VEL,<left_rad_s>,<right_rad_s>` USB Serial 전달 | ✅ |
| 5 | STM32가 명령 수신해 양쪽 모터 실제 구동 | ✅ |
| 6 | 전진 / 후진 | ✅ |
| 7 | 좌회전 / 우회전 | ✅ |
| 8 | `/cmd_vel` 중단 시 watchdog 자동 정지 (약 0.5초) | ✅ |
| 9 | ROS2 → Bridge → STM32 → Motor 전체 송신 경로 | ✅ |

8번은 Bridge의 `command_watchdog`이 `timed_out`으로 전환해 `SET_WHEEL_VEL,0.000,0.000`을
계속 내보내는 동작이다. STM32 자체의 Communication Timeout(`MOTION_CONTROLLER_COMM_TIMEOUT_MS`)과는
별개의 상위 안전장치이며, 이번 실기에서는 상위(Bridge) 쪽이 먼저 동작한 것으로 확인됐다.

### 아직 검증되지 않은 것 (STM → ROS2 수신 경로 전체)

1. STM32가 보내는 `STATUS` 패킷을 Bridge가 수신 — **미구현** (`serial_link.py`에 `read()` 없음)
2. `STATUS` 문자열 파싱 — 미구현
3. actual wheel velocity / PWM / encoder total의 ROS2 토픽 발행 — 미구현
4. 잘못된 패킷·수신 끊김 처리 — 미구현
5. STATUS 수신 경로 실기 테스트 — 미수행

### ⚠️ 이 기록의 한계 (검증 가능성 관련)

이 저장소의 기록 규칙은 "원본 출력을 `<details>`로 남겨 사람이 검증 가능하게" 하는 것인데,
이번 실기는 **콘솔 원본 출력이 확보되지 않았다.** 아래 항목도 미기록이다:

- 실행 호스트 (Jetson Orin Nano / 개발 PC 중 어디였는지)
- 실제 `serial_port` 값, `max_wheel_rad_s` 사용값, `tx_rate_hz`·`cmd_vel_timeout_sec` 값
- 바퀴 공중 상태였는지 지면 주행이었는지
- 좌우 회전 방향이 명령과 일치했는지에 대한 정량 근거
  (엔코더 좌우 매핑 `TIM2`=Left / `TIM8`=Right는 여전히 코드 주석 기준이며 실측 미확정)

따라서 이 항목은 **"동작을 확인했다"는 사람의 관찰 기록**이며, 재현 가능한 로그 근거는 없다.
다음 실기에서는 노드 콘솔 출력(`TX tx#N state=... command='...'`)과 사용 파라미터를 함께 남길 것.

### 참고: 같은 커밋의 자동화 테스트 결과 (2026-08-02, Claude, PTY/단위 테스트)

실기와 별개로 하드웨어 없이 돌린 결과다.

- `colcon build --symlink-install` — 경고·에러 0
- `python3 -m pytest src/stm_serial_bridge/test/ -q` — **112 passed**
  (차동구동 9 + 프로토콜 10 + SerialLink 39 + watchdog 26 + limiter 28)
- PTY(`pty.openpty()`) 통합: 54~57 프레임 전부 ASCII·CRLF 종단, 깨진/빈 프레임 0, 평균 20.00 Hz,
  `waiting(0,0)` → `active` → `timed_out(0,0)` 전이 확인
- `max_wheel_rad_s=2.0`에서 원본 `1.923/4.231` → `0.909/2.000` 비례 축소, 제한 전 프레임 PTY 송신 0건
- write 실패(PTY master close → `[Errno 5]`) 시 `Serial TX failed` 1회 + 0.22초 내 자동 종료, 종료 코드 1

## 2026-08-02 13:45 — ✅ BE 55 tests + FE 타겟 선택 릴레이 3종 E2E 통과 (Claude)

- **명령**: `backend/gradlew.bat test`, 이후 `bootRun`(8081, **MQTT_BROKER_URL=tcp://localhost:1883 강제**)
  + 가짜 Jetson(Python: mp4→JPEG WS 발행) + 가짜 FE(Node WS 리스너) + mosquitto_pub/sub + curl
- **환경**: Windows 11, OpenJDK 21.0.12, MySQL(AWS RDS), Mosquitto 로컬 브로커
- **브랜치**: `backend/feature/video-select-relay`
- **결과**: 18→**19 suites, 55 tests**, 0 failures (신규 7: MqttTracksMessageHandlerTest 4, FollowTargetServiceTest 3)
- **신규 기능 E2E**:
  - 영상 릴레이: `/ws/carts/1/video/publish`(발행) → `/ws/carts/1/video`(시청).
    98프레임/10초(9.7fps, ~40KB JPEG) 손실 0, 시청측 저장 JPEG 디코딩 정상(640×480)
  - 트랙 릴레이: MQTT `choll/cart/tracks` → WS `TRACKS_UPDATED` 페이로드 원형 그대로 수신
  - 타겟 선택: `POST /api/carts/1/follow/target {trackId:16}` → 202 `{SENT}` →
    MQTT `choll/cart/cmd {"command":"SELECT_TARGET","trackId":16}` 수신 확인
- **추가(14:00) 브라우저 시각 검증**: BE 정적 테스트 페이지
  `http://localhost:8081/target-select-test.html` (FE 참조 구현으로 커밋) +
  `tests/tools/fake_jetson.py`(result01.mp4→JPEG WS + 가짜 이동 트랙 MQTT 5Hz)로
  영상 렌더링(271프레임)·박스 실시간 갱신·**박스 클릭→202 SENT→MQTT SELECT_TARGET** 확인
- **트러블슈팅 2건** (재발 방지 기록):
  - `ServletServerContainerFactoryBean`이 테스트 mock 서블릿 컨텍스트에서 기동 실패
    → 세션별 `setBinaryMessageSizeLimit(1MB)`로 대체
  - **backend/.env의 MQTT_BROKER_URL이 EC2 브로커**라 로컬 pub/sub과 분리돼 침묵
    → E2E는 반드시 `MQTT_BROKER_URL=tcp://localhost:1883` 오버라이드로 실행할 것.
    EC2 브로커에는 실카트 LWT(retained carts/status)가 살아 있음 — 테스트 트래픽 금지

<details>
<summary>E2E 원본 출력 (가짜 FE 수신 로그·cmd 구독)</summary>

```text
# fake_jetson.py
connected: ws://localhost:8081/ws/carts/1/video/publish
sent 98 frames in 10.1s (~9.7 fps)

# fake_fe.mjs (발췌)
[video] frame #1 (38560 bytes) saved
[video] frame #80 (40644 bytes) saved
[events] {"type":"TRACKS_UPDATED","payload":{"image_width":640,"image_height":480,"tracks":[{"id":16,"x":220,"y":30,"w":180,"h":420},{"id":23,"x":20,"y":180,"w":60,"h":120}]}}
[video] total frames=98, last=39245 bytes

# mosquitto_sub -t choll/cart/cmd -v
choll/cart/cmd {"command":"SELECT_TARGET","trackId":16}

# REST 응답
{"trackId":16,"status":"SENT"}
```

</details>


## 2026-07-31 — ✅ BE 48 tests, MQTT 브로커 인증 설정 추가 후 통과 (Claude)

- **명령**: `backend/gradlew.bat test`
- **환경**: Windows 11, Microsoft OpenJDK 21.0.12, MySQL(AWS RDS)
- **결과**: BUILD SUCCESSFUL (18 suites, 48 tests, 0 failures)
- **변경**: EC2 Mosquitto가 인증 필수가 되어 `mqtt.username`/`mqtt.password` 설정 추가
  (빈 값이면 기존처럼 익명 접속 — 로컬 개발 영향 없음). CI/CD 파일 신규:
  `Jenkinsfile`, `backend/Dockerfile`, `frontend/Dockerfile`+`nginx.conf`, `infra/docker-compose.app.yml`

## 2026-07-31 — ✅ BE 48 tests + TaskProgress에 totalSlots 추가 검증 (Claude)

- **명령**: `backend/gradlew.bat test`, 이후 `bootRun`(8081) + `GET /api/carts/1/tasks/progress`
- **환경**: Windows 11, Microsoft OpenJDK 21.0.12, MySQL(AWS RDS)
- **결과**: 18 suites, 48 tests, 0 failures, 0 errors
- **변경**: 진행률 분모를 슬롯 개수로 쓰기로 한 팀 결정에 따라 `TaskProgress`에 `totalSlots`(카트 슬롯 수, DB 카운트) 추가.
  FE 계산식: `percent = (totalSlots - remainingBooks) / totalSlots` (빈 카트 100%, 6권 50%)
- **E2E**: `{"totalSlots":12,"totalBooks":27,"shelvedBooks":27,"remainingBooks":0,...}` — DB 슬롯 12개 반영 확인

## 2026-07-31 11:37 — ✅ BE 48 tests, 슬롯 30→12 축소 반영 후 전체 통과 (Claude)

- **명령**: `backend/gradlew.bat test`
- **환경**: Windows 11, Microsoft OpenJDK 21, MySQL(AWS RDS)
- **브랜치**: `develop` (ed719a8 이후 작업 트리, 커밋 전)
- **결과**: 18 suites, 48 tests, 0 failures, 0 errors
- **변경 범위**: 슬롯 개수 30→12 — `cart-slot-seed.sql`(12행 + 13번 이후 DELETE),
  `Slot.java` 체크 제약 `between 1 and 12`, `SlotService.Response` Swagger `maximum="12"`,
  `SlotServiceTests` 슬롯 번호 30→12, `CART_SLOT.md`·`bookDB.md` 문서 갱신
- ⚠️ 운영 DB의 기존 `slots_chk_1 CHECK (1~30)` 제약은 ddl-auto=update로 변경되지 않음 —
  시드 재실행으로 13~30번 행 삭제는 되지만, 제약 자체를 12로 조이려면 수동 ALTER 필요

<details>
<summary>gradlew test 원본 출력 (요약부)</summary>

```text
> Task :compileJava
> Task :processResources
> Task :classes
> Task :compileTestJava
> Task :testClasses
> Task :test

BUILD SUCCESSFUL in 19s
4 actionable tasks: 4 executed

# build/test-results/test/*.xml 집계
suites=18 tests=48 failures=0 errors=0
```

</details>

## 2026-07-30 17:40 — ✅ BE 48 tests + NAV 명령 하행·Task 진행률 E2E 통과 (Claude)

- **명령**: `backend/gradlew.bat test`, 이후 `bootRun`(8081) + REST 호출 + `mosquitto_sub -t "choll/cart/cmd"` + Node WS 리스너
- **환경**: Windows 11, Microsoft OpenJDK 21.0.12, MySQL(AWS RDS), Mosquitto 로컬 브로커
- **브랜치**: `develop` (109b1b7 이후 작업 트리, 커밋 전)
- **결과**: 18 suites, 48 tests, 0 failures, 0 errors (신규 9개: NavigationServiceTest 6, TaskServiceTests 3 추가)
- **검증 범위**:
  - NAV-01 `POST /navigation {zoneId:8}` → 202 `{navigationId:1, ACCEPTED}` + 카트 MOVING
    + MQTT `choll/cart/cmd {"requestId":1,"command":"MOVE","zoneId":8,"x":775.0,"y":505.0}` (Z7 bbox 중심)
    + WS `NAVIGATION_STATUS_UPDATED {ACCEPTED}`
  - 중복 시작 → 400, NAV-02 `DELETE` → 204 + 카트 IDLE + MQTT CANCEL + WS `{CANCELLED}`
  - SortingTask: RFID DETECTED → 작업 생성, REMOVED → 완료.
    진행률 `{total:1, shelved:0→1, remaining:1→0}` REST·WS(`TASK_PROGRESS_UPDATED`) 동시 확인 — shelvedBooks 하드코딩 0 해소
- **부수 검증**: FE 이벤트 이중 수신 제보 → 단일 리스너로 1회 수신 확인(BE 정상). 원인은 FE CartSocket의
  StrictMode 재연결 경합(소켓 2개 생존)으로 진단.

<details>
<summary>E2E: MQTT 명령 발행 + WS 수신 원본</summary>

```text
# mosquitto_sub -t "choll/cart/cmd" -v
choll/cart/cmd {"requestId":1,"command":"MOVE","zoneId":8,"x":775.0,"y":505.0}
choll/cart/cmd {"requestId":1,"command":"CANCEL","zoneId":8,"x":null,"y":null}

# WS 리스너 (/ws/carts/1)
MSG {"type":"NAVIGATION_STATUS_UPDATED","payload":{"navigationId":1,"status":"ACCEPTED","destinationZoneId":8,"failReason":null}}
MSG {"type":"NAVIGATION_STATUS_UPDATED","payload":{"navigationId":1,"status":"CANCELLED","destinationZoneId":8,"failReason":null}}
MSG {"type":"SLOT_UPDATED","payload":{"id":5,"slotNumber":5,"status":"OCCUPIED","isTarget":false,"book":{...,"title":"이불 여행",...}}}
MSG {"type":"TASK_PROGRESS_UPDATED","payload":{"totalBooks":1,"shelvedBooks":0,"remainingBooks":1,"currentZoneSlotNumbers":[]}}
MSG {"type":"SLOT_UPDATED","payload":{"id":5,"slotNumber":5,"status":"EMPTY","isTarget":false,"book":null,...}}
MSG {"type":"TASK_PROGRESS_UPDATED","payload":{"totalBooks":1,"shelvedBooks":1,"remainingBooks":0,"currentZoneSlotNumbers":[]}}

# REST: GET /tasks/progress
{"totalBooks":1,"shelvedBooks":0,"remainingBooks":1,"currentZoneSlotNumbers":[]}   (DETECTED 후)
{"totalBooks":1,"shelvedBooks":1,"remainingBooks":0,"currentZoneSlotNumbers":[]}   (REMOVED 후)
```

</details>

## 2026-07-30 14:20 — ✅ BE 39 tests + 하트비트 토픽 변경(carts/status) 검증 (Claude)

- **명령**: `backend/gradlew.bat test`, 이후 `bootRun`(8081) + `mosquitto_pub -t "carts/status" -m '{}'`
- **환경**: Windows 11, Microsoft OpenJDK 21.0.12, MySQL(AWS RDS), Mosquitto 로컬 브로커
- **브랜치**: `develop` (5aed143 이후 작업 트리, 커밋 전)
- **결과**: 17 suites, 39 tests, 0 failures, 0 errors
  (토픽에서 cartId 파싱이 사라져 `ignoresUnsupportedTopics` 테스트 1개 제거 → 40→39)
- **변경**: EM 협의로 하트비트 토픽 `carts/+/status` → `carts/status` (cartId 미포함).
  `mqtt.rfid-cart-id`를 공용 `mqtt.cart-id`로 통합 (하트비트·RFID 공용 귀속 설정)
- **E2E**: 기동 직후 `"online":false` → `carts/status` 빈 페이로드 1건 발행 → `"online":true` (REST 교차 확인)

## 2026-07-30 13:26 — ✅ BE 40 tests + 하트비트 ONLINE/OFFLINE E2E 통과 (Claude)

- **명령**: `backend/gradlew.bat test`, 이후 `bootRun`(포트 8081, MQTT_CLIENT_ID 분리) + `mosquitto_pub` + Node WS 리스너
- **환경**: Windows 11, Microsoft OpenJDK 21.0.12, MySQL(AWS RDS), Mosquitto 로컬 브로커
- **브랜치**: `backend/feature/mqtt-ws-bridge` (2f0b442 이후 작업 트리, 커밋 전)
- **결과**: 17 suites, 40 tests, 0 failures, 0 errors (신규 8개: CartConnectionServiceTest 5, MqttHeartbeatMessageHandlerTest 3)
- **검증 범위**:
  - `carts/1/status` 하트비트 수신 → OFFLINE 카트 ONLINE 전환 + WS `CART_CONNECTION_UPDATED {online:true}`
  - 무신호 15초(+워치독 5초 주기) → OFFLINE 전환 + WS `{online:false}` (13:05:00 수신 → 13:05:20 전환, 정확히 타임아웃+주기)
  - RFID 태깅도 생존 신호로 처리 (검증 중 실물 태깅에도 OFFLINE 전환되는 결함 발견 → markAlive 연결로 수정 후 재검증)
  - 위치 텔레메트리 markAlive 경유로 전환 이벤트 공유
- **주의**: 생존 판정이 페이로드 timestamp 기준 — 과거 timestamp를 보내면 즉시 OFFLINE 재전환됨(테스트 중 재현).
  카트 시계 동기화(NTP) 전제. 수신 시각 기준으로 바꿀지 EM과 논의 필요.

<details>
<summary>E2E: WS 수신 원본 (하트비트·워치독·RFID 생존신호)</summary>

```text
# 시나리오 1: 하트비트 → ONLINE, 무신호 20초 → OFFLINE (KST 13:05)
[2026-07-30T04:05:04.989Z] MSG {"type":"CART_CONNECTION_UPDATED","payload":{"online":true,"lastSeenAt":"2026-07-30T13:05:00"}}
[2026-07-30T04:05:20.000Z] MSG {"type":"CART_CONNECTION_UPDATED","payload":{"online":false,"lastSeenAt":"2026-07-30T13:05:00"}}
# (같은 구간에 실물 RFID 태깅 SLOT_UPDATED 다수 수신 — 태깅 중에도 OFFLINE 전환된 것이 결함 발견 계기)

# 시나리오 2 (markAlive 연결 후 재기동): RFID DETECTED만으로 ONLINE 전환
[2026-07-30T04:26:39.858Z] MSG {"type":"CART_CONNECTION_UPDATED","payload":{"online":true,"lastSeenAt":"2026-07-30T13:15:00"}}
[2026-07-30T04:26:39.885Z] MSG {"type":"SLOT_UPDATED","payload":{"id":5,"slotNumber":5,"status":"OCCUPIED",...}}
# 페이로드 timestamp(13:15)가 실제 시각(13:26)보다 과거라 워치독이 즉시 OFFLINE 재전환 — timestamp 기준 판정의 특성
[2026-07-30T04:26:41.703Z] MSG {"type":"CART_CONNECTION_UPDATED","payload":{"online":false,"lastSeenAt":"2026-07-30T13:15:00"}}
```

REST 교차 확인: 하트비트 후 `GET /api/carts/1` → `"online":true`, 무신호 후 → `"online":false`.

</details>

## 2026-07-30 12:11 — ✅ BE 32 tests + MQTT→WS 실연동(위치·RFID) E2E 통과 (Claude)

- **명령**: `backend/gradlew.bat test`, 이후 `bootRun`(MQTT_ENABLED=true) + `mosquitto_pub` 실발행 + Node WS 리스너
- **환경**: Windows 11, Microsoft OpenJDK 21.0.12, MySQL(AWS RDS), Mosquitto 로컬 브로커, Node v24
- **브랜치**: `develop` (f5584e2 기준 작업 트리, 커밋 전)
- **결과**: 15 suites, 32 tests, 0 failures, 0 errors (신규 11개: CartPositionTelemetryServiceTest 2,
  MqttRfidMessageHandlerTest 4, SlotRfidEventServiceTest 4, CartEventPublisherTest 1)
- **검증 범위**:
  - MQTT `carts/1/telemetry/position` 수신 → DB 갱신 + WS `CART_POSITION_UPDATE` 발행 (yaw는 EM 미송신으로 임시 0)
  - MQTT `choll/cart/rfid` DETECTED → uid `0437F306`(초록 눈 코끼리) book_copies 매칭 → 슬롯 1 OCCUPIED + WS `SLOT_UPDATED`
  - REMOVED → 슬롯 1 EMPTY 복구 + WS `SLOT_UPDATED` (테스트 후 시드 상태 원복 확인)
  - REST `GET /api/carts/1`, `GET /api/carts/1/slots/1` 로 DB 반영 교차 확인

<details>
<summary>Gradle 테스트 출력 + 스위트별 집계</summary>

```text
> Task :compileJava
> Task :processResources
> Task :classes
> Task :compileTestJava
> Task :processTestResources NO-SOURCE
> Task :testClasses
> Task :test

BUILD SUCCESSFUL in 36s
4 actionable tasks: 4 executed

com.ssafy.backend.BackendApplicationTests: tests=1 failures=0 errors=0 skipped=0
com.ssafy.backend.bookimport.BookCsvImportServiceTests: tests=1 failures=0 errors=0 skipped=0
com.ssafy.backend.booklocation.BookLocationServiceTests: tests=4 failures=0 errors=0 skipped=0
com.ssafy.backend.cart.CartServiceTests: tests=1 failures=0 errors=0 skipped=0
com.ssafy.backend.mqtt.position.CartPositionTelemetryServiceTest: tests=2 failures=0 errors=0 skipped=0
com.ssafy.backend.mqtt.position.MqttPositionMessageHandlerTest: tests=3 failures=0 errors=0 skipped=0
com.ssafy.backend.mqtt.position.PolygonZoneMatcherTest: tests=2 failures=0 errors=0 skipped=0
com.ssafy.backend.mqtt.position.RecentPositionBufferTest: tests=2 failures=0 errors=0 skipped=0
com.ssafy.backend.mqtt.position.StableZoneTrackerTest: tests=3 failures=0 errors=0 skipped=0
com.ssafy.backend.mqtt.rfid.MqttRfidMessageHandlerTest: tests=4 failures=0 errors=0 skipped=0
com.ssafy.backend.mqtt.rfid.SlotRfidEventServiceTest: tests=4 failures=0 errors=0 skipped=0
com.ssafy.backend.slot.SlotServiceTests: tests=2 failures=0 errors=0 skipped=0
com.ssafy.backend.task.TaskServiceTests: tests=1 failures=0 errors=0 skipped=0
com.ssafy.backend.websocket.CartEventPublisherTest: tests=1 failures=0 errors=0 skipped=0
com.ssafy.backend.websocket.PositionTestPublisherTest: tests=1 failures=0 errors=0 skipped=0
```

</details>

<details>
<summary>E2E: mosquitto_pub 발행 ↔ Node WS 리스너(/ws/carts/1) 수신 원본</summary>

발행 (mosquitto_pub -h localhost):

```text
-t "carts/1/telemetry/position" -m '{"x": 250.5, "y": 120.0, "timestamp": "2026-07-30T12:10:00.000+09:00"}'
-t "choll/cart/rfid" -m '{"slot_id": 1, "uid": "0437F306", "event": "DETECTED", "timestamp": "2026-07-30T12:10:01.000+09:00"}'
-t "choll/cart/rfid" -m '{"slot_id": 1, "uid": "0437F306", "event": "REMOVED", "timestamp": "2026-07-30T12:11:00.000+09:00"}'
```

WS 수신:

```text
[2026-07-30T03:08:09.152Z] OPEN
[2026-07-30T03:08:21.403Z] MSG {"type":"CART_POSITION_UPDATE","payload":{"mapId":2,"x":250.5,"y":120.0,"yaw":0,"valid":true}}
[2026-07-30T03:08:22.435Z] MSG {"type":"SLOT_UPDATED","payload":{"id":1,"slotNumber":1,"status":"OCCUPIED","isTarget":false,"book":{"id":143180,"bookId":112105,"title":"초록 눈 코끼리","author":"강정연 글;백대승 그림","callNumber":"아 813.8-강74ㅊ","rfidTagId":"0437F306","bookshelfId":9,"bookshelfNumber":"800","shelfZoneId":7,"zoneName":"오른쪽 중앙 존"},"lastDetectedAt":"2026-07-30T12:10:01"}}
[2026-07-30T03:09:04.499Z] MSG {"type":"SLOT_UPDATED","payload":{"id":1,"slotNumber":1,"status":"EMPTY","isTarget":false,"book":null,"lastDetectedAt":"2026-07-30T12:11:00"}}
```

REST 교차 확인: `GET /api/carts/1` → position 250.5/120.0, `GET /api/carts/1/slots/1` → OCCUPIED 후 EMPTY 복구.

</details>

## 2026-07-28 17:43 — ✅ BE 20 tests·Z1~Z7 시드 재실행 통과 (Codex)

- **명령**: `backend/gradlew.bat test`, `source backend/src/main/resources/db/test-room-bookshelves.sql`
- **환경**: Windows 11, Microsoft OpenJDK 21.0.11, MySQL 8.4
- **브랜치**: `backend/feature/rfid_zone_data`
- **결과**: 10 suites, 20 tests, 0 failures, 0 errors
- **검증 범위**: Z1~Z7 중복 없는 재구성, 책장 10개 존 배치, 소장 도서
  67,289권 책장 연결, 테스트 RFID 5개 보존, 백엔드 전체 테스트

<details>
<summary>백엔드 Gradle 테스트 최종 출력</summary>

```text
> Task :compileJava UP-TO-DATE
> Task :processResources
> Task :classes
> Task :compileTestJava UP-TO-DATE
> Task :processTestResources NO-SOURCE
> Task :testClasses UP-TO-DATE
> Task :test

BUILD SUCCESSFUL in 40s
4 actionable tasks: 2 executed, 2 up-to-date
```

</details>

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
