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

## 2026-08-08 12:00 — ✅ EM+ROS2 실기: 보정 후 1m 직진 x2 재검증 — 거리 +0.15% 확인 / ⚠️ yaw drift는 오히려 +67.5% 증가 (relu 실기 / Claude 분석)

- **배경**: 11:00 항목에서 `wheel_radius_m` 을 0.065 → **0.0587** 로 보정한 뒤, 같은 1 m 직진을
  2회 재수행했다. **코드는 수정하지 않았다**(사용자 지시: 분석·기록만).
- 대상 커밋: `1a1f7a5` (working tree)

### 실측 (relu, 실기)

| 회차 | 시작 (x, y, yaw) | 종료 (x, y, yaw) | Δx | Δy | **보고 `\|Δ\|`** | Δyaw |
|---|---|---|---|---|---|---|
| 1 | -0.607, 0.411, -0.584 | 0.159, -0.219, -0.781 | +0.766 | -0.630 | **0.9918** | -0.197 (-11.3°) |
| 2 | -0.546, 0.407, -0.653 | 0.196, -0.280, -0.863 | +0.742 | -0.687 | **1.0112** | -0.210 (-12.0°) |

실제 이동거리는 2회 모두 약 1.0 m 직진.

### ✅ 결과 1 — 거리 스케일 보정 확인

평균 보고 이동거리 **1.0015 m** → 오차 **+0.15%**. `wheel_radius_m=0.0587` 과
`counts_per_wheel_rev=68160` 조합은 거리에 대해 맞는다. 보정 전 +10.7% 에서 해소됐다.

### ⚠️ 결과 2 — yaw drift 는 줄지 않고 **커졌다** (예측 빗나감)

11:00 항목에서 "반지름 보정으로 보고 drift 가 약 9.7% 축소될 것"이라고 예측했으나,
**실제로는 정반대로 커졌다.**

비교는 **곡률 `κ = Δyaw / d_c` (rad/m)** 로 해야 한다 — `Δθ` 와 `d_c` 가 둘 다 `r` 에
비례하므로 **`κ` 와 `d_L/d_R` 은 `r` 에 무관**하고, 따라서 보정 전후를 직접 비교할 수 있다.

| 회차 (시간 순) | r | 보고 `\|Δ\|` | Δyaw | **κ (rad/m)** | **d_L/d_R** |
|---|---|---|---|---|---|
| S1-1 | 0.065 | 1.1012 | -0.095 | -0.0863 | +3.33% |
| S1-2 | 0.065 | 1.1136 | -0.161 | -0.1446 | +5.65% |
| S1-3 | 0.065 | 1.1055 | -0.147 | -0.1330 | +5.18% |
| S2-1 | 0.0587 | 0.9918 | -0.197 | -0.1986 | +7.84% |
| S2-2 | 0.0587 | 1.0112 | -0.210 | -0.2077 | +8.22% |
| **세션1** | | 1.1068 | -0.1343 | **-0.1213** | **+4.72%** |
| **세션2** | | 1.0015 | -0.2035 | **-0.2032** | **+8.03%** |

**κ 가 +67.5% 증가**했다. κ 는 `r` 에 무관하므로 **보정 탓이 아니라 물리적 좌우 비대칭
자체가 커진 것**이다. 회차별로도 3.33 → 5.65 → 5.18 → 7.84 → 8.22% 로 대체로 증가한다.

### 분석

**관측 1 — 비대칭은 상수가 아니다.** 좌우 엔코더 counts/rev 차이나 바퀴 지름 차이는
**상수여야 하는데 관측은 상수가 아니다.** 고정 원인의 설명력이 떨어지고, 슬립·마찰·기구
헐거워짐·속도 의존 edge 누락처럼 **조건에 따라 변하는 원인**이 남는다.
(표본 5개이고 S1-3 < S1-2 이므로 "단조 증가"로 단정하지는 않는다.)

**관측 2 — 공통 성분은 안정, 차동 성분만 증가.** `r=0.065` 기준 환산:

| | 공통 `d_c` | 차동 `d_L - d_R` | d_L | d_R |
|---|---|---|---|---|
| 세션1 | 1.1068 | 0.0510 | 1.1323 | 1.0813 |
| 세션2 | 1.1090 (**+0.2%**) | 0.0856 (**+68%**) | 1.1518 | 1.0662 |

**평균은 그대로인데 좌우가 평균을 중심으로 대칭적으로 벌어졌다.** 이것은 **실제로 원호를
그렸을 때의 서명**이다 — 원호에서는 바깥 바퀴가 더 가고 안쪽이 덜 가며 **평균 = 경로 길이**다.
한쪽 센서만 틀렸다면 평균도 함께 움직였어야 한다.

**관측 3 — 실제로 휠 메커니즘이 존재한다.** `motor_config.h` 의 `MOTOR_PI_KP`/`MOTOR_PI_KI`
가 **아직 0.0f** 이다(문서 `current.md:67` 에도 명시). 즉 STM 은 바퀴 속도를 **폐루프로 맞추지
않고 Feedforward(개루프)만** 쓴다. 좌우 모터·기어박스·마찰이 조금만 달라도 같은 목표 rad/s 에서
**실제 속도가 달라져 카트가 실제로 휜다.** 배터리 전압 변화로 불균형이 변할 수 있어 관측 1과도
맞는다.

→ **현재 가장 유력한 가설: 카트가 실제로 우측으로 휘고 있고 오도메트리는 그것을 옳게 보고하고
있다.** 그렇다면 오도메트리 버그가 아니라 **구동계 불균형**이며, 해결도 `wheel_separation_m` 이
아니라 **PI 속도 제어 튜닝**이다.

**관측 4 — 자로 재면 바로 판별된다.** 원호 가정 시 1 m 주행 후:

| | 곡률반경 | **횡방향 이탈** | **최종 방위** |
|---|---|---|---|
| 세션1 | 8.25 m | **6.1 cm** | 6.9° |
| 세션2 | 4.92 m | **10.1 cm** | 11.6° |

10 cm 이탈과 11.6° 기울어짐은 **눈으로 보인다.** 실제로 벗어나 있으면 오도메트리는 정상이다.

### 다음 실측(raw encoder)에서 기록할 값

⚠️ **raw count 만으로는 결론이 나지 않는다** — 오도메트리 `Δθ` 가 애초에 그 count 에서 나온
값이라 `ΔL/ΔR ≈ 1.08` 은 산술적으로 반드시 나온다. **바닥 기준 ground truth 를 함께 재야**
새 정보가 생긴다. 가장 깨끗한 실험은 **모터 끄고 벽·직선자를 따라 밀기**(좌우 지면 이동거리가
같음이 보장됨) → 그 조건의 `ΔL/ΔR` 은 센서·기구 비대칭만 담는다.

기록 항목·계산식·기준값(**184,804 count/m**)은 `ros2_ws/CLAUDE.md`
"다음 실측: raw `encoder_total` 측정에서 기록할 값" 절에 정리했다.

### 변경 파일

| 파일 | 변경 |
|---|---|
| `ros2_ws/CLAUDE.md` | 보정 후 재검증 결과 + drift 분석 전면 개정 + 다음 측정 기록 항목 |
| `tests/TEST_LOG.md` | 이 항목 |

**코드·파라미터는 변경하지 않았다** — `wheel_radius_m`(0.0587), `wheel_separation_m`(0.38),
`counts_per_wheel_rev`(68160), STM 펌웨어 모두 그대로다.

<details>
<summary>분석 계산 원본 출력</summary>

```
=== 회차별 (시간 순) ===
run   |  r     | 보고|Δ| | Δyaw   | 곡률 κ=Δyaw/d_c | d_L/d_R  | r=0.065 환산 d_c
S1-1 | 0.0650 | 1.1012  | -0.095 |   -0.08627      | 1.03333 (+3.33%) | 1.1012
S1-2 | 0.0650 | 1.1136  | -0.161 |   -0.14458      | 1.05649 (+5.65%) | 1.1136
S1-3 | 0.0650 | 1.1055  | -0.147 |   -0.13297      | 1.05184 (+5.18%) | 1.1055
S2-1 | 0.0587 | 0.9918  | -0.197 |   -0.19863      | 1.07844 (+7.84%) | 1.0982
S2-2 | 0.0587 | 1.0112  | -0.210 |   -0.20767      | 1.08216 (+8.22%) | 1.1197

세션1 (08-08 오전): 보고 d_c=1.1068, r=0.065환산 d_c=1.1068, κ=-0.12127 rad/m, d_L/d_R=+4.72%
세션2 (보정 후): 보고 d_c=1.0015, r=0.065환산 d_c=1.1090, κ=-0.20315 rad/m, d_L/d_R=+8.03%

=== 핵심 ===
곡률 κ (r 무관): 세션1 -0.12127 -> 세션2 -0.20315   (+67.5%)
세션1 (r=0.065 환산): 공통 d_c=1.1068,  차동 d_L-d_R=0.05100,  d_L=1.1323, d_R=1.0813
세션2 (r=0.065 환산): 공통 d_c=1.1090,  차동 d_L-d_R=0.08561,  d_L=1.1518, d_R=1.0662

=== 실제로 휘었다면 관측돼야 할 값 (원호 가정) ===
세션1: 곡률반경 8.25 m -> 1 m 주행 시 횡방향 이탈 6.1 cm, 최종 방위 6.9°
세션2: 곡률반경 4.92 m -> 1 m 주행 시 횡방향 이탈 10.1 cm, 최종 방위 11.6°

=== 다음 측정의 기준값 ===
현 설정 counts/m (좌우 공통) = 184,804
세션2 비대칭(+8.03%)이 그대로 재현될 경우 1 m 주행 예상치:
  ΔL ≈ 191,938   ΔR ≈ 177,671   평균 184,804  비 1.08030
```

</details>

### ⚠️ 이 기록의 한계

- **방위 ground truth 는 여전히 없다.** 거리만 확인됐고 실제 횡방향 이탈·최종 기울기는
  측정되지 않았다. 관측 2·3의 "실제로 휜다" 가설은 **아직 검증되지 않은 가설**이다.
- **표본 5개**(세션1 3 + 세션2 2). 세션 간 조건 차이(속도 프로파일, 하중, 배터리, 바닥)가
  기록되지 않아 관측 1의 원인을 좁힐 수 없다.
- **회차 사이 카트 재정렬 여부가 기록되지 않았다.** 오도메트리 yaw 가 5회에 걸쳐
  -0.096 → -0.863(누적 약 -44°)로 단조 누적되는데, 카트를 매번 물리적으로 다시 정렬했다면
  이는 오도메트리 쪽 오차를 시사하고, 정렬하지 않았다면 카트가 실제로 44° 돌아 있어야 한다.
- 관측 3의 PI 게인 0.0f 는 **코드·문서 확인 결과**이며, 그것이 실제로 좌우 속도차를 만드는지는
  **측정하지 않았다.**

## 2026-08-08 11:00 — ✅ EM+ROS2 실기: Wheel Odometry 1m 직진 x3 → 거리 스케일 보정(r 0.065→0.0587), 538 tests 통과 / ⚠️ yaw drift 원인 미확정 (relu 실기 / Claude 분석·반영)

- **배경**: 앞 항목(10:00)의 `wheel_odometry` 노드를 **실제 하드웨어**에서 처음 검증했다.
  1 m 직진을 3회 수행하고 시작/종료 포즈를 기록했다.
- 대상 커밋: `1a1f7a5` (working tree)

### 실측 (relu, 실기)

| 회차 | 시작 (x, y, yaw) | 종료 (x, y, yaw) | Δx | Δy | Δyaw | **보고 `\|Δ\|`** |
|---|---|---|---|---|---|---|
| 1 | 0.102, 0.374, -0.096 | 1.197, 0.257, -0.191 | +1.095 | -0.117 | -0.095 | **1.1012** |
| 2 | 0.123, 0.479, -0.169 | 1.207, 0.224, -0.330 | +1.084 | -0.255 | -0.161 | **1.1136** |
| 3 | 0.172, 0.496, -0.237 | 1.229, 0.172, -0.384 | +1.057 | -0.324 | -0.147 | **1.1055** |

실제 이동거리는 3회 모두 약 **1.0 m 직진**.

- **거리**: 평균 배율 **1.1068** → 오도메트리가 약 **10.7% 크게** 보고. 3회 모두 재현.
- **yaw**: 3회 모두 **음(-) 방향**으로 drift. 평균 -0.1343 rad/m.

시작 방위가 0이 아니므로(-0.096 / -0.169 / -0.237) `Δx` 가 아니라 **변위 크기 `|Δ|`** 로
비교했다(회전 불변). 보고 경로가 휘어 호 길이가 현보다 길지만 차이는 **0.1% 미만**이라
무시했다(호 보정 시 r 이 0.046 mm 달라질 뿐 — 측정 스프레드 ±0.56%보다 훨씬 작다).

### 1. 거리 스케일 보정 (적용함)

```
r_new = 0.065 / 1.106788 = 0.058728  →  채택 0.0587   (잔차 -0.05%)
```

**오도메트리 설정에만 적용**했다. `counts_per_wheel_rev=68160` 과 STM 펌웨어 77520 은
지시대로 **변경하지 않았다.**

⚠️ **이 0.0587 은 "바퀴 반지름 실측치"가 아니다.** 거리에는 `2*pi*r / counts_per_rev` 라는
**곱만** 들어가므로 직진 시험으로 r 과 counts_per_rev 를 분리할 수 없다. (유효 구름반지름 +
슬립 + 엔코더 스케일 오차)를 전부 흡수한 **보정 상수**다.

⚠️ **브리지의 `wheel_radius_m` 은 0.065 로 유지**했다(의도적 분리):

- 브리지의 r 은 `/cmd_vel`(m/s) -> 바퀴 rad/s 변환에 쓰는 **명목 기구 치수**이며 엔코더가
  전혀 개입하지 않는 개루프 명령 경로다.
- `r=0.065` 를 참으로 두면 이번 데이터가 가리키는 유효 counts/rev 는 약 **75,439** 로,
  손회전 실측 68,160 보다 **펌웨어 명목 77,520 에 훨씬 가깝다**(2.7% 차이).
  즉 10.7% 의 상당 부분이 반지름이 아니라 **미해결 엔코더 스케일**일 가능성이 있다.
- 명령 경로에 옮기면 실제 주행 속도와 속도 봉투 표(4.615/1.754/6.369)가 모두 바뀐다.

두 파일의 `wheel_radius_m` 이 갈렸으므로, 기존 "두 YAML 일치" 테스트에서 이 키를 빼고
**"의도적으로 다르다"를 명시적으로 고정하는 테스트**로 교체했다.
`wheel_separation_m`·`counts_per_wheel_rev` 는 계속 일치를 강제한다.

### 2. yaw drift — 분석만, 코드 수정 없음 (지시대로)

`Δθ = (d_R - d_L) / L` 이므로 이것은 각도 문제가 아니라 **좌우 이동거리 차이** 문제다:

```
d_L - d_R = 0.1343 x 0.38 = 0.051 m   ->   d_L=1.1323, d_R=1.0813   (좌우 4.72% 차이)
```

**`wheel_separation_m` 은 원인이 될 수 없다** — `d_L = d_R` 이면 `L` 이 얼마든 `Δθ = 0` 이다.
`L` 을 바꾸면 drift 의 **표시 크기만** 줄고 원인은 남은 채 **진짜 회전까지 왜곡**된다.
(지시하신 "임의로 바꾸지 말 것"이 맞다.)

⚠️ **이번 반지름 보정으로 보고 drift 가 약 9.7% 작아진다**(`Δθ` 도 r 에 비례,
-0.1343 → 약 -0.1213). **개선이 아니라 눈금이 줄어든 것**이다.

원인 후보와 다음 실측 순서는 `ros2_ws/CLAUDE.md` "직진 시 yaw drift" 절에 정리했다.
요지: ① 바퀴 지름 실측(가장 싸고 결정적) → ② 3~5 m 주행으로 **실제 방위 ground truth** 확보
(현재 거리만 확인됐고 방위는 미측정 — "실제로 안 직진했을" 가능성이 배제되지 않았다) →
③ raw `encoder_total` 로 좌우 델타 직접 측정 → ④ 모터 끄고 밀기 → ⑤ 후진 → ⑥ 속도·하중 변경.
`L` 캘리브레이션(360° 회전)은 **좌우 스케일 정리 후에** 한다 — 순서를 바꾸면 두 오차가
서로를 가린다.

참고 정황: `r=0.065`·무슬립 가정으로 역산한 유효 counts/rev 는 **L 77,178 / R 73,699** 로,
**좌측이 펌웨어 명목 77,520 과 0.44% 차이**다. 후보 ①·④를 가리키지만 가정 의존이 커서
근거로 확정하지 않았다.

### 변경 파일

| 파일 | 변경 |
|---|---|
| `config/wheel_odometry.yaml` | `wheel_radius_m` **0.065 → 0.0587** + 보정 근거·한계 |
| `wheel_odometry_node.py` | 같은 기본값 + 주석 |
| `config/stm_serial_bridge.yaml` | **값 변경 없음.** r 을 0.065 로 두는 이유 명시 + `counts_per_wheel_rev` 가 사본임을 명시 |
| `stm_serial_bridge_node.py` | 주석만 (`counts_per_wheel_rev` 소비자는 별도 노드) |
| `test_wheel_odometry_node.py` | 상수 갱신, 일치 테스트에서 `wheel_radius_m` 제외, 신규 3개(의도적 분리 / 배율 상쇄 / 실기 count 재현) |
| `ros2_ws/CLAUDE.md` | 스케일 보정 절 + yaw drift 분석 절 |

### 명령·결과

```bash
cd ros2_ws
export ROS_LOCALHOST_ONLY=1
source /opt/ros/humble/setup.bash && colcon build --symlink-install
source install/setup.bash
python3 -m pytest src/stm_serial_bridge/test/ src/cart_teleop/test/ -q
```

**538 passed** (직전 537 + 신규 3 − 파라미터 축소 2).

<details>
<summary>pytest 원본 출력</summary>

```
........................................................................ [ 13%]
........................................................................ [ 26%]
........................................................................ [ 40%]
........................................................................ [ 53%]
........................................................................ [ 66%]
........................................................................ [ 80%]
........................................................................ [ 93%]
..................................                                       [100%]
538 passed in 1.95s
```

</details>

<details>
<summary>보정 계산 원본 출력</summary>

```
run |  |Δ| (보고 이동거리) | 실제 1.0m 대비 | Δyaw
 1  |      1.101233       |   +110.12%      | -0.095
 2  |      1.113589       |   +111.36%      | -0.161
 3  |      1.105543       |   +110.55%      | -0.147

평균 배율 k = 1.106788  (스프레드 1.1012~1.1136, ±0.56%)
보정 반지름 r = 0.065 / k = 0.058728 m
→ 채택 0.0587 m  (잔차 -0.048%)

[검산] 호 길이 보정 시 k=1.107659 → r=0.058682 m (차이 0.046 mm, 측정 스프레드보다 훨씬 작음)

=== 좌우 분해 (평균) ===
Δyaw 평균 -0.1343 rad → d_L - d_R = 0.05105 m
d_L = 1.13231 m,  d_R = 1.08127 m,  d_L/d_R = 1.04721  (+4.72%)
역산 count: L=188,974  R=180,455   (1.0m = 2.448538 rev, r=0.065 가정)
→ 유효 counts/rev:  L=77,178   R=73,699   평균=75,439
   비교: 손회전 실측 68,160 / 펌웨어 명목 77,520

=== 보정 r=0.0587 적용 후 (같은 count 재계산) ===
이동거리 0.999515 m (목표 1.0),  Δyaw -0.121309 rad (보정 전 -0.1343)
→ yaw drift 는 사라지지 않고 -9.7% 만큼 '축소'될 뿐이다
```

</details>

### ⚠️ 이 기록의 한계

- **보정은 "실제 1.0 m"라는 기준에 전적으로 의존한다.** 사용자 보고값이 "약 1.0 m"이므로,
  기준이 1% 틀리면 r 도 1% 틀린다. 시종점 표시 방법과 오차는 기록되지 않았다.
- **표본 3개**다. 스프레드는 ±0.56%로 좁지만, 계통 오차(슬립·엔코더 스케일)의 **귀속**은
  이 데이터로 해결되지 않는다.
- **방위 ground truth 없음** — 거리만 확인됐다. yaw drift 중 실제 회전분이 얼마인지 모른다.
- **보정 후 실기 재검증은 하지 않았다.** 0.0587 이 실제로 1.0 m 를 재현하는지는
  **다음 주행에서 확인해야 한다.** 현재는 같은 count 입력에 대한 계산 일치만 테스트로 고정했다.
- **`ruff check` 미실행** (환경에 `ruff`·`pip` 없음).
- **작업 중 사고 재발 1건**: `colcon build` 를 리포지토리 루트에서 다시 실행해
  루트 `build/`·`install/`·`log/` 가 생성됐다(셸 작업 디렉터리가 초기화된 상태에서 실행).
  즉시 삭제했고 세 디렉터리 모두 `.gitignore` 대상이라 추적 파일 변화는 없다.

## 2026-08-08 10:00 — ✅ ROS2: 별도 `wheel_odometry` 노드 + `/wheel/odom` 발행, 537 tests 통과 + 실행 파일 E2E (Claude)

- **배경**: 앞 항목(09:30)의 순수 모듈을 ROS 에 배선했다. **기존
  `stm_serial_bridge_node` 와 분리된 별도 노드**로 만들었다(사용자 지시).
- 대상 커밋: `1a1f7a5` (working tree)

### 신규·변경 파일

| 파일 | 내용 |
|---|---|
| `stm_serial_bridge/wheel_odometry_node.py` | 신규. `/stm/encoder_total` 구독 → `/wheel/odom`(`nav_msgs/Odometry`) 발행 |
| `config/wheel_odometry.yaml` | 신규. 노드 이름 `wheel_odometry` 키 |
| `test/test_wheel_odometry_node.py` | 신규. 49 tests |
| `setup.py` | `wheel_odometry_node` console_script 추가 |
| `package.xml` | `nav_msgs` exec_depend 추가 |
| `ros2_ws/CLAUDE.md` | 10c 완료 + 10d/10e 남은 항목 |

### 지시받은 조건과 구현 상태

| 조건 | 상태 |
|---|---|
| 첫 `encoder_total` 은 적분 없이 rebaseline 만 | ✅ 발행도 하지 않는다 (속도 0을 지어내지 않기 위해) |
| `counts_per_wheel_rev` = 68160.0 사용 | ✅ 기본값·YAML 모두 |
| `wheel_radius_m`/`wheel_separation_m` 기존 값 사용 | ✅ 두 YAML 일치를 테스트로 강제 |
| `/stm/wheel_actual_rad_s` 미사용 | ✅ 구독조차 하지 않음 (`ros2 node info` 로 확인) |
| TF 미발행 | ✅ `/tf` 발행자 없음 확인 |
| 최종 `/odom` 미발행 | ✅ `/wheel/odom` 만 |
| EKF 코드 없음 | ✅ |
| 브리지와 분리된 별도 노드 | ✅ Serial 포트를 열지 않는다 |

### 명령·결과

```bash
cd ros2_ws
export ROS_LOCALHOST_ONLY=1
source /opt/ros/humble/setup.bash && colcon build --symlink-install
source install/setup.bash
python3 -m pytest src/stm_serial_bridge/test/ src/cart_teleop/test/ -q
```

**537 passed** (기존 488 + 신규 49).

<details>
<summary>pytest 원본 출력</summary>

```
........................................................................ [ 26%]
........................................................................ [ 40%]
........................................................................ [ 53%]
........................................................................ [ 67%]
........................................................................ [ 80%]
........................................................................ [ 93%]
.................................                                        [100%]
537 passed in 1.44s
```

</details>

### 실행 파일 E2E (pytest 밖, 실제 `ros2 run` + CLI 발행)

```bash
ros2 run stm_serial_bridge wheel_odometry_node --ros-args --params-file \
  install/stm_serial_bridge/share/stm_serial_bridge/config/wheel_odometry.yaml
ros2 topic pub --once /stm/encoder_total std_msgs/msg/Int32MultiArray "{data: [20000, 22000]}"
ros2 topic echo /wheel/odom --once
```

<details>
<summary>노드 시작 로그 + 수신한 /wheel/odom (요약)</summary>

```
[INFO] [wheel_odometry]:   counts_per_wheel_rev = 68160.0  <-- 2026-08-08 실측(좌우 공통). ⚠️ 펌웨어 명목 77520 과 다름
[INFO] [wheel_odometry]: wheel_odometry 시작: /stm/encoder_total -> /wheel/odom (m/count=0.000005992)
[INFO] [wheel_odometry]: TF는 발행하지 않는다 — odom -> base_link는 EKF의 몫이다.
[WARN] [wheel_odometry]: pose/twist covariance는 0으로 남겨둔다 — 근거 있는 값이 아직 없다. EKF에 연결하기 전에 반드시 설정할 것
[INFO] [wheel_odometry]: 첫 encoder_total: 적분 없이 기준만 잡는다 (L=10000, R=11000)
```

```
header: {frame_id: odom},  child_frame_id: base_link
pose.pose.position:    x: 0.06291286233320988   y: 0.000496019207449503   z: 0.0
pose.pose.orientation: z: 0.007883980687644131  w: 0.9999689209413045
twist.twist:           linear.x: 0.06675738255312783   angular.z: 0.016731173572212498
pose.covariance / twist.covariance: 전부 0.0
```

```
$ ros2 node info /wheel_odometry
  Subscribers:  /stm/encoder_total: std_msgs/msg/Int32MultiArray
  Publishers:   /wheel/odom: nav_msgs/msg/Odometry   (그 외 /rosout, /parameter_events)
$ ros2 topic list | grep '^/tf'
  (없음)
```

</details>

**손계산 대조** — 델타 `(10000, 11000)` count, `m/count = 5.9919e-6`:

| 값 | 손계산 | 수신값 |
|---|---|---|
| `d_c` | 0.0629149 m | x = 0.0629129 (mid-angle cos 반영) |
| `Δθ` | 0.0157681 rad | — |
| `orientation.z` = sin(Δθ/2) | 0.0078840 | **0.00788398** ✅ |
| `y` = d_c·sin(Δθ/2) | 4.9603e-4 | **0.000496019** ✅ |

첫 샘플이 적분되지 않고(로그), `/tf` 발행자가 없으며, `/stm/wheel_actual_rad_s` 를
구독하지 않는다는 것까지 실행 상태에서 확인했다.

### ⚠️ 이 기록의 한계 / 남은 것

- **하드웨어 미검증.** `ros2 topic pub` 으로 만든 **가짜 count** 로만 확인했다. 실제 주행에서
  오도메트리가 실제 이동량과 얼마나 맞는지는 **측정하지 않았다.**
- **STM32 재부팅을 탐지하지 않는다(10d).** 실행 중 카운터가 0으로 초기화되면 포즈가 크게
  튄다. `rebaseline()` 은 준비돼 있으나 **호출 조건이 없다** — `/stm/connected` 전이만으로는
  모든 reset 을 잡을 수 없으므로 탐지 방법부터 정해야 한다.
- **공분산이 0이다(10e).** EKF 연결 전 반드시 설정해야 한다. 노드가 시작 시 경고를 남기고,
  테스트도 "0이 맞다"가 아니라 **"아직 설정하지 않았다"는 현재 상태를 고정**한다.
- **launch 파일 미통합.** 현재는 `ros2 run` 으로만 띄운다.
- **`ruff check` 미실행** (환경에 `ruff`·`pip` 없음). `py_compile` + 88자 검사로 대체했고
  신규 2개 파일 모두 초과 줄 없음. `D`/`ANN`/`I` 규칙은 미검증.
- E2E 확인 후 백그라운드 노드 프로세스를 종료했다(`ps` 로 잔여 없음 확인).

## 2026-08-08 09:30 — ✅ ROS2: `wheel_odometry.py` 순수 모듈 + 단위 테스트 70개, 488 tests 통과 + 뮤테이션 검증 (Claude)

- **배경**: 앞 항목(09:00)에서 확정한 실측 68160 count/rev 를 소비하는 **순수 계산 모듈**을
  구현했다. 이번 단계는 계산 로직까지이며 **ROS publisher·`/wheel/odom` 발행·TF 는 손대지
  않았다**(사용자 지시).
- 대상 커밋: `1a1f7a5` (working tree)

### 신규 파일

| 파일 | 내용 |
|---|---|
| `stm_serial_bridge/wheel_odometry.py` | `WheelGeometry`/`OdometryState`(frozen) + `encoder_delta`·`wheel_distances`·`twist_from_distances`·`advance`·`rebaseline`·`initial_state`·`normalize_angle` |
| `test/test_wheel_odometry.py` | 70 tests |

`rclpy`·ROS 메시지·serial·**시계**에 의존하지 않는다. dt 는 인자로만 받는다.

### 설계상 확정한 것

- **속도는 엔코더 델타로 계산한다.** `/stm/wheel_actual_rad_s`(명목 77520 기준, 약 12% 작음)는
  쓰지 않는다. 이 결정을 테스트로도 고정했다 —
  `test_measured_scale_differs_from_firmware_nominal_by_about_12_percent`
- **int32 래핑 보정**: `((curr - prev + 2**31) % 2**32) - 2**31`. 단순 뺄셈은 경계에서
  `-4294967295` 라는 가짜 델타를 만든다(테스트로 고정)
- **포즈 적분은 midpoint(2차)**. 원호 구간에서 진행 방향이 현(chord) 방향과 정확히 일치하므로
  오차는 "호 길이 대신 현 길이" 뿐이다
- `theta` 는 `(-pi, pi]` 정규화
- **포즈는 dt 무관 / 속도만 dt 비례** (STATUS 에 타임스탬프가 없어 dt 는 수신 시각 차이)

### 10c(노드 배선) 단계 제약 — 문서에 고정

`ros2_ws/CLAUDE.md` "휠 오도메트리" 절에 기록했다:
① `/odom` 이 아니라 **`/wheel/odom`** 별도 토픽, ② **TF 발행 안 함**(최종 `/odom` 과
`odom -> base_link` 는 이후 EKF 담당), ③ **`rebaseline()` 호출 정책 미정** — `/stm/connected`
false→true 전이만으로 모든 STM reset 을 잡을 수 있다고 **가정하지 않는다**,
④ 노드 내장 vs 별도 `wheel_odometry_node` 분리 **미결정**.

### 명령·결과

```bash
cd ros2_ws
source /opt/ros/humble/setup.bash && colcon build --symlink-install
source install/setup.bash
python3 -m pytest src/stm_serial_bridge/test/ src/cart_teleop/test/ -q
```

**488 passed** (기존 418 + 신규 70).

<details>
<summary>pytest 원본 출력</summary>

```
......................................................................   [100%]
70 passed in 0.05s
```

```
........................................................................ [ 14%]
........................................................................ [ 29%]
........................................................................ [ 44%]
........................................................................ [ 59%]
........................................................................ [ 73%]
........................................................................ [ 88%]
........................................................                 [100%]
488 passed in 1.22s
```

</details>

### 뮤테이션 검증 — 테스트가 실제로 버그를 잡는지 확인

"70개 통과"가 공허한 통과가 아님을 보이기 위해, 소스에 의도적 결함을 넣고 테스트가
실패하는지 확인한 뒤 원본으로 복원했다.

| 뮤테이션 | 결과 |
|---|---|
| M1: 래핑 보정 제거 (`curr - prev`) | **7 failed**, 63 passed |
| M2: midpoint → Euler (`theta + dtheta/2` → `theta`) | **1 failed**, 69 passed |
| M3: omega 부호 반전 | **6 failed**, 64 passed |
| 복원 후 | **70 passed** (소스 원본과 `diff` 일치 확인) |

M2 를 잡는 테스트가 1개인 것은 의도한 대로다 — 해석적 원호 수렴 테스트
(`test_advance_converges_to_the_analytic_arc`)가 그 목적으로 작성된 유일한 테스트다.

### ⚠️ 이 기록의 한계

- **`ruff check` 미실행** — 이 환경에 `ruff`·`pip` 가 없다. 대신 `py_compile` 문법 검사와
  88자 초과 줄 검사를 수행했다(신규 2개 파일 모두 **초과 줄 없음**).
- **실기·mock 미검증**: 순수 함수만 구현했고 노드에 배선하지 않았으므로 실행 경로에 아무
  영향이 없다. `/stm/encoder_total` 실데이터로는 아직 한 번도 돌리지 않았다.
- **작업 중 사고 1건**: `colcon build` 를 **리포지토리 루트에서** 실행해 루트에
  `build/`·`install/`·`log/` 가 생성됐다(09:20:50). 기존 루트 워크스페이스가 없었음을
  확인한 뒤 삭제했고, 세 디렉터리 모두 `.gitignore` 대상이라 추적된 파일 변화는 없다.
  이후 빌드는 모두 `ros2_ws/` 에서 실행했다.

## 2026-08-08 09:00 — ✅ EM+ROS2: 엔코더 count/rev 재측정(판정 A 확정) + `counts_per_wheel_rev` 파라미터 추가, 418 tests 통과 (relu 실측 / Claude 반영)

- **배경**: Wheel Odometry 구현 전에 바퀴 1회전당 엔코더 count 를 재측정했다. 2026-08-03
  측정(통합 68162.5)이 명목값 77520 보다 약 12.1% 작아 원인 미확정 상태였고,
  `embedded/motor/docs/current.md` 의 "다음 개발 목표 2번"에 **판정 A/B/C 기준**을 미리
  정해 두었다.
- 대상 커밋: `1a1f7a5` "[feat] ROS2 수동 주행 teleop 추가"

### 실측 (relu, 실기)

방법: 바퀴를 **공중에 띄운 상태**에서 모터를 구동하지 않고 손으로 **1회전씩 좌우 각 10회**
`encoder_total` 변화량을 측정, **이상치 제거 후 평균**.

| 대상 | 2026-08-03 (각 4회전) | **2026-08-08 (각 10회)** | 차이 |
|---|---|---|---|
| Left | 68107.75 | **약 68420** | +312 |
| Right | 68217.25 | **약 67913** | -304 |
| **좌우 전체 평균** | **68162.5** | **약 68167** | **+4.5** |

- **판정 A 확정** — 통합 평균이 기존 실측과 사실상 동일하게 재현됐다. 명목 77520(=380×51×4)
  과의 약 -12.1% 차이는 **1회성 측정 실수가 아니다.**
- ⚠️ **좌우 편차는 재현되지 않았다.** 08-03 은 Right 가 약 0.16% 컸고, 08-08 은 Left 가 약
  0.75% 크다 — **크기도 부호도 달라졌다.** 두 측정 모두 손 회전이라 "정확히 1회전"을 맞추는
  오차가 값에 섞여 있다. **좌우 차이를 하드웨어 특성으로 확정하지 않으며, 좌우 개별 보정값도
  도입하지 않는다.** (사전 합격 기준의 "좌우 편차 1% 이내"는 만족한다.)
- ⚠️ **원인은 여전히 미확정.** CPR 380 의 정의 / Quadrature 배율(TI12=x4 가정) / 타이머 입력
  필터(IC1/IC2Filter=8) / 실제 감속비 중 무엇인지 이 측정으로는 구분되지 않는다. 재측정은
  "실측값이 맞다"만 확인했을 뿐 **원인 규명이 아니다.**

### 결정 (relu)

- **ROS Wheel Odometry 는 좌우 공통 `68160` count/rev 를 기준값으로 쓴다.**
- **STM 펌웨어(77520)와 mock 은 이번 작업에서 바꾸지 않는다.** 그 상수는 `actual_rad_s`
  뿐 아니라 **PI 제어 입력과 Stall 판정까지 함께** 바꾸므로, 별건의 Encoder Scale
  Calibration 작업으로 남긴다.
- 따라서 **`/stm/wheel_actual_rad_s`(77520 기준)와 ROS odometry 속도(68160 기준)의 스케일이
  현재 서로 다르다.** 의도된 일시적 불일치이며, 두 값을 같은 축에서 직접 비교하지 않는다.
  이 사실을 아래 4개 문서에 명시했다.

### 변경 파일

| 파일 | 변경 |
|---|---|
| `ros2_ws/.../config/stm_serial_bridge.yaml` | **`counts_per_wheel_rev: 68160.0` 신규**(+근거 주석). 파라미터 10 → **11개** |
| `ros2_ws/.../stm_serial_bridge_node.py` | 같은 이름 `declare_parameter` + `_log_parameters()` 출력 추가 |
| `ros2_ws/.../mock_stm.py` | 주석만. `DEFAULT_COUNTS_PER_WHEEL_REV` **값은 77520 유지** — mock 이 흉내내는 대상은 odometry 가 아니라 펌웨어이기 때문 |
| `motor_config.h` | **주석만. 매크로 값 변경 없음** (재측정 결과 + ROS/STM 스케일 불일치 명시) |
| `embedded/motor/docs/serial_protocol.md` | 재측정 절 + "펌웨어와 ROS의 스케일 불일치" 절 신규 |
| `embedded/motor/docs/current.md` | 캘리브레이션 항목 갱신, "다음 개발 목표 2번" **완료 처리** |
| `ros2_ws/CLAUDE.md` | 엔코더 스케일 절 갱신 + 스케일 불일치 절 신규. 파라미터 개수 표기 `9개` → `11개` (기존 표기가 이미 실제 10개와 어긋나 있었다) |

⚠️ `counts_per_wheel_rev` 는 **선언·로깅만 되고 아직 소비하는 코드가 없다.** `wheel_odometry.py`
구현은 다음 단계로 분리했다.

### 명령·결과

```bash
cd ros2_ws
source /opt/ros/humble/setup.bash && colcon build --symlink-install
source install/setup.bash
python3 -m pytest src/stm_serial_bridge/test/ src/cart_teleop/test/ -q
```

**418 passed** (기존과 동일 — 이번 변경은 기존 동작을 건드리지 않았다).

<details>
<summary>colcon build + pytest 원본 출력</summary>

```
Starting >>> cart_teleop
Starting >>> stm_serial_bridge
Finished <<< stm_serial_bridge [1.11s]
Finished <<< cart_teleop [1.13s]

Summary: 2 packages finished [1.29s]
```

```
........................................................................ [ 17%]
........................................................................ [ 34%]
........................................................................ [ 51%]
........................................................................ [ 68%]
........................................................................ [ 86%]
..........................................................               [100%]
418 passed in 1.40s
```

</details>

<details>
<summary>파라미터 스모크 테스트 (YAML ↔ 노드 기본값 일치 + 시작 로그)</summary>

```
[INFO] [1786147443.150505076] [stm_serial_bridge]: 파라미터:
[INFO] [1786147443.150792885] [stm_serial_bridge]:   serial_port         = /dev/ttyACM0
[INFO] [1786147443.150998590] [stm_serial_bridge]:   baud_rate           = 115200
[INFO] [1786147443.151242435] [stm_serial_bridge]:   wheel_radius_m      = 0.065
[INFO] [1786147443.151547075] [stm_serial_bridge]:   wheel_separation_m  = 0.38  <-- 2026-08-04 좌우 구동 바퀴 트레드 중심선 간 실측값
[INFO] [1786147443.151820489] [stm_serial_bridge]:   counts_per_wheel_rev= 68160.0  <-- 2026-08-08 실측(좌우 공통). ⚠️ 펌웨어 명목 77520 과 다름
[INFO] [1786147443.152082241] [stm_serial_bridge]:   tx_rate_hz          = 20.0
[INFO] [1786147443.152381194] [stm_serial_bridge]:   cmd_vel_timeout_sec = 0.5
[INFO] [1786147443.152753601] [stm_serial_bridge]:   dry_run             = True
[INFO] [1786147443.153007414] [stm_serial_bridge]:   max_wheel_rad_s     = 1.0  <-- ⚠️ 실제 모터 정격 확정 전 임시 벤치 제한
[INFO] [1786147443.153242897] [stm_serial_bridge]:   rx_poll_hz          = 50.0
[INFO] [1786147443.153531257] [stm_serial_bridge]:   status_timeout_sec  = 0.5

yaml counts_per_wheel_rev = 68160.0
node default              = 68160.0 (float)
YAML == node default      = True
yaml key count            = 11
```

</details>

### ⚠️ 이 기록의 한계

- **실측값은 사용자 구두 보고값이다.** 10회 개별 측정의 원본 `encoder_total` 값과 이상치
  제거 기준은 이 로그에 확보되지 않았다(08-03 기록에는 구간별 원본이 남아 있다).
- **`ruff check` 를 돌리지 못했다** — 이 환경에 `ruff` 가 설치돼 있지 않고 `pip` 도 없다.
  대신 `py_compile` 문법 검사와 88자 초과 줄 검사를 직접 수행했다: **추가한 줄은 모두 88자
  이하**이며, 초과 줄 4개(`stm_serial_bridge_node.py:60,728,729`, `mock_stm.py:339`)는
  `git show HEAD:` 비교로 **변경 전부터 있던 것**임을 확인했다(신규 위반 없음).
- **첫 pytest 실행은 무효였다.** `install/` 이 심볼릭이 아닌 **복사본**이라 수정 전 코드가
  로드됐다(파라미터 스모크 테스트가 `ParameterNotDeclaredException` 으로 이를 드러냈다).
  `colcon build --symlink-install` 재실행 후의 결과만 위에 기록했다.
- **실기 미검증**: 이번 변경 자체는 하드웨어에서 돌리지 않았다. 파라미터가 선언·로깅된다는
  것만 확인했고, 소비하는 로직이 없으므로 주행 동작에 영향이 없다.

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

## 2026-08-04 — ✅ EM+ROS2 실기: `cart_teleop` WASD 수동 주행 동작 확인 / ⚠️ 수치 정확도는 미검증 (relu 실기 / Claude 문서 반영)

- **환경**: 실제 STM32 + 모터 연결. `cart_teleop → /cmd_vel → stm_serial_bridge`,
  Bridge `mode:=hardware` + `speed_profile:=slow`
- **커밋**: 브랜치 `em/feature/motor-control`. 이번 실기에서 **코드는 변경하지 않았다**
- **대상**: 바로 아래 항목(`cart_teleop` 패키지 추가)의 실기 검증

### 확인된 것

| 항목 | 결과 |
|---|---|
| Linux 터미널 WASD 입력 → 실제 로봇 동작 | ✅ 동작함 |
| 키를 **짧게 한 번** 입력 | ✅ 잠시 주행 후 **command lease 만료로 자동 정지** |
| 위 자동 정지의 성격 | ✅ `input_timeout_sec` 기반의 **의도된 안전 동작** (결함 아님) |
| teleop 키 조작 전반 | ✅ 정상 작동 |

즉 `SSH 키보드 → cart_teleop → /cmd_vel → stm_serial_bridge → STM32 → 모터` 전 구간이
실기에서 동작하고, **command lease 설계(키를 놓으면 timeout 후 정지)가 실제 하드웨어에서
의도대로 작동**함을 확인했다.

### ⚠️ 확인 필요 — 실기에서 쓴 `input_timeout_sec` 값

**코드 기본값은 1.0초**(`teleop_keys.DEFAULT_INPUT_TIMEOUT_SEC`,
`teleop_node.declare_parameter("input_timeout_sec", ...)`)다. 그러나 실행 시
`-p input_timeout_sec:=...` 로 덮어썼는지는 **확인할 수 없어 1.0초로 단정하지 않는다.**

역추적이 불가능한 이유: **teleop 노드는 파라미터를 로그에 남기지 않는다**
(`teleop_node.py` 에 `get_logger().info` 0건). Bridge 는 `_log_parameters()` 로 시작 시
전체 파라미터를 찍지만 teleop 에는 그 경로가 없다.
→ **후속 개선 대상**: teleop 시작 시 파라미터 로그 추가(이번 범위 밖 — 코드 미변경 지시).

### ⚠️ 이번 실기로 검증되지 **않은** 것

- **낮은 속도 단계의 실제 바닥 데드밴드** — 단계 4 이하는 바퀴 ≤1.6 rad/s → 개루프
  PWM ≤16. PWM<20 은 비선형(데드존) 구간으로 기록돼 있어 **바닥에서 안 움직일 가능성**이
  남아 있다. 어떤 단계로 주행했는지도 기록되지 않았다
- **실제 주행 속도·회전각 수치 정확도** — 측정하지 않았다. 주행거리·속도·회전각을
  **수치 검증 완료로 표시하지 않는다**
- **LiDAR/slam_toolbox 동시 실행**
- **실제 지도 작성 품질**
- **장시간 SSH 세션에서의 입력 지연·안정성** (자동반복 초기 지연이 실제 SSH 환경에서
  `input_timeout_sec` 보다 짧은지도 미확인)
- `Space` 정지·`DISARMED` 충돌 차단의 **실기** 동작 (mock 에서만 확인)

### ⚠️ 안전 표현

`Space` 는 **정지 명령(zero Twist)** 이며 **ESTOP 이 아니다.** 현재 Bridge 에는 STM
`ESTOP`/`STOP` 명령 송신 인터페이스가 없다. **실제 비상정지는 물리 전원 차단이 필요하다.**

### ⚠️ 이 기록의 한계

결과는 **사용자 보고값**이며 teleop 화면·브리지 로그 **원본은 확보되지 않았다.**
"짧게 한 번 입력 후 자동 정지"의 주행 시간·거리도 측정값이 아니다.

## 2026-08-04 — ✅ ROS2: `cart_teleop` 수동 주행 패키지 추가 (WASD→/cmd_vel), 64 + 349 tests 통과 (Claude)

- **환경**: Ubuntu 22.04, ROS2 Humble, Python 3.10. **하드웨어 미연결** — mock/PTY 만 사용
- **커밋**: 브랜치 `em/feature/motor-control` (`5a3ca3c` 위에 미커밋)
- **목적**: LiDAR + slam_toolbox 를 띄운 상태에서 SSH 터미널 WASD 로 주행하며 **수동 지도
  작성**. 이후 teleop 을 끄고 Nav2 P2P 로 전환한다.
- **경로**: `SSH 키보드 → cart_teleop → /cmd_vel → stm_serial_bridge → STM32`

### 신규 패키지 `ros2_ws/src/cart_teleop/` (ament_python)

| 파일 | 역할 |
|---|---|
`cart_teleop/teleop_keys.py` | **순수 로직** — 키→명령, 속도 단계, command lease 판정. `rclpy`·`termios`·`select`·`serial`·`stm_serial_bridge` 를 import 하지 않음(AST 테스트로 고정) |
`cart_teleop/teleop_node.py` | `rclpy` + `termios`/`select` 입력, 20Hz Twist 발행, ANSI UI, Publisher 충돌 검사, 안전 종료 |
`test/test_teleop_keys.py` | 순수 로직 단위 테스트 69개 |
`package.xml`·`setup.py`·`setup.cfg`·`resource/cart_teleop` | 패키지 골격. 의존성은 `rclpy`·`geometry_msgs` 뿐 |

**launch 파일은 만들지 않았다** — teleop 은 stdin(tty)을 점유해야 하므로
`ros2 run cart_teleop keyboard_teleop` 이 표준 실행 방법이다.

**Serial 포트를 열지 않는다.** 포트 소유자는 `stm_serial_bridge` 하나이며, 이 계약을
두 파일 모두에 대해 AST import 검사 테스트로 고정했다.

### 핵심 설계: command lease (latch 아님)

터미널은 **키 릴리즈를 감지할 수 없다.** 그래서 W/S/A/D 입력마다 유효시간
(`input_timeout_sec`, 기본 1.0초)을 갱신하고, 만료되면 zero Twist 로 전환하며 **동작을
폐기**한다(다시 움직이려면 새 키 필요). 키를 누르고 있으면 OS 자동반복이 lease 를
갱신한다. 1.0초는 자동반복 초기 지연(약 0.5초)보다 크게 잡아 끊김을 피한 값이다.

### `=` 속도 증가 별칭 추가 (같은 날 후속)

`+` 는 대부분의 배열에서 Shift 가 필요해 주행 중 조작이 번거롭다. 같은 물리 키의
Shift 없는 문자 `=` 를 **`+` 의 별칭**으로 받아들이도록 추가했다. `+` 동작·기본 속도·
`input_timeout_sec`·나머지 키 매핑은 **변경하지 않았다.**

- `SPEED_UP_KEYS = {"+", "="}` 로 판정. `=` 는 자신의 라벨(`= 속도 단계 증가 (+ 별칭)`)을
  표시해 사용자가 실제로 누른 키를 알 수 있다
- UI 안내: `+ 속도↑` → **`+/= 속도↑`**
- 신규 테스트 5개: `=` 가 단계를 올리는지 / `+` 만 쓴 상태와 **완전히 동일한 상태·발행값**
  인지 / `=` 로도 최대 clamp / `=` 는 lease 를 갱신하지 않는지(속도 키이므로) / 라벨 표시

**실제 노드 확인 (PTY)**: 시작 `5/5` → `-`×3 → `2/5` → **`=`** → `3/5` → `+` → `4/5` →
`=`×4 → **`5/5`(clamp)**. `= 속도 단계 증가` 라벨과 `+/= 속도↑` 안내가 화면에 표시되고
`q` 종료코드 0.

경계값 `elapsed >= timeout` 을 TIMEOUT 으로 두는 것은 의도적이다 —
`command_watchdog.select_wheel_command()` 와 같은 규칙(애매하면 정지).

### 명령과 결과

```bash
cd ros2_ws
colcon build --symlink-install                      # 2 packages, 경고 0
python3 -m pytest src/cart_teleop/test/ -q          # 69 passed in 0.06s
python3 -m pytest src/stm_serial_bridge/test/ -q    # 349 passed in 1.12s  (회귀 0)
bash scripts/verify_bridge_mock.sh                  # 3/3 통과, 잔존 프로세스 없음
git diff --check                                    # exit 0
ros2 run cart_teleop keyboard_teleop < /dev/null    # 비-TTY -> 명확한 오류 + exit 1
```

### ★ mock 왕복 검증 (PTY 로 가짜 터미널을 붙여 키 주입)

Bridge `mode:=mock speed_profile:=slow` + teleop 실행 후 실제 송신값:

| 입력 | 기대 | 실제 `SET_WHEEL_VEL` | 결과 |
|---|---|---|---|
`W` (전진) | `2.000,2.000` | `2.000,2.000` | ✅ |
`A` (좌회전) | `-1.754,1.754` | `-1.754,1.754` | ✅ |
`D` (우회전) | `1.754,-1.754` | `1.754,-1.754` | ✅ |
`Space` / lease timeout | `0.000,0.000` | `0.000,0.000` | ✅ |

`W → 0.13 m/s → 바퀴 2.0 rad/s`, `A → 0.60 rad/s → 바퀴 ±1.754`(L=0.38 기준) —
**둘 다 slow 상한(2.0) 이내라 Bridge 에서 축소되지 않았다.**

### ★ 상태 전이 검증

| 시나리오 | 관측 상태 | 결과 |
|---|---|---|
teleop 단독 + W | `ARMED` | ✅ |
외부 `/cmd_vel` Publisher 기동 | `ARMED → DISARMED` (외부 1개 표시) | ✅ |
DISARMED 중 W 입력 | 상태 변화 없음(DISARMED 유지, non-zero 미발행) | ✅ |
외부 Publisher 종료 | **`STOPPED`** (`ARMED` 로 자동 복귀하지 **않음**) | ✅ |
해제 후 키 없이 대기 | 상태 변화 없음 | ✅ **자동 재가동 금지 확인** |
새 W 입력 | `ARMED` | ✅ |
무입력 2.5초 | `TIMEOUT` 1회 → `STOPPED` | ✅ |
`q` | `QUIT`, 종료 코드 0 | ✅ |

### ★ 종료 경로 검증 (`q` / 실제 Ctrl+C)

| 경로 | 방법 | 결과 |
|---|---|---|
`q` | PTY 로 `q` 주입 | ✅ 종료코드 0, 정지·복원 메시지 출력 |
**실제 Ctrl+C** | `pty.fork()` 로 제어 터미널을 붙이고 **`0x03` 문자를 tty 에 주입** → 드라이버가 foreground 프로세스 그룹에 SIGINT | ✅ 종료코드 0, 0.0초 내 종료, 정지·복원 메시지 출력, 잔존 프로세스 없음 |
비-TTY | `< /dev/null` | ✅ 명확한 오류 + 종료코드 1 |

`tty.setcbreak()` 를 쓴 덕분에 ISIG 가 유지되어 Ctrl+C 가 SIGINT 로 동작한다
(`tty.setraw()` 면 그냥 문자가 되어 종료되지 않는다).

### ⚠️ 검증 과정에서 있었던 정정 (3건 — 전부 검증 하네스 문제였다)

1. **`TIMEOUT`·`QUIT` 미관측** — 1차 PTY 검증에서 두 상태가 화면 로그에 없었다. 원인은
   **하네스가 PTY master 를 2.5초간 읽지 않아 버퍼가 포화**된 것이고 **노드 결함이
   아니었다.** 읽기 스레드로 계속 비우도록 고쳐 재실행하니 `TIMEOUT` 1회·`QUIT` 1회가
   정상 관측됐다. (`TIMEOUT` 이 1회만 나오는 것은 설계대로다 — 만료 tick 에서만
   `TIMEOUT` 이고 이후는 `STOPPED` 다.)
2. **Bridge 잔존 프로세스** — 하네스가 **정리 전에 잔존 검사를 출력**하는 순서 문제였다.
   수동 정리 후 재확인해 잔존 0 을 확인했다.
3. **Ctrl+C 로 종료되지 않음(오판)** — 1차 시도에서 15초 내 종료되지 않고 터미널이
   cbreak 로 남았다. 그러나 원인은 하네스가 **`ros2 run` 래퍼 PID 하나에만** SIGINT 를
   보낸 것이었다. 실제 Ctrl+C 는 tty 드라이버가 **foreground 프로세스 그룹 전체**에
   보내므로 상황이 다르다. `pty.fork()` + `0x03` 주입으로 다시 검증해 **정상 종료**를
   확인했다.
   → ⚠️ 다만 여기서 **운영상 주의점**이 하나 드러났다: 다른 셸에서 종료시킬 때
   `kill -INT <ros2 run PID>` 는 노드에 닿지 않아 터미널이 cbreak 로 남을 수 있다.
   프로세스 그룹으로 보내야 한다(`kill -INT -<PGID>`). 정상 종료 수단은 **터미널에서
   `q`/`Esc`/`Ctrl+C`** 다.

### ⚠️ 실기에서 검증하지 않은 것

- **실제 모터로 teleop 주행** — mock 송신값까지만 확인했다
- **속도 단계를 내렸을 때 실제로 움직이는지** — 단계 4 이하는 바퀴 1.6 rad/s 이하 →
  개루프 PWM 16 이하다. PWM<20 은 비선형(데드존) 구간으로 기록돼 있어 **바닥에서 안
  움직일 가능성**이 있다. 기본값을 최대 단계로 둔 이유다
- **자동반복 초기 지연이 실제 SSH 환경에서 1.0초 이내인지** — 터미널·SSH 설정에 따라
  다르다. 끊김이 있으면 `input_timeout_sec` 을 올려야 한다
- LiDAR/slam_toolbox 와 동시 실행, 실제 지도 작성 품질
- 실제 SSH 세션(네트워크 지연 포함)에서의 키 응답성

## 2026-08-04 — ✅ EM+ROS2 실기: `L=0.38` 반영 확인 — `slow` 프로파일 **바닥 제자리 회전** 성공 / ⚠️ 회전각 수치는 미검증 (relu 실기 / Claude 문서 반영)

- **환경**: 실제 STM32 + 모터. `stm_serial_bridge` hardware 모드, `speed_profile:=slow`
  (`max_wheel_rad_s = 2.0`), **바닥 주행**
- **명령**: `/cmd_vel` `linear.x=0.0, angular.z=0.6` → **약 1초 후 zero Twist**
- **커밋**: 브랜치 `em/feature/motor-control`. **코드 변경 없음** — 문서만 갱신
- **의의**: `wheel_separation_m` 0.30 → **0.38**(실측) 변경이 실제로 동작에 반영되는지를
  확인하는 첫 테스트다. 직진은 `L` 과 무관해 앞선 전진 테스트로는 확인할 수 없었다.

### 결과

| 항목 | 결과 |
|---|---|
`/stm/wheel_target_rad_s` | ✅ **약 `[-1.754, 1.754]`** |
| 좌우 바퀴 | ✅ 반대 방향으로 회전 |
| 차체 | ✅ **왼쪽(반시계)으로 제자리 회전** |
| 명령 종료 후 | ✅ 정상 정지 |
| FAULT | ✅ 없음 |

### 이 결과가 확인해 주는 것 3가지

1. **`L=0.38` 이 실제로 STM 까지 반영된다.**
   `0.6 × 0.38/2 / 0.065 = 1.753846` → 관측 `1.754` 와 일치. `L=0.30` 이었다면 1.385 가
   나왔을 자리다. 즉 YAML·노드 기본값·기구학 변환이 한 줄로 이어져 있음이 실기로 확인됐다.
2. **`slow`(2.0)가 제자리 회전 봉투를 비례 축소 없이 통과시킨다** (1.754 < 2.0).
   2.0 을 최초 통합 프로파일로 고른 근거가 실기로 확인됐다 — 조향은 온전하고 직진 속도만
   낮은 상태라는 설계 의도가 성립한다.
3. **REP 103 부호 규약이 맞다.** `angular.z > 0` → 반시계(좌회전) → 왼쪽 바퀴 음수·오른쪽
   양수. 코드 주석(`differential_drive.cmd_vel_to_wheel_rad_s`)의 규약과 일치한다.

### ⚠️ 검증되지 않은 것

- **회전각 수치** — 실제로 몇 도 돌았는지 **측정하지 않았다.** 따라서 `ω=0.6 rad/s` 와
  일치하는지, 회전량 정확도가 어떤지는 **미검증**이다. 확인된 것은 방향·부호·목표값과
  "제자리 회전이 일어난다"까지다.
- **직진 속도 수치** — 앞선 항목대로 여전히 미검증 (약 5.8 cm 관측값은 속도로 환산 불가)
- **`bench`(1.0)·`nav2`(6.4) 의 바닥 주행** — 미검증 유지
- `wheel_actual_rad_s` 수치 정확도, 엔코더 count/rev 12.1% 원인 — 미확정 유지

### ⚠️ 이 기록의 한계

결과는 **사용자 보고값**이며 `ros2 topic echo /stm/wheel_target_rad_s` 출력과 브리지 로그
**원본은 확보되지 않았다.** 회전각 측정 도구·기준도 없다(측정 자체를 하지 않음).

## 2026-08-04 — ✅ EM+ROS2 실기: `speed_profile:=slow` **바닥 전진·정지** 확인 / ⚠️ 속도 정확도는 미검증 유지 (relu 실기 / Claude 문서 반영)

- **환경**: 실제 STM32 + 모터. `stm_serial_bridge` hardware 모드, `speed_profile:=slow`
  (`max_wheel_rad_s = 2.0`), **바닥 주행**
- **명령**: `/cmd_vel` `linear.x=0.3, angular.z=0.0` → **1초 후 zero Twist 발행**
- **커밋**: 브랜치 `em/feature/motor-control`. **코드 변경 없음** — 문서만 갱신

### 결과

| 항목 | 결과 |
|---|---|
| 차체 전진 | ✅ **실제로 전진함** (바닥 주행) |
| 명령 종료 후 정지 | ✅ 정상 정지 |
| 급가속·위험한 움직임 | ✅ 없음 |
| FAULT | ✅ 없음 |
| 이동량 (관측값) | **약 5.8 cm** |

**판정: `slow` 프로파일의 바닥 전진 및 정지 동작 확인 완료.**
이로써 `slow` 는 바퀴 공중(앞선 항목)과 **바닥** 양쪽에서 동작이 확인됐다.

### ⚠️ 5.8 cm 를 속도로 환산하지 않는 이유 (판정 보류)

- 발행 창 1초에 **ROS2 CLI 기동·discovery 시간이 포함될 수 있다.** 실제 모터가 명령을 받은
  시간이 1초보다 짧을 수 있으므로, 5.8 cm 를 **1초 주행거리로 확정하지 않는다.**
- 따라서 **0.058 m/s 로 환산하지 않는다.**
- 계산상 값 0.13 m/s 와의 차이 원인은 **이번 테스트만으로 판정하지 않는다.**
  (후보: 유효 구동 시간, 개루프 PWM↔속도 관계, 정지마찰·부하, 엔코더 스케일 12.1% 미확정 —
  이 데이터로는 서로 구분되지 않는다.)
- **속도 정확도는 미검증 상태를 유지한다.**

정량 측정이 필요해지면 CLI 기동 시간이 섞이지 않는 방법으로 다시 해야 한다
(예: 정상 상태로 충분히 오래 주행시킨 뒤 구간 거리/시간 측정, 또는 `/stm/encoder_total`
변화량 기반 측정 — 다만 후자는 엔코더 스케일 12.1% 미확정 문제를 함께 안는다).

### ⚠️ 여전히 미검증 (유지)

- **`slow` 의 실제 주행 속도 정확도** — 위 사유로 미검증
- **`bench`(1.0, 계산상 0.065 m/s) 의 바닥 주행** — 미검증. 모터 데드밴드 미만일 가능성이
  남아 있어 바닥에서 안 움직일 수 있다
- **`nav2`(6.4) 의 바닥 주행** — 미검증. 실기 검증된 최대는 여전히 2.0 rad/s 다
- **`L=0.38` 기준 회전 주행** — 이번에도 직진만 했다
- `wheel_actual_rad_s` 수치 정확도, 엔코더 count/rev 12.1% 원인 — 미확정

### ⚠️ 이 기록의 한계

결과는 **사용자 보고값**이며 브리지 로그·`ros2 topic echo` **원본은 확보되지 않았다.**
이동량 5.8 cm 의 측정 방법(기준점·측정 도구)도 기록되지 않았다.

## 2026-08-04 — ✅ ROS2: `wheel_separation_m` 실측 0.38 반영, 속도 봉투 재계산 + nav2 프로파일 6.0→6.4, 349 tests 통과 (relu 실측 / Claude 반영)

- **환경**: Ubuntu 22.04, ROS2 Humble. 코드·문서 변경은 hardware 없이 mock/PTY 로만 검증
- **커밋**: 브랜치 `em/feature/motor-control` (`18e3b5b` 위에 미커밋)

### 실측 (relu)

| 항목 | 값 |
|---|---|
| 측정 기준 | **왼쪽 구동 바퀴 트레드 중심선 ↔ 오른쪽 구동 바퀴 트레드 중심선 사이 거리** |
| 실측 | **38 cm → `wheel_separation_m = 0.38`** |
| 이전 값 | `0.30` (미실측 placeholder) |

### 봉투 재계산 (`r=0.065`, Nav2 `max_vel_x=0.3` / `max_vel_theta=0.6`)

| Nav2 명령 | L=0.30 (이전) | **L=0.38 (실측)** |
|---|---|---|
| 직진 `v=0.3` | 4.615 rad/s | **4.615 rad/s** (불변) |
| 제자리 회전 `ω=0.6` | 1.385 rad/s | **1.754 rad/s** |
| 직진+회전 (최악) | 6.000 rad/s | **6.369 rad/s** |

`L` 은 **회전 성분에만** 들어가므로 직진 요구량은 바뀌지 않는다. 최악 조합이 6.369 로
올라가 **기존 `nav2` 프로파일 6.0 은 부족**해졌고(약 5.8% 축소 발생), **6.4** 로 올렸다.

### 변경 파일

| 파일 | 변경 |
|---|---|
`config/stm_serial_bridge.yaml` | `wheel_separation_m` **0.30 → 0.38**, placeholder 문구 제거 + 2026-08-04 실측 명시. 봉투 계산표 갱신 |
`config/speed_profile_slow.yaml` | **값 2.0 유지.** 회전 수용 근거를 1.385 → **1.754** 로 갱신 (2.0 이 여전히 덮는다. `L>0.433` 이면 깨진다는 조건도 기재) |
`config/speed_profile_nav2.yaml` | **6.0 → 6.4**. 6.369 계산과 "계산상 상한, 실기 미검증" 유지 |
`test_differential_drive.py` | `WHEEL_SEPARATION_M` 0.30→0.38, 회귀값 갱신(직진 4.615 / 회전 **1.754** / 최악 **6.369**), 기존 곡선 주행 회귀값 `1.923077/4.230769` → **`1.615385/4.538462`**, 프로파일 커버리지 테스트 2개 신규 |
`ros2_ws/CLAUDE.md` | 계산표·프로파일 표 갱신, 실측 완료 반영, **좌우 매핑 실기 기록의 `angular.z=±0.433333` 이 이제 유효하지 않다는 경고 추가** |
`tests/TEST_LOG.md` | 이 항목 |

**코드 로직은 변경하지 않았다** — `required_max_wheel_rad_s()`·`limit_wheel_rad_s()` 는
그대로이고 상수·설정·회귀값만 갱신했다. `stm_serial_bridge_node.py` 도 미수정.

### 명령과 결과

```bash
cd ros2_ws
colcon build --symlink-install                        # 경고 0
python3 -m pytest src/stm_serial_bridge/test/ -q      # 349 passed in 1.41s
bash scripts/verify_bridge_mock.sh                    # 3/3 통과, 잔존 프로세스 없음
```

**349 passed** (직전 347 + 신규 2: `slow` 가 회전 봉투를 덮는지, `nav2` 가 전체 봉투를
덮는지). 기존 테스트 **회귀 없음** — 단 L 의존 회귀값 3개는 의도적으로 갱신했다.

### ★ 프로파일 검증 (mock/PTY)

**A. 직진 단독** `linear.x=0.3` (요구 4.615) — L 변경과 무관해야 한다

| 실행 | 기대 | 실제 | 결과 |
|---|---|---|---|
`(기본 bench)` | `1.000,1.000` | `SET_WHEEL_VEL,1.000,1.000` | ✅ |
`speed_profile:=slow` | `2.000,2.000` | `2.000,2.000` | ✅ |
`speed_profile:=nav2` | `4.615,4.615` | `4.615,4.615` | ✅ |
`max_wheel_rad_s:=3.5` | `3.500,3.500` | `3.500,3.500` | ✅ |

**B. 최악 조합** `linear.x=0.3, angular.z=0.6` (요구 left 2.862 / right **6.369**)

| 실행 | 기대 | 실제 | 결과 |
|---|---|---|---|
`speed_profile:=nav2` | `2.862,6.369` (**제한 없음**) | `2.862,6.369` | ✅ |
`speed_profile:=slow` | `0.899,2.000` (비례 축소) | `0.899,2.000` | ✅ |

- `nav2`(6.4)에서 요구 6.369 가 **무축소로 통과**함을 확인 — 6.4 로 올린 목적이 달성됐다.
- `slow`(2.0)에서는 축소되지만 **좌우 비율이 `0.449275362` 로 원본과 정확히 동일** —
  궤적 곡률이 보존됨을 수치로 확인했다.

### ⚠️ 검증 과정에서 있었던 정정

`slow` 최악 조합의 기대값을 처음 `0.898` 로 잡았는데 실제는 `0.899` 였다. 재계산 결과
정확값이 `0.898550725` 로 **3자리 반올림 시 `0.899` 가 맞다** — **코드가 아니라 검증
스크립트의 기대값이 틀렸다.** 기대값을 고쳐 재실행해 통과를 확인했다.

### ⚠️ 실기에서 검증하지 않은 것

- **`L=0.38` 로 실제 회전 주행** — 이번 변경은 회전 성분을 바꾸는데, 회전 실기는 하지
  않았다. 직진(2026-08-04 `slow` 실기)만 확인된 상태다
- **`nav2` 프로파일(6.4)** — 실기 미진행. 6.4 rad/s ≈ 바퀴 원주속도 0.42 m/s 로,
  실기 검증된 최대(2.0 rad/s, 바퀴 공중)의 3배가 넘는다
- `wheel_actual_rad_s` 수치 정확도, 실제 주행 속도, 바닥 주행 — 모두 여전히 미검증
- 엔코더 count/rev 12.1% 차이 원인 미확정

### 발견한 미해결 불일치 (수정하지 않음, 결정 필요)

`stm_serial_bridge_node.py:147` 의 `declare_parameter("wheel_separation_m", 0.30)` 이
**여전히 0.30** 이고, `:427` 의 시작 로그도 `"⚠️ 조립 후 실측 필요한 임시값"` 문구를
유지하고 있다. launch 는 항상 YAML(0.38)을 넘기므로 정상 경로에는 영향이 없으나,
`ros2 run` 으로 파라미터 없이 띄우면 **0.30 이 쓰인다.** 사용자가 지정한 변경 파일 목록에
노드가 없어 수정하지 않았다.

## 2026-08-04 — ✅ EM+ROS2 실기: `speed_profile:=slow`(2.0 rad/s) hardware 모드 주행 확인 (relu 실기 / Claude 문서 반영)

- **환경**: 실제 STM32 + 모터 연결. `stm_serial_bridge` **hardware 모드**,
  `speed_profile:=slow`, `serial_port` 는 STMicroelectronics STLink **by-id 경로**,
  **바퀴 공중 상태**
- **커밋**: 브랜치 `em/feature/motor-control` (`18e3b5b` + 미커밋 1단계 변경).
  이번 실기에서 **코드는 변경하지 않았다** — 문서만 갱신
- **대상**: 바로 아래 항목(속도 봉투 정합 + 프로파일)의 실기 검증

### 절차와 결과

| 단계 | 결과 |
|---|---|
`check_stm_topics` (6개 토픽) | ✅ 통과 — `/stm/connected=true`, `/stm/fault=NONE`, `wheel_target_rad_s`·`wheel_actual_rad_s`·`pwm`·`encoder_total` 모두 수신 |
`/cmd_vel linear.x=0.3, angular.z=0.0` 3초 발행 | ✅ 발행됨 |
slow 프로파일의 상한 적용 | ✅ 좌우 목표가 **2.0 rad/s 로 제한**됨 (요구 4.615 → 2.0) |
모터 동작 | ✅ 좌우 바퀴 모두 **전진 방향**으로 회전 |
`/cmd_vel` 종료 후 | ✅ **watchdog 으로 정지** |
FAULT | ✅ 발생 없음 |

즉 **`base YAML → speed_profile 오버레이 → 실제 STM 송신 → 모터 구동`** 경로가 실기에서
동작한다. mock 에서 확인한 `SET_WHEEL_VEL,2.000,2.000` 이 실제 하드웨어에서도 성립했다.

### 이번에 생략한 항목 (근거 있는 생략)

후진·좌회전·우회전은 수행하지 않았다. 방향 매핑은 **2026-08-02**(`/cmd_vel` → 모터 구동)과
**2026-08-03**(좌우 매핑·부호 실측 확정) 실기에서 이미 확인했고, 이번 변경 범위는 방향
매핑이 아니라 **launch 구성과 속도 상한 프로파일**이기 때문이다.

### ⚠️ 이번 실기로 검증되지 **않은** 것

- **`wheel_actual_rad_s` 의 수치 정확도** — 측정하지 않았다. 엔코더 count/rev 12.1% 차이
  원인이 **여전히 미확정**이므로 보고값은 실제보다 약 12% 작다는 전제로 해석해야 한다
- **실제 주행 속도가 0.13 m/s 인지** — 측정하지 않았다. "모터가 전진 방향으로 돈다"까지만
  확인했고 속도의 정량 확인은 없다
- **`nav2` 프로파일(6.0 rad/s)** — 실기 테스트하지 않았다
- **`bench` 프로파일(1.0 → 0.065 m/s)이 바닥에서 움직이는지** — 모터 데드밴드 미만일
  가능성이 남아 있다
- **바닥 주행** — 이번 실기는 바퀴 공중 상태였다
- `wheel_separation_m=0.30` 실측, Stall/FAULT 실기, USB 강제 분리, STATUS 중단 시 연결
  상태 전이 — 모두 여전히 미검증

### ⚠️ 이 기록의 한계 / 확인 필요

- 결과는 **사용자 구두 보고값**이며 `check_stm_topics` 출력·브리지 로그 **원본은 확보되지
  않았다**. 다음 실기에서는 `2>&1 | tee` 로그를 함께 남기면 검증 가능성이 올라간다.
- 사용자 보고에 "**바퀴를 공중에 띄운 상태**"와 "**로봇이 실제로 전진함**"이 함께 있었다.
  두 서술은 양립하지 않으므로(공중이면 차체가 전진할 수 없다) **바닥 접지 여부를 이 기록으로
  확정하지 않는다.** 위 표에는 모순 없이 확인되는 "좌우 바퀴가 전진 방향으로 회전"까지만
  적었고, **바닥 주행은 미검증으로 유지**한다. 다음 실기에서 명확히 구분해 기록할 것.

## 2026-08-04 — ✅ ROS2: 속도 봉투 정합 + 프로파일(bench/slow/nav2) 추가, 347 tests 통과 (Claude)

- **환경**: Ubuntu 22.04, ROS2 Humble, Python 3.10. **하드웨어 미연결** — mock/PTY 만 사용
- **커밋**: 브랜치 `em/feature/motor-control` (`18e3b5b` 위에 미커밋)
- **배경**: Nav2 봉투(`max_vel_x=0.3`, `max_vel_theta=0.6`)가 요구하는 바퀴 각속도는 최대
  **6.0 rad/s** 인데 브리지 상한은 벤치 잠정값 **1.0** 이었다. `limit_wheel_rad_s()` 가
  좌우 비율을 유지한 채 **전체를 0.217배로 축소**하므로, 궤적은 맞지만 직진이 0.065 m/s 로
  기어가 "Nav2 가 동작하지 않는다"처럼 보일 상태였다.

### 변경 (기본 상한 1.0 은 유지)

| 항목 | 내용 |
|---|---|
`differential_drive.required_max_wheel_rad_s()` | 신규 순수 함수. 봉투 두 꼭짓점 `(\|v\|, ±\|ω\|)`에서 기존 `cmd_vel_to_wheel_rad_s()` 를 호출해 절댓값 최대를 취한다 — 기구학식 중복 없음 |
`config/speed_profile_slow.yaml` | 신규 오버레이, `max_wheel_rad_s: 2.0` |
`config/speed_profile_nav2.yaml` | 신규 오버레이, `6.0` + 실기 미검증 경고 |
`launch/stm_serial_bridge.launch.py` | `speed_profile:=bench\|slow\|nav2`(기본 `bench`), `max_wheel_rad_s:=<float>` |
`config/stm_serial_bridge.yaml` | **주석만** 추가 (봉투 계산표·프로파일 사용법). 값 `1.0` 유지 |
`stm_serial_bridge_node.py` | **수정하지 않음** — `_log_parameters()`(`:435-438`)가 이미 `max_wheel_rad_s` 를 경고 문구와 함께 출력하고 있었다 |

**파라미터 우선순위**: `base YAML` → `speed_profile 오버레이` → `launch 인자`.

### 명령과 결과

```bash
cd ros2_ws
colcon build --symlink-install                        # 경고 0
python3 -m pytest src/stm_serial_bridge/test/ -q      # 347 passed in 1.37s
bash scripts/verify_bridge_mock.sh                    # 3/3 통과, 잔존 프로세스 없음
```

**단위 테스트: 347 passed** (기존 329 + 신규 18). 기존 329 **회귀 없음**.
신규는 직진만/제자리회전만/최악조합, 각속도·선속도 부호 무관, 영(0) 봉투, 두 함수 정합
교차검증, `wheel_radius`/`separation` 0 이하 `ValueError`, 비유한 전파(`nan > 0.0`이
False 여서 NaN 이 0.0 으로 삼켜지는 함정 고정), 벤치 상한(1.0) < 요구(6.0) 회귀 고정.

### ★ 프로파일 실효성 검증 (mock/PTY, `linear.x=0.3` → 요구 4.615 rad/s)

| 실행 | 기대 송신 | 실제 송신 | 결과 |
|---|---|---|---|
`(기본)` | `SET_WHEEL_VEL,1.000,1.000` | `1.000,1.000` | ✅ |
`speed_profile:=slow` | `2.000,2.000` | `2.000,2.000` | ✅ |
`speed_profile:=nav2` | `4.615,4.615` | `4.615,4.615` | ✅ |
`max_wheel_rad_s:=3.5` | `3.500,3.500` | `3.500,3.500` | ✅ |
`slow` + `max_wheel_rad_s:=3.5` | `3.500,3.500` (인자 우선) | `3.500,3.500` | ✅ |
`speed_profile:=turbo` | 명확히 실패 | exit 1, `provided value "turbo" is not valid. Valid options are: ['bench', 'nav2', 'slow']` | ✅ |

- `nav2` 프로파일의 상한은 6.0 이지만 직진 요구량이 4.615 이므로 **4.615 가 송신되는 것이
  정상**이다(6.000 이 나오면 오히려 잘못된 것). 즉 이 프로파일에서는 제한이 걸리지 않는다.

### ⚠️ 실제 장비에서 검증하지 않은 것 (성공으로 단정하지 말 것)

- **`slow`(2.0)·`nav2`(6.0) 프로파일의 실제 주행** — mock 에서 **송신 문자열만** 확인했다.
  모터가 그 속도를 실제로 내는지, 부하·전류·바닥 마찰에서 어떻게 되는지는 **전부 미검증**
- **`bench`(1.0 → 0.065 m/s)가 바닥에서 움직이는지** — 모터 데드밴드(PWM<20 비선형) 미만일
  가능성이 있어 **아예 안 움직일 수 있다**
- `wheel_separation_m=0.30` 은 여전히 **미실측 placeholder** — 회전 성분 환산이 틀어지면
  6.0 이 의도한 것보다 큰 속도를 의미할 수 있다
- Nav2 `velocity_smoother` 가 실제로 `/cmd_vel` 에 발행하는지 — 이 머신에 `nav2_bringup`
  **미설치**로 확인 불가. 브랜치 문서(`ROS2_API.md:14`)의 주장에 근거한 값이다
- Nav2 쪽 `max_vel_x`/`max_vel_theta` 자체도 `TODO-팀확인` 표기 — 봉투 정합의 최종 결정은
  팀 합의 사항이다
- 엔코더 count/rev 12.1% 차이 원인 **미확정** (PI 게인 0.0f 라 지금은 open-loop 로 무영향)

### 보류

`target_watchdog.py`(사서 유실 타임아웃 순수 로직)는 계획에 있으나 **이번 단계에서 착수하지
않았다** — 실기 확인 뒤로 보류.

## 2026-08-04 — ✅ ROS2: stm_serial_bridge launch/YAML/mock 검증 워크플로우 추가, mock 3시나리오 통과 + 329 tests (Claude)

- **환경**: Ubuntu 22.04, ROS2 Humble, Python 3.10. **하드웨어 없음** — 실제 `/dev/ttyACM*`를
  전혀 열지 않고 Linux PTY 만 사용
- **커밋**: 브랜치 `em/feature/motor-control` (HEAD `76dee46`, 미커밋 상태)
- **추가한 것**: launch 파일, 파라미터 YAML, STM 대역 mock, 토픽 자동 검증 도구, 회귀 스크립트
  (기존 노드·파서·펌웨어는 **변경 없음**)

### 명령과 결과

```bash
cd ros2_ws
colcon build --symlink-install                          # 경고 0
python3 -m pytest src/stm_serial_bridge/test/ -q        # 329 passed in 1.11s
bash scripts/verify_bridge_mock.sh                      # 3/3 통과
```

| 시나리오 | 확인 내용 | 결과 |
|---|---|---|
| 1. connect | mock STATUS → `/stm/*` 6개 토픽 발행, 원소 수 2, `connected=true` | ✅ |
| 2. cmd_vel | `/cmd_vel` → `SET_WHEEL_VEL` → mock → STATUS → `encoder_total` 변화 | ✅ |
| 3. disconnect | STATUS 중단 → `status_timeout_sec`(0.5s) → `connected=false` | ✅ |

- 시나리오 2 실측: `encoder_total` `[17579, 17579]` → `[41457, 41457]` (1초 간격).
  즉 **송신·수신 왕복이 실제로 맞물려 돈다.**
- 시나리오 3 실측: 브리지 로그에 `/stm/connected: true` → `/stm/connected: false`
  (`마지막 유효 STATUS 이후 0.5s 이상 경과`) 전이가 남았다.

### 단위 테스트

**329 passed** (기존 298 + 신규 31). 기존 298개 **회귀 없음**.
신규는 `test_mock_stm.py` — 핵심은 **왕복 테스트**로, mock 이 만든 STATUS 줄을 브리지의
실제 파서(`parse_packet()`)가 읽어 값이 그대로 복원되는지 고정한다. 이게 깨지면 mock 이
펌웨어 형식을 벗어난 것이다.

<details>
<summary>검증 스크립트 출력 (요약)</summary>

```
[1/3] connect — mock STATUS 가 /stm/* 6개 토픽으로 발행되는가
  OK  /stm/wheel_target_rad_s         1  [0.0, 0.0]
  OK  /stm/wheel_actual_rad_s         1  [0.0, 0.0]
  OK  /stm/pwm                        1  [0, 0]
  OK  /stm/encoder_total              1  [0, 0]
  OK  /stm/connected                  1  True
  OK  /stm/fault                      1  NONE
  결과: ✅ 합격
  ---> ✅ connect 통과

[2/3] cmd_vel — /cmd_vel 이 mock 까지 갔다가 encoder_total 변화로 돌아오는가
encoder_total 1차: array('i', [17579, 17579])
encoder_total 2차: array('i', [41457, 41457])
  누적 count 가 변화했다 (TX -> mock -> STATUS -> 토픽 왕복 성립)
  ---> ✅ cmd_vel 통과

[3/3] disconnect — STATUS 중단 후 status_timeout_sec 로 connected=false 가 되는가
  OK  /stm/connected                  2  False
  모드: STATUS 중단 → connected=false 확인
  결과: ✅ 합격
  ---> ✅ disconnect 통과

 결과: ✅ 3개 시나리오 전부 통과 (잔존 프로세스 없음)
```

</details>

### ⚠️ 중간에 발견하고 고친 결함 (검증 신뢰도에 직접 영향)

**첫 실행에서 시나리오 2·3의 결과가 오염됐다.** 스크립트의 `cleanup()`이 `ros2 launch`
프로세스만 종료하고 그 자식(`mock_stm`, 브리지 노드)은 **고아로 남겼다.** 그래서 시나리오 3
시점에 **브리지 노드 3개가 같은 토픽에 동시 발행**하고 있었다
(증상: cmd_vel 을 주지 않은 시나리오 3에서 `encoder_total`이 `[70275, 70275]`로 나옴).

- 원인: 백그라운드 launch 가 스크립트와 **같은 프로세스 그룹**이어서 그룹 단위 종료를 못 했다
- 수정: `setsid` 로 별도 프로세스 그룹에 띄우고 **그룹 전체**에 SIGINT → 대기 → SIGKILL.
  그룹 ID가 스크립트 자신의 것과 같으면 그룹 kill 을 하지 않는 안전장치도 넣었다
  (자기 자신을 죽이는 사고 방지)
- 재검증: 시나리오 3 의 `encoder_total`이 `[0, 0]`으로 정상 격리됨을 확인했고,
  스크립트 마지막에 **잔존 프로세스 검사**를 추가해 같은 실수가 조용히 넘어가지 않게 했다
- ⚠️ **위 표의 결과는 수정 후 재실행한 값이다.** 수정 전 첫 실행 결과는 신뢰할 수 없다.

### 하드웨어 없이 검증하지 못한 것 (성공으로 단정하지 말 것)

- `wheel_actual_rad_s` 의 **수치 정확도** — mock 은 `actual = target` 스텁이므로 스케일을
  검증할 수 없다. 엔코더 count/rev 12.1% 차이 원인은 **여전히 미확정**
- 실제 모터 구동·부하·전류, 실제 USB Serial 전기적 특성
- 실제 Stall 발생 시 **펌웨어의** FAULT 판정 (mock 은 형식만 흉내)
- USB 강제 분리 시 RX fatal error 처리
- `wheel_separation_m=0.30` 실측, 실제 바닥 주행

### 알려진 거친 부분 (미수정, 기능 영향 없음)

launch 에 SIGINT 를 주면 브리지 노드가 `destroy_node()` 중 `KeyboardInterrupt` traceback 을
찍고 exit code -2 로 죽는다(launch 가 ERROR 로 보고). 노드 종료 경로의 문제이고 이번 작업
범위(launch/검증 워크플로우)를 벗어나므로 **고치지 않았다.**

## 2026-08-04 — ✅ EM 실기: 기어비 51:1 펌웨어 빌드·플래시·전진/후진 동작 확인 / ⚠️ actual_rad_s 수치 정확도는 미검증 (relu 실기 / Claude 문서 반영)

- **대상**: `embedded/motor/stm32_workspace/motor-control/Application/Config/motor_config.h`
  (2026-08-03에 `MOTOR_GEAR_RATIO` 100.0f → **51.0f**로 정정한 그 변경의 실기 반영)
- **실행자·환경**: relu. **Windows STM32CubeIDE**에서 빌드·플래시, 실기 동작 확인
- **커밋**: 브랜치 `em/feature/motor-control` (HEAD `76dee46`). **이번 작업은 문서만 수정, 코드 변경 0줄**

### 결과

| 항목 | 결과 |
|---|---|
| STM32CubeIDE 펌웨어 빌드 | ✅ **성공** |
| 보드 플래시 | ✅ **성공** |
| 전진 동작 | ✅ **정상** |
| 후진 동작 | ✅ **정상** |
| `actual_rad_s` 수치 정확도 | ⚠️ **미검증** |
| count/rev 12.1% 차이 원인 | ⚠️ **미확정 (그대로 남음)** |

- 이번 변경은 상수 하나(`MOTOR_GEAR_RATIO`)뿐이며, 전진/후진 동작에 **회귀는 없었다.**

### ⚠️ 이번에 검증되지 **않은** 것 (성공으로 단정하지 말 것)

- **`actual_rad_s`의 수치 정확도**: "전진/후진이 동작한다"만 확인했다. 보고되는 rad/s가 실제 회전
  속도와 얼마나 일치하는지는 **측정하지 않았다.** 정량 데이터가 없다.
- **count/rev 12.1% 차이의 원인**: 이번 빌드로 해결된 것이 **아니다.** 감속비 기재만 정정했고
  명목 **77520**(=380×51×4) vs 실측 **68162.5**의 차이는 그대로다.
  → STATUS의 LA/RA와 `/stm/wheel_actual_rad_s`는 **여전히 실제보다 약 12% 작게 보고된다**는
  전제로 해석해야 한다.
- 원인 후보(미구분): CPR 380의 정의 / Quadrature 배율(TI12 = x4 가정) /
  타이머 입력 필터(`IC1Filter`/`IC2Filter`=8) / 실제 하드웨어 감속비.
- Stall/`FAULT` 계열 실기 검증, `RESET_STALL` 송신, STATUS 중단 시 연결 상태 전이, USB 강제 분리,
  `wheel_separation_m=0.30` 실측, 실제 바닥 주행 — 모두 **여전히 미검증**.

### 확인 사항: 엔코더 상태의 ROS2 연동은 **이미 구현되어 있다** (신규 구현 없음)

"STM 엔코더 상태를 ROS2 토픽으로 발행" 요구사항을 코드베이스에서 재분석한 결과, 전 구간이
이미 구현되어 있고 **2026-08-03 실기 검증까지 완료**된 상태였다. 따라서 **신규 구현을 하지 않았다.**

```
STM StatusReporter (10Hz)
  → "STATUS,<LT>,<LA>,<RT>,<RA>,<LPWM>,<RPWM>,<LE>,<RE>\r\n"
  → SerialLink.read_available() → LineDecoder.feed() → parse_packet()
  → ROS2 Publish
```

| 요구 값 | 이미 발행되는 토픽 | 타입 | 단위 |
|---|---|---|---|
| 좌/우 누적 encoder count | `/stm/encoder_total` | `Int32MultiArray [left, right]` | count |
| 좌/우 wheel speed | `/stm/wheel_actual_rad_s` | `Float32MultiArray [left, right]` | **rad/s** |

- 속도 단위는 **rad/s로 통일**되어 있다. RPM은 `motor.c`의 중간 계산 변수로만 존재하고
  패킷·토픽에는 나가지 않는다. `SET_WHEEL_VEL` 명령 단위와 같아 target/actual을 같은 축에서
  비교할 수 있고 ROS2 관례에도 맞으므로 **변경하지 않았다.**
- ⚠️ 와이어 필드 순서는 **좌우 교차**(`LT,LA,RT,RA`)다. `target_L,target_R,actual_L,actual_R`이 아니다.

### count/rev 실측값 68162.5의 정확한 의미 (오해 방지)

2026-08-03 원본 기록(이 로그 아래쪽 항목)을 재확인한 결과:

| 대상 | 구간 | 변화량 | 회전 수 |
|---|---|---|---|
| Left | 136320 → 205017 | 68697 | 1회전 |
| Left | 205071 → 408805 | 203734 | 3회전 |
| Right | 138 → 68603 | 68465 | 1회전 |
| Right | 68931 → 273335 | 204404 | 3회전 |

- Left: (68697 + 203734) / **4회전** = **68107.75** count/**1회전**
- Right: (68465 + 204404) / **4회전** = **68217.25** count/**1회전**
- 좌우 전체 평균 = **68162.5 count / 바퀴 1회전** (좌우 각 4회전, 합계 8회전 측정의 평균)

⚠️ **68162.5는 "바퀴 1회전당" count다. "출력축 8회전 누적 count"가 아니다.**
(8회전은 평균을 낸 표본 수이지 68162.5가 대응하는 회전 수가 아니다.)

### 다음 실기 검증 절차 (하드웨어 확보 시)

정확도 검증은 **목표/보고 속도 비교가 아니라 1회전 전후 `encoder_total` 차이 측정**으로 한다.

```bash
export ROS_LOCALHOST_ONLY=1
cd /home/relu/geonhee/jolae-git/ros2_ws
source /opt/ros/humble/setup.bash && source install/setup.bash

# 1) Bridge 실행 (바퀴 공중 상태)
ros2 run stm_serial_bridge stm_serial_bridge_node --ros-args \
  -p dry_run:=false -p serial_port:=/dev/ttyACM0 -p baud_rate:=115200 \
  2>&1 | tee ~/stm_$(date +%Y%m%d_%H%M%S).log

# 2) 기본 상태 확인
ros2 topic echo /stm/connected --qos-durability transient_local   # true
ros2 topic hz /stm/wheel_actual_rad_s                             # 약 10Hz

# 3) ★ 스케일 검증 — 모터 미구동(target 0), 손으로 출력축을 정확히 1회전
ros2 topic echo /stm/encoder_total
#    회전 직전 값과 직후 값을 기록해 차이를 계산. 좌우 각각 4회 이상 반복해 평균.
```

**합격 기준**

| 항목 | 기준 |
|---|---|
| 1회전당 count 변화량 | 좌우 각각 재현성 있게 측정되고, 좌우 편차가 **1% 이내** |
| 판정 A | 평균이 **68162.5 근처** → 기존 실측 재확인 (명목 77520이 틀림) |
| 판정 B | 평균이 **77520 근처** → 명목값이 맞고 2026-08-03 측정에 오차가 있었음 |
| 판정 C | 둘 다 아님 → 추가 원인 조사 (IC Filter 등. `.ioc` 변경은 사용자 승인 필요) |
| 좌우 매핑 | 물리 왼쪽만 돌릴 때 `encoder_total[0]`만 변화 (2026-08-03 확정분 재확인) |

⚠️ **합격 기준에서 제외한 것**: "Target 2.0 rad/s를 주면 Actual이 약 1.76 rad/s가 된다" 같은
목표-실제 속도 비교. Actual은 **모터 부하·마찰·제어 상태에 따라 달라지므로** 스케일 판정 근거로
쓸 수 없다. (이전 문서에 이런 기대값이 합격 기준처럼 적혀 있었고, 이번에 제거했다.)

### 이 기록의 한계

- 빌드·플래시·전진/후진 결과는 **사용자 구두 보고값**이며, **CubeIDE 빌드 로그 원본은 확보되지
  않았다.** 이 환경에는 `arm-none-eabi-gcc`가 없어 STM32 펌웨어 빌드를 재현할 수 없다.
- 전진/후진은 **정성적 동작 확인**이며 속도·거리 정량 측정이 없다.
- 하드웨어가 SSAFY에 있어 이번 세션에서는 실기 검증이 불가능했다 — 문서 정리만 수행했다.

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
