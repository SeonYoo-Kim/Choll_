# Test Log — AI

**AI 파트(`ai/`) 테스트 실행 기록**입니다. 에이전트(Claude)든 사람이든, AI 테스트를 돌렸으면 결과를 여기에 남깁니다.
목적: "테스트 통과했다"는 말을 사람이 눈으로 검증할 수 있게 하는 것.
FE/BE 등 다른 파트의 기록은 [루트 tests/TEST_LOG.md](../../tests/TEST_LOG.md)를 사용합니다.

## 기록 규칙

- **최신 항목이 맨 위** (이 문단 바로 아래에 추가).
- 항목 형식: `## 날짜 시각 — 결과 요약 (실행자)` + 환경·명령·커밋 + 접힌 전체 출력(`<details>`).
- **실패도 기록한다.** 실패 → 수정 → 재실행이면 두 번 다 남겨서 이력이 보이게 한다.
- 원본 출력은 `<details>` 블록에 그대로 붙인다 (요약만 믿지 말고 검증 가능하게).

---

## 2026-08-03 14:11 — ✅ MQTT 토픽 개편 후 114 passed, ruff 변경 파일 0건 (Claude)

- **명령**: `pytest ai/test/ -q` + `ruff check fe_bridge_logic.py fe_bridge_node.py follow_robot_launch.py test_fe_bridge_logic.py`
- **환경**: Windows 11 개발 PC, Python 3.12 (miniforge base), ruff 0.16.0
- **커밋**: `d6ab80c`(develop) 위로 리베이스 — 브랜치 `refactor/mqtt-topic-rename`
- **변경**: MQTT 토픽 개편에 따른 fe_bridge 파라미터 기본값 교체
  - `tracks_topic`: `choll/cart/tracks` → `status/target` (launch + `declare_parameter` 양쪽)
  - `command_topic`: `choll/cart/cmd` → `cmd/move/cart` (launch + `declare_parameter` 양쪽)
  - 나머지는 docstring·주석의 토픽명 갱신. **로직 변경 없음 → 테스트 개수 변화 없음(114).**
- **미검증**: Jetson 실기 스모크(새 토픽으로 BE와 실제 송수신)는 미실시.
  BE 단위 테스트 결과는 [tests/TEST_LOG.md](../../tests/TEST_LOG.md) 2026-08-03 항목 참조.
- **참고**: 저장소 전체 `ruff check .`는 **219건으로 변화 없음** — 이번 변경과 무관한 기존 지적
  (docstring 누락 등). AI 변경 파일만 검사하면 0건. 함께 손댄 `tests/tools/fake_jetson.py`는
  토픽 문자열만 바뀌어 기존 1건(D103)이 그대로 유지된다.

<details>
<summary>pytest / ruff 원본 출력</summary>

```
........................................................................ [ 63%]
..........................................                               [100%]
114 passed in 0.14s
```

```
warning: The following rules have been removed and ignoring them has no effect:
    - ANN101
    - ANN102

All checks passed!
```

</details>

## 2026-08-02 13:47 — ✅ 114 passed (+11 신규), ruff 변경 파일 0건 (Claude)

- **명령**: `pytest ai/test/` + `ruff check fe_bridge_logic.py fe_bridge_node.py launch setup.py test_fe_bridge_logic.py`
- **환경**: Windows 11 개발 PC, Python 3.12.12 (miniforge base), pytest 9.1.1, ruff 0.16.0
- **커밋**: develop 이후 작업 트리 (`ai/feature/fe-target-select`, 커밋 전)
- **맥락**: FE 화면에서 추종 대상을 직접 선택하는 모드 — Jetson 쪽 브릿지.
  - `fe_bridge_node.py` 신규: /camera/image_raw→JPEG→BE WS(10fps, drop-oldest),
    /person_tracks→MQTT choll/cart/tracks(5Hz, bbox 좌상단 변환),
    MQTT choll/cart/cmd SELECT_TARGET→/select_target. 연결 실패 시 재접속(BE보다
    먼저 떠도 안전). launch `fe_bridge:=true auto_select:=false`로 활성화.
  - `fe_bridge_logic.py` 순수 모듈: RateLimiter/build_tracks_payload/parse_select_command.
  - 신규 테스트 11개: 전송률 제한 3, 페이로드 변환 3, 명령 파싱 5
    (MOVE 등 타 명령 무시, 비정수 trackId 거부 포함).
  - **BE 상대편은 backend/feature/video-select-relay에서 가짜 Jetson/FE로 E2E 완료**
    (tests/TEST_LOG.md 2026-08-02 항목). Jetson 실기 스모크는 내일 오전 예정.
- **주의**: Jetson에 `pip3 install websocket-client paho-mqtt` 선행 필요.

<details>
<summary>pytest 출력 (마지막 줄)</summary>

```
============================= 114 passed in 0.12s =============================
```

</details>

## 2026-07-31 15:20 — ✅ Jetson 실기: 가짜 SLAM 포즈로 /target_position 검증 (사용자+Claude)

- **명령**: launch(8노드) + `ros2 topic pub -r 10 /robot_pose ...` (yaw 0°/90° 두 케이스)
  + `ros2 topic echo /target_position`
- **환경**: Jetson Orin Nano, ROS2 Humble, 실카메라·LiDAR, SLAM 없음(가짜 포즈)
- **브랜치**: `ai/feature/target-position-publish`
- **검증**:
  - 포즈 미발행 시 발행 보류 (stale 가드 동작)
  - **동일 위치에서 yaw 전환 직전/직후 쌍** (결정적 증거):
    yaw=0° (1.6499, -0.0214) ↔ yaw=90° (0.0230, 1.6348).
    이론값(90° 회전)은 (0.0214, 1.6499) — 오차 거리 1.5cm(LiDAR 노이즈 범위),
    방위각 0.07°. 쿼터니언→yaw→지도 변환 체인 정합 확인.
  - 보조 측정(사람 이동 후): yaw=0° (1.651, 0.004), yaw=90° (-0.137, 1.269)
    — 각각 거리·방위각으로 역산 시 자기일관. 부호 규약(왼쪽=+방위각)도 REP 103대로.
- **후속**: 토픽 계약 확정 — EM이 `/robot_pose`(PoseStamped, frame=map) 발행하기로
  (AI 선정 규격 채택). EM 실포즈 연동 후 재검증 필요.

<details>
<summary>ros2 topic echo 원본</summary>

```
# ── 동일 위치, yaw 전환 직전/직후 쌍 ──
# orientation {z: 0.0, w: 1.0} (yaw 0°), stamp 1785460257.76
point:
  x: 1.6498616191146769
  y: -0.02136724348545165
  z: 0.0
# orientation {z: 0.7071, w: 0.7071} (yaw 90°), stamp 1785460259.23
point:
  x: 0.022982125709143722
  y: 1.634838460127709
  z: 0.0

# ── 보조 측정 (사람 이동 후) ──
# yaw 0°, stamp 1785460255.91
point:
  x: 1.6509941418342378
  y: 0.00440672279725503
  z: 0.0
# yaw 90°, stamp 1785460270.53
point:
  x: -0.1369525628485981
  y: 1.2686292026986632
  z: 0.0
```

</details>

## 2026-07-31 09:33 — ✅ 103 passed (+12 신규), ruff 변경 파일 0건 (Claude)

- **명령**: `pytest ai/test/` + `ruff check target_position_node.py setup.py launch conftest.py test_target_position.py`
- **환경**: Windows 11 개발 PC, Python 3.12.12 (miniforge base), pytest 9.1.1, ruff 0.16.0
- **커밋**: develop `fab1f07` 이후 작업 트리 (target_position_node 신규, 커밋 전)
- **맥락**: **아키텍처 변경** — AI는 cmd_vel/RPM 생성에서 손을 떼고, SLAM(EM) 포즈
  + 카메라 방위각 + LiDAR 거리로 **사서의 지도 좌표(/target_position)를 발행**하는
  것까지만 담당. 경로 계획·모터는 EM(SLAM Nav→STM32)으로 이관.
  - `target_position_node.py` 신규: /target_person + /scan(BEST_EFFORT) + 카트
    포즈(PoseStamped, 토픽 계약 협의 중 — Known Gaps 2번) 구독 →
    PointStamped(frame=map) 발행. 미관측/거리 실패/포즈 stale 시 미발행.
  - 순수 함수 3종: `yaw_from_quaternion`, `robot_frame_bearing`(센서 보정 없는
    물리 방위각 — LiDAR 조회각과 구분), `target_position_in_map`.
    거리 측정은 control_node의 기존 순수 함수 재사용.
  - control_node/motor_node는 EM 재활용 예정으로 무수정 보존 (launch 데모용 유지).
  - **1차 수집 에러**: 상대 import가 pytest 단일 모듈 import와 충돌 →
    try/except 폴백으로 해결. conftest에 PointStamped/PoseStamped 스텁 추가.
  - 신규 테스트 12개: 쿼터니언→yaw 4, 물리 방위각 3, 지도 좌표 변환 5.
- **주의**: 실기 검증은 EM SLAM 포즈 토픽 확정 후 가능 (그 전에는 포즈 미수신
  경고와 함께 발행 보류가 정상).

<details>
<summary>pytest 출력 (마지막 줄)</summary>

```
============================= 103 passed in 0.11s =============================
```

</details>

## 2026-07-29 15:08 — ✅ 91 passed (+8 신규, 1차 1건 실패 후 수정), ruff 0건 (Claude)

- **명령**: `pytest ai/test/` + `ruff check reid_node.py reid_logic.py launch test_reid_logic.py`
- **환경**: Windows 11 개발 PC, Python 3.12.12 (miniforge base), pytest 9.1.1, ruff 0.16.0
- **커밋**: develop `2aec0ff` 이후 작업 트리 (재탐색 오인 방지 3종, 커밋 전)
- **맥락**: 실기 영상(result14_70.mp4) — threshold 0.70에서 6m 뒤 검은 옷 타인을
  SIM 0.915~0.966으로 오인 재잠금 (오인 후 force-add로 뱅크 오염 → 잠금 고착).
  - `candidate_is_feasible` 신규: 시공간 타당성 게이트 — 마지막 관측 대비
    중심 이동(300px/s + 60px 여유)과 크기 비율(높이=거리 프록시, 1.15 + 0.7/s)이
    경과 시간 내 도달 가능해야 재탐색 후보 자격. 장기 재등장은 자연히 무제한.
  - 재잠금 연속 확인: 같은 후보가 `recovery_confirm_frames`(10, 30fps 0.33초 /
    10fps 1초) 연속 수락 조건 충족 시에만 확정 (AutoSelectStabilizer 재사용).
  - 뱅크 오염 방지: 재잠금 직후 force-add 제거, `post_recovery_update_delay_sec`
    (2초) 동안 뱅크 갱신 유예.
  - similarity_threshold 기본 0.85→0.70 (게이트 조합 전제. launch `threshold:=`).
  - **1차 실행 1건 실패**: 경과 0초에서 크기 허용 폭이 정확히 1.0이라 bbox
    노이즈(1%)도 기각 → `size_ratio_base_tolerance`(1.15) 추가 후 통과.
  - 신규 테스트 8개: result14 재현 기각, 장기 재등장 허용, 중심 점프 시간
    의존, 크기 밴드 확장, 무효 입력, 음수 경과.
- **주의**: 실기 재검증 — result14 시나리오에서 배경 인물이 feasibility gate
  로그로 기각되는지, 진짜 재등장이 10프레임 확인 후 잡히는지.

<details>
<summary>pytest 출력 (마지막 줄)</summary>

```
============================= 91 passed in 0.12s ==============================
```

</details>

## 2026-07-29 14:48 — ✅ 83 passed (회귀), ruff 변경 파일 0건 (Claude)

- **명령**: `pytest ai/test/` + `ruff check follow_robot_launch.py`
- **환경**: Windows 11 개발 PC, Python 3.12.12 (miniforge base), pytest 9.1.1, ruff 0.16.0
- **커밋**: develop `2aec0ff` 이후 작업 트리 (threshold launch 인자, 커밋 전)
- **맥락**: 실기 임계값 실험용 launch 인자 추가 —
  `ros2 launch person_follow_robot follow_robot_launch.py threshold:=0.80`.
  `ParameterValue(value_type=float)`로 문자열 인자를 double 파라미터에 매핑
  (미사용 시 launch가 문자열로 넘겨 타입 오류 나는 것 방지). 순수 로직 변경
  없음 → 기존 83개 회귀만 확인. launch 인자 동작 자체는 Jetson 실기 확인 필요.

<details>
<summary>pytest 출력 (마지막 줄)</summary>

```
============================= 83 passed in 0.08s ==============================
```

</details>

## 2026-07-29 14:33 — ✅ 83 passed (+12 신규), ruff 변경 파일 0건 (Claude)

- **명령**: `pytest ai/test/` + `ruff check reid_node.py reid_logic.py launch test_reid_logic.py`
- **환경**: Windows 11 개발 PC, Python 3.12.12 (miniforge base), pytest 9.1.1, ruff 0.16.0
- **커밋**: develop `2aec0ff` 이후 작업 트리 (재인식 개선, 커밋 전)
- **맥락**: 실기 영상(result10.mp4) 분석 — 전신·정면 재등장에도 재인식 실패.
  원인: ①초근접(몸통 조각) 크롭으로 뱅크 등록 ②매 프레임 추가로 FIFO 뱅크가
  최근 0.7초 동일 모습만 보유 ③임계값 0.90 과도(재등장 동일인 기각, 타인은 ≤0.68).
  - `reid_logic.py` 신규 (순수): `crop_quality_ok`(좌우 잘림·초근접 배제,
    상하 접촉은 1m 추종 정상 상태라 허용), `accept_recovery`(임계값 + 1·2위 마진).
  - reid_node: 피처 추가 0.3초 샘플링(`feature_sample_interval_sec`, 재탐색
    성공 직후는 force), 크롭 품질 게이트를 등록·갱신·자동선택에 적용,
    임계값 0.90→0.85, `recovery_margin`=0.05.
  - AI_SPECIFICATIONS.md의 Memory Bank/Recovery 절 동기 갱신.
  - 신규 테스트 12개: 크롭 품질 6(잘림/초근접/상하 허용), 수락 판정 6(마진 포함).
- **주의**: 실기 재검증 필요 — result10.mp4와 같은 시나리오(초근접 등록 시도 →
  자동선택 보류되는지, 상실 후 전신 재등장 → 재인식되는지).

<details>
<summary>pytest 출력 (마지막 줄)</summary>

```
============================= 83 passed in 0.16s ==============================
```

</details>

## 2026-07-29 14:06 — ✅ 71 passed (+9 신규), ruff 변경 파일 0건 (Claude)

- **명령**: `pytest ai/test/` + `ruff check reid_node.py target_auto_select.py launch test_auto_select.py`
- **환경**: Windows 11 개발 PC, Python 3.12.12 (miniforge base), pytest 9.1.1, ruff 0.16.0
- **커밋**: develop `e724d6f` 이후 작업 트리 (타겟 자동 선택, 커밋 전)
- **맥락**: 요구사항 변경 — /select_target 수동 지정 대신 **최대 bbox(=최근접) 자동 선택**.
  - `target_auto_select.py` 신규 (순수 모듈): `largest_track`(최소 면적 필터 포함),
    `AutoSelectStabilizer`(N프레임 연속 최대일 때만 확정 — 스쳐 가는 오탐 방지).
  - reid_node: WAITING_SELECTION에서 자동 선택 시도, 확정 시 기존 2초 등록 흐름 재사용.
    /select_target은 수동 오버라이드로 유지. 파라미터 3개 신설
    (`auto_select_enabled`=True, `auto_select_stable_frames`=15, `auto_select_min_area_px`=5000).
  - reid_node 기존 lint 부채 정리 (UP035, D107×3, ANN401 noqa).
  - 신규 테스트 9개: 최대 면적 선택·최소 면적 필터(4), 안정화 확정·후보 교체
    리셋·소실 리셋·재무장·클램프(5).
- **주의**: 실기 검증 필요 — 여러 사람이 있을 때 카메라 앞 사람이 선택되는지,
  0.5초 확정 지연이 체감상 적절한지, min_area 기본값이 실카메라에서 맞는지.

<details>
<summary>pytest 출력 (마지막 줄)</summary>

```
============================= 71 passed in 0.07s ==============================
```

</details>

## 2026-07-28 15:35 — ✅ 62 passed (+3 신규), ruff 0건 (Claude)

- **명령**: `pytest ai/test/` + `ruff check motor_node.py test_motor_logic.py`
- **환경**: Windows 11 개발 PC, Python 3.12.12 (miniforge base), pytest 9.1.1, ruff 0.16.0
- **커밋**: `d915f86` 이후 작업 트리 (/wheel_speed_cmd 3원소 계약 반영, 커밋 전)
- **맥락**: EM이 JETSON_TO_STM.md 수신 규격을 `[제어종류, 좌 RPM, 우 RPM]`
  (0=모터, 1=LED)로 변경 → motor_node가 여전히 2원소 `[left, right]`를 발행해
  계약 불일치 상태였음.
  - `wheel_command_data()` 신규: 페이로드 조립을 순수 함수로 분리, 항상
    `[CMD_TYPE_MOTOR(0), left, right]` 발행. LED(1)는 예약 — motor_node 미사용.
  - 노드 CLAUDE.md 토픽 표·SYSTEM_ARCHITECTURE.md 동시 갱신 (계약 변경 규칙).
  - 신규 테스트 3개: 계약 레이아웃 일치, 정지 명령 `[0,0,0]`, int 강제.
- **주의**: STM32 수신은 micro-ROS 연결 후 실기에서 확인 필요
  (Int32MultiArray 구독자 메모리 사전 할당 필수 — EM 전달 완료).

<details>
<summary>pytest 출력 (마지막 줄)</summary>

```
============================= 62 passed in 0.12s ==============================
```

</details>

## 2026-07-28 11:32 — ✅ 59 passed (+19 신규), ruff 0건 (Claude)

- **명령**: `pytest ai/test/ -v` + `ruff check search_behavior.py test_search_logic.py`
- **환경**: Windows 11 개발 PC, Python 3.12.12 (miniforge base), pytest 9.1.1, ruff 0.16.0
- **커밋**: `5b9dea4`(develop) 이후 작업 트리 (탐색 상태머신 신규, 커밋 전)
- **맥락**: "사서 상실 → 마지막 위치 이동 → 사라진 방향 회전 탐색" 기능의
  프레임워크 독립 부분 선행 구현 (조립 전이라 순수 로직만).
  - `search_behavior.py` 신규: SearchBehavior 상태머신
    (TRACKING → GOTO_LAST → SEARCH_ROTATE → SEARCH_FAILED),
    `estimate_exit_direction`(bbox 이력 → 소실 방향), dead reckoning 거리 적분,
    장애물 시 전진 포기, 총 탐색 시간·최대 회전각 상한, 타겟 재관측 시 즉시 복귀.
  - **control_node 배선은 미포함** (실기 검증 불가) — 조립 후 연결.
  - 신규 테스트 19개: 방향 추정 5(속도/위치 폴백/중앙 소실), 진입 분기 3,
    GOTO_LAST 5(정렬→전진 순서, 적분 도착, 장애물 중단), 회전 2(방향·상한),
    전역 규칙 4(재관측 복귀, 총 타임아웃, 비활성 0 출력, dt<=0 안전).

<details>
<summary>pytest 출력 (마지막 줄)</summary>

```
============================= 59 passed in 0.11s ==============================
```

</details>

## 2026-07-28 10:54 — ✅ 40 passed (이동 후 회귀), ruff 0건 (Claude)

- **명령**: `pytest ai/test/` + `pytest`(testpaths 기본값) + `ruff check ai/test/`
- **환경**: Windows 11 개발 PC, Python 3.12.12 (miniforge base), pytest 9.1.1, ruff 0.16.0
- **커밋**: `5b9dea4`(develop) 이후 작업 트리 (테스트 디렉토리 이동, 커밋 전)
- **맥락**: AI 테스트를 루트 `tests/` → `ai/test/`로 이동 (루트는 파트 공통 규칙·공용
  로그만 유지). conftest.py의 노드 import 경로를 새 위치 기준으로 수정하고
  pyproject.toml `testpaths`를 `ai/test`로 변경. develop 머지에서 깨졌던
  TEST_LOG.md(충돌 마커 잔재 3곳, FE/BE 항목이 AI 항목 details 안에 끼어듦)를
  분리·복구 — FE/BE(Codex) 항목 4건은 루트 tests/TEST_LOG.md로 원복.
  두 실행 경로(명시 경로·기본 설정) 모두에서 40개 통과 확인.

<details>
<summary>pytest 출력 (마지막 줄)</summary>

```
============================= 40 passed in 0.09s ==============================
```

</details>

## 2026-07-28 09:55 — ✅ 40 passed (+11 신규), ruff 변경 파일 0건 (Claude)

- **명령**: `pytest tests/ -v` + `ruff check control_node.py follow_robot_launch.py test_control_logic.py`
- **환경**: Windows 11 개발 PC, Python 3.12.12 (miniforge base), pytest 9.1.1, ruff 0.16.0
- **커밋**: `53d8f01` 이후 작업 트리 (bbox 폭 조회창 + 드롭아웃 유예, 커밋 전)
- **맥락**: 실기 영상(result_LiDAR_calibration.mp4) 분석 결과 — 타겟이 화면
  우측일 때 조회 광선이 몸을 빗나가 배경(7.3m)을 재거나 NO LIDAR 발생.
  원인: ±2인덱스(±1°) 초협소 조회창 + 미캘리브레이션 오프셋.
  - `min_valid_range_in_span` 신규: bbox 각도 폭 범위의 유효 range **최소값**
    (가장 가까운 표면=사람) 채택. 평균 방식 대체. 360° 순환 인덱스 지원.
  - `bbox_half_span_rad` 신규: bbox 픽셀 폭 → 각도 반폭 환산 (`bbox_span_scale`
    파라미터로 가장자리 배경 광선 배제, 기본 0.8).
  - 드롭아웃 유예: 측정 실패 시 `distance_grace_period_sec`(기본 0.5s) 동안
    직전 유효 거리 유지.
  - 신규 테스트 11개: 반폭 환산(4) + 범위 조회(7: 최소값 선택, 부분 드롭아웃
    생존, 전체 무효, 스캔 없음, 경계 순환, 최소 창 보존, 무효값 필터).
- **주의**: 실기 검증 필요 — 우측 7.3m 오답과 NO LIDAR 빈도가 줄었는지 영상 재확인.

<details>
<summary>pytest 출력 (마지막 줄)</summary>

```
============================= 40 passed in 0.04s ==============================
```

</details>

## 2026-07-28 09:21 — ✅ 29 passed (+3 신규), ruff 변경 파일 0건 (Claude)

- **명령**: `pytest tests/ -v` + `ruff check control_node.py follow_robot_launch.py test_control_logic.py`
- **환경**: Windows 11 개발 PC, Python 3.12.12 (miniforge base), pytest 9.1.1, ruff 0.16.0
- **커밋**: `53d8f01` 기준 작업 트리 (lidar_mirrored 보정, 커밋 전)
- **맥락**: 실기 증상 — 타겟이 화면 왼쪽이면 오른쪽 저편 물체의 거리가,
  오른쪽이면 왼쪽 물체의 거리가 잡힘 (중앙은 정상) = LiDAR 각도 축 좌우 반전.
  - `camera_bearing_to_lidar_angle`에 `mirrored` 인자 추가 (방위각 부호 반전,
    장착 오프셋은 반전 후 적용). REP 103 기본 동작(mirrored=False)은 불변.
  - control_node `lidar_mirrored` 파라미터(기본 True, 실측 반영) + launch 반영.
  - 신규 테스트 3개: mirrored 중앙=0(대칭점 불변), 좌우 반전, 오프셋과의 결합 순서.
- **주의**: 좌우 반전은 실기에서 방향이 맞는지 최종 확인 필요. LiDAR 장착이나
  드라이버 reversion 설정을 바꾸면 lidar_mirrored 재검증.

<details>
<summary>pytest 출력 (마지막 줄)</summary>

```
============================= 29 passed in 0.08s ==============================
```

</details>

## 2026-07-28 09:07 — ✅ 26 passed, ruff 변경 파일 0건 (Claude)

- **명령**: `pytest tests/` + `ruff check debug_visualization_node.py`
- **환경**: Windows 11 개발 PC, Python 3.12.12 (miniforge base), pytest 9.1.1, ruff 0.16.0
- **커밋**: `53d8f01` 기준 작업 트리 (상태 배너 하단 이동·축소, 커밋 전)
- **맥락**: 상단 상태 배너(Re-ID Debug | Tracks | TARGET | DIST)가 바운딩박스
  거리 라벨을 가리는 문제. `_draw_banner`에 scale/thickness 파라미터 추가
  (기본값은 RECOVERED 오버레이용 1.1/3 유지), 상태 배너만 0.55/1로 축소해
  프레임 하단(왼쪽)으로 이동. cv2 그리기 로직 → 기존 26개 회귀만 확인.

<details>
<summary>pytest 출력 (마지막 줄)</summary>

```
============================= 26 passed in 0.04s ==============================
```

</details>

## 2026-07-28 08:53 — ✅ 26 passed, ruff 변경 파일 0건 (Claude)

- **명령**: `pytest tests/` + `ruff check debug_visualization_node.py`
- **환경**: Windows 11 개발 PC, Python 3.12.12 (miniforge base), pytest 9.1.1, ruff 0.16.0
- **커밋**: `53d8f01` 기준 작업 트리 (라벨 화면 안 clamp, 커밋 전)
- **맥락**: 바운딩박스가 프레임 밖으로 나가면 거리/ID 라벨이 화면 밖에 그려져
  보이지 않는 문제 수정. `_draw_label`(모든 라벨 공통 진입점)에서 배경 사각형이
  프레임 안에 완전히 들어오도록 x·y를 clamp. cv2 의존 그리기 로직이라 순수 테스트
  없음 → 기존 26개 회귀만 확인, 표시 확인은 Jetson 실기.

<details>
<summary>pytest 출력 (마지막 줄)</summary>

```
============================= 26 passed in 0.03s ==============================
```

</details>

## 2026-07-28 08:42 — ✅ 26 passed, ruff 변경 파일 0건 (Claude)

- **명령**: `pytest tests/` + `ruff check control_node.py conftest.py`
- **환경**: Windows 11 개발 PC, Python 3.12.12 (miniforge base), pytest 9.1.1, ruff 0.16.0
- **커밋**: `53d8f01` 기준 작업 트리 (/scan QoS 수정, 커밋 전)
- **맥락**: Jetson 실기에서 영상에 `NO LIDAR`가 찍힌 문제 수정 검증.
  원인: ydlidar 드라이버는 BEST_EFFORT(sensor QoS)로 발행하는데 control_node가
  기본 RELIABLE로 구독 → QoS 비호환으로 /scan 미수신.
  - control_node: /scan 구독을 `qos_profile_sensor_data`(BEST_EFFORT)로 변경.
  - 거리 획득 실패 경고에 원인 구분 추가 (/scan 미수신 vs 유효 range 없음).
  - conftest.py에 `rclpy.qos` 스텁 추가 (미추가 시 import 실패).
  - 순수 로직 변경 없음 → 기존 26개 회귀 확인. QoS 매칭 자체는 Jetson 실기 검증 필요.

<details>
<summary>pytest 출력 (마지막 줄)</summary>

```
============================= 26 passed in 0.06s ==============================
```

</details>

## 2026-07-27 17:30 — ✅ 26 passed, ruff 변경 파일 0건 (Claude)

- **명령**: `pytest tests/ -v` + `ruff check control_node.py debug_visualization_node.py`
- **환경**: Windows 11 개발 PC, Python 3.12.12 (miniforge base), pytest 9.1.1, ruff 0.16.0
- **커밋**: `36cc4dd` 기준 작업 트리 (거리 표시 NaN 폴백 추가, 커밋 전)
- **맥락**: 실기에서 result.mp4에 거리 라벨이 안 찍힌 문제의 후속 수정 검증.
  원인 추정: LiDAR 거리 측정 실패 시 `/target_distance`를 아예 발행하지 않아
  디버그 노드가 표시할 데이터가 없었음.
  - control_node: 타겟이 보이는데 측정 실패면 NaN 발행 (미검출 시엔 여전히 미발행).
  - debug_visualization_node: NaN → 박스 우상단 `NO LIDAR`, 수신 없음 → 배너 `DIST: --`,
    정상 → `X.XXm`. 상단 배너에 `DIST:` 항목 상시 추가.
  - 순수 로직 변경 없음 → 기존 26개로 회귀 확인. 실기 검증은 Jetson에서 필요.

<details>
<summary>pytest 출력 (마지막 8줄)</summary>

```
tests/test_motor_logic.py::TestValidation::test_negative_max_rpm_raises PASSED [ 80%]
tests/test_pid.py::test_proportional_term_only PASSED                    [ 84%]
tests/test_pid.py::test_output_is_clamped_to_limit PASSED                [ 88%]
tests/test_pid.py::test_integral_accumulates_over_time PASSED            [ 92%]
tests/test_pid.py::test_derivative_responds_to_error_change PASSED       [ 96%]
tests/test_pid.py::test_zero_dt_disables_derivative PASSED               [100%]

============================= 26 passed in 0.05s ==============================
```

</details>

## 2026-07-27 17:11 — ✅ 26 passed, ruff 변경 파일 0건 (Claude)

- **명령**: `pytest tests/ -v` + `ruff check <변경 파일들>`
- **환경**: Windows 11 개발 PC, Python 3.12.12 (miniforge base), pytest 9.1.1, ruff 0.16.0
- **커밋**: `36cc4dd` 기준 작업 트리 (디버그 영상 거리 표시 기능, 커밋 전)
- **맥락**: 디버그 영상의 타겟 바운딩박스 우상단에 LiDAR 측정 거리(m) 표시 기능 검증.
  - control_node: 측정 거리를 `/target_distance`(std_msgs/Float32)로 발행.
  - debug_visualization_node: 구독 후 타겟 박스 우상단에 `X.XXm` 라벨
    (staleness 타임아웃 `distance_display_timeout_sec`=1s 초과 시 숨김).
  - conftest.py 스텁에 `Float32` 추가 — 추가 전에는 control_node import 실패로
    테스트 수집 자체가 깨졌음 (해당 실행도 아래 이력 참조).
  - 새 순수 로직 없음(발행/구독+cv2 그리기) → 신규 pytest 케이스 없이 기존 26개로 회귀 확인.
- **ruff**: 변경 파일(control_node·debug_visualization_node·launch·conftest) `All checks passed!`
  (debug_visualization_node의 기존 lint 이슈 — frame 타입 힌트, import 정렬, docstring —
  이번 기회에 함께 정리. `ruff format --check`의 저장소 기존 포맷 드리프트는 미변경.)

<details>
<summary>1차 실행 — ❌ 수집 에러 (conftest 스텁에 Float32 부재)</summary>

```
ERROR collecting tests/test_control_logic.py
ai\src\person_follow_robot\person_follow_robot\control_node.py:29: in <module>
    from std_msgs.msg import Float32
E   ImportError: cannot import name 'Float32' from 'std_msgs.msg' (unknown location)
ERROR collecting tests/test_pid.py
    (동일 원인)
!!!!!!!!!!!!!!!!!!! Interrupted: 2 errors during collection !!!!!!!!!!!!!!!!!!!
============================== 2 errors in 0.17s ==============================
```

</details>

<details>
<summary>2차 실행 — pytest 전체 출력</summary>

```
============================= test session starts =============================
platform win32 -- Python 3.12.12, pytest-9.1.1, pluggy-1.6.0 -- C:\Users\SSAFY\miniforge3\python.exe
cachedir: .pytest_cache
rootdir: C:\SSAFY\workspace\Choll
configfile: pyproject.toml
plugins: anyio-4.14.1
collecting ... collected 26 items

tests/test_control_logic.py::TestNormalizeCenterX::test_image_center_maps_to_zero PASSED [  3%]
tests/test_control_logic.py::TestNormalizeCenterX::test_left_edge_maps_to_minus_one PASSED [  7%]
tests/test_control_logic.py::TestNormalizeCenterX::test_right_edge_maps_to_plus_one PASSED [ 11%]
tests/test_control_logic.py::TestNormalizeCenterX::test_quarter_position PASSED [ 15%]
tests/test_control_logic.py::TestNormalizeCenterX::test_out_of_frame_is_clamped PASSED [ 19%]
tests/test_control_logic.py::TestNormalizeCenterX::test_non_positive_width_raises PASSED [ 23%]
tests/test_control_logic.py::TestCameraBearingToLidarAngle::test_center_maps_to_zero PASSED [ 26%]
tests/test_control_logic.py::TestCameraBearingToLidarAngle::test_right_edge_is_negative_half_fov PASSED [ 30%]
tests/test_control_logic.py::TestCameraBearingToLidarAngle::test_left_edge_is_positive_half_fov PASSED [ 34%]
tests/test_control_logic.py::TestCameraBearingToLidarAngle::test_mount_offset_shifts_lookup_angle PASSED [ 38%]
tests/test_control_logic.py::TestPidReset::test_reset_clears_integral_and_derivative_state PASSED [ 42%]
tests/test_motor_logic.py::TestStraightLine::test_forward_gives_equal_positive_rpms PASSED [ 46%]
tests/test_motor_logic.py::TestStraightLine::test_backward_gives_equal_negative_rpms PASSED [ 50%]
tests/test_motor_logic.py::TestRotation::test_left_turn_makes_right_wheel_faster PASSED [ 53%]
tests/test_motor_logic.py::TestRotation::test_spin_in_place_wheels_are_opposite PASSED [ 57%]
tests/test_motor_logic.py::TestClamping::test_peak_clamped_to_max_rpm PASSED [ 61%]
tests/test_motor_logic.py::TestClamping::test_clamp_preserves_left_right_ratio PASSED [ 65%]
tests/test_motor_logic.py::TestClamping::test_zero_command_is_zero PASSED [ 69%]
tests/test_motor_logic.py::TestValidation::test_non_positive_radius_raises PASSED [ 73%]
tests/test_motor_logic.py::TestValidation::test_non_positive_separation_raises PASSED [ 76%]
tests/test_motor_logic.py::TestValidation::test_negative_max_rpm_raises PASSED [ 80%]
tests/test_pid.py::test_proportional_term_only PASSED                    [ 84%]
tests/test_pid.py::test_output_is_clamped_to_limit PASSED                [ 88%]
tests/test_pid.py::test_integral_accumulates_over_time PASSED            [ 92%]
tests/test_pid.py::test_derivative_responds_to_error_change PASSED       [ 96%]
tests/test_pid.py::test_zero_dt_disables_derivative PASSED               [100%]

============================= 26 passed in 0.03s ==============================
```

</details>

## 2026-07-24 16:43 — ✅ 26 passed, ruff 변경 파일 0건 (Claude)

- **명령**: `pytest tests/ -v` + `ruff check <변경 파일들>`
- **환경**: Windows 11 개발 PC, Python 3.12.12 (miniforge base), pytest 9.1.1, ruff 0.16.0
- **맥락**: motor_node 차동구동 역기구학 구현(+14 테스트) 및 control_node LiDAR 조회
  각도 부호 버그 수정(+카메라 방위각→LiDAR 각도 변환 함수 분리) 검증.
  - `test_motor_logic.py` 신규 11개: 직진/후진 RPM, 좌회전 시 오른쪽 바퀴 가속(REP 103),
    제자리 회전 부호, max_rpm 클램핑(좌우 비율 보존), 입력 검증.
  - `test_control_logic.py`에 `camera_bearing_to_lidar_angle` 4개 추가: 중앙=0,
    화면 오른쪽=음의 방위각, 장착 오프셋 반영.
- **ruff**: 변경 파일(motor_node·control_node·launch·tests/) 기준 `All checks passed!`
  (저장소 전체에는 다른 노드의 기존 이슈 잔존)

<details>
<summary>pytest 전체 출력</summary>

```
============================= test session starts =============================
platform win32 -- Python 3.12.12, pytest-9.1.1, pluggy-1.6.0 -- C:\Users\SSAFY\miniforge3\python.exe
cachedir: .pytest_cache
rootdir: C:\SSAFY\workspace\Choll
configfile: pyproject.toml
plugins: anyio-4.14.1
collecting ... collected 26 items

tests/test_control_logic.py::TestNormalizeCenterX::test_image_center_maps_to_zero PASSED [  3%]
tests/test_control_logic.py::TestNormalizeCenterX::test_left_edge_maps_to_minus_one PASSED [  7%]
tests/test_control_logic.py::TestNormalizeCenterX::test_right_edge_maps_to_plus_one PASSED [ 11%]
tests/test_control_logic.py::TestNormalizeCenterX::test_quarter_position PASSED [ 15%]
tests/test_control_logic.py::TestNormalizeCenterX::test_out_of_frame_is_clamped PASSED [ 19%]
tests/test_control_logic.py::TestNormalizeCenterX::test_non_positive_width_raises PASSED [ 23%]
tests/test_control_logic.py::TestCameraBearingToLidarAngle::test_center_maps_to_zero PASSED [ 26%]
tests/test_control_logic.py::TestCameraBearingToLidarAngle::test_right_edge_is_negative_half_fov PASSED [ 30%]
tests/test_control_logic.py::TestCameraBearingToLidarAngle::test_left_edge_is_positive_half_fov PASSED [ 34%]
tests/test_control_logic.py::TestCameraBearingToLidarAngle::test_mount_offset_shifts_lookup_angle PASSED [ 38%]
tests/test_control_logic.py::TestPidReset::test_reset_clears_integral_and_derivative_state PASSED [ 42%]
tests/test_motor_logic.py::TestStraightLine::test_forward_gives_equal_positive_rpms PASSED [ 46%]
tests/test_motor_logic.py::TestStraightLine::test_backward_gives_equal_negative_rpms PASSED [ 50%]
tests/test_motor_logic.py::TestRotation::test_left_turn_makes_right_wheel_faster PASSED [ 53%]
tests/test_motor_logic.py::TestRotation::test_spin_in_place_wheels_are_opposite PASSED [ 57%]
tests/test_motor_logic.py::TestClamping::test_peak_clamped_to_max_rpm PASSED [ 61%]
tests/test_motor_logic.py::TestClamping::test_clamp_preserves_left_right_ratio PASSED [ 65%]
tests/test_motor_logic.py::TestClamping::test_zero_command_is_zero PASSED [ 69%]
tests/test_motor_logic.py::TestValidation::test_non_positive_radius_raises PASSED [ 73%]
tests/test_motor_logic.py::TestValidation::test_non_positive_separation_raises PASSED [ 76%]
tests/test_motor_logic.py::TestValidation::test_negative_max_rpm_raises PASSED [ 80%]
tests/test_pid.py::test_proportional_term_only PASSED                    [ 84%]
tests/test_pid.py::test_output_is_clamped_to_limit PASSED                [ 88%]
tests/test_pid.py::test_integral_accumulates_over_time PASSED            [ 92%]
tests/test_pid.py::test_derivative_responds_to_error_change PASSED       [ 96%]
tests/test_pid.py::test_zero_dt_disables_derivative PASSED               [100%]

============================= 26 passed in 0.06s ==============================
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
