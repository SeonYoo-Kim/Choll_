# scripts/ — 젯슨 운영·진단 스크립트

> 실기(Jetson Orin Nano)에서 반복 실행하는 기동·종료·진단 도구.
> 사람용 절차의 정본은 [../README.md](../README.md), 규칙은 [../CLAUDE.md](../CLAUDE.md).
> 마지막 갱신: 2026-08-13

## 왜 스크립트인가

기동에 프로세스 9개가 필요하고 순서 의존이 있다. 터미널 9개로 나누면 순서를 틀리거나
중복 기동하기 쉽다 — 실제로 반복된 실패 원인이었다.

- `zupt_node` 2개 → `/odom_zupt` 18.9 Hz (기대 10 Hz), 재기동마다 누적
- `fe_bridge_node` 2개 → 같은 BE WebSocket 을 다투어 FE 영상이 검게 나옴
- Nav2 를 안 내리고 AI 를 띄움 → `/cmd_vel` 발행자 2개, 카트가 예측 불가하게 움직임

🔴 **`pkill -f` 패턴은 반드시 스크립트 파일 안에 둔다.** 호출하는 명령줄에 두면
`pkill -f` 가 자기 셸의 cmdline 을 매칭해 셸이 같이 죽는다(exit 144). 이 저장소에서
여러 번 발생한 사고다.

## 목록

| 스크립트 | 용도 |
|---|---|
| [simple_follow_up.sh](simple_follow_up.sh) | 단순 사서 추종 원커맨드 기동 (9단계 + 단계별 헬스체크) |
| [choll_all_down.sh](choll_all_down.sh) | 전체 스택 안전 순서 종료 |
| [free_mem_for_ai.sh](free_mem_for_ai.sh) | AI 재기동 전 메모리 확보 (CUDA OOM 대응) |
| [mqtt_sniff.py](mqtt_sniff.py) | 브로커 `#` 전체 구독 — 읽기 전용 트래픽 관측 |
| [scan_analyze.py](scan_analyze.py) | bag 에서 라이다 자기차폐 각도 객관 산정 |

---

## simple_follow_up.sh — 단순 추종 기동

```bash
# 🔴 지도 없는 곳에서 추종만 시연 (가장 가벼움)
bash scripts/simple_follow_up.sh --follow-only          # 최근접 인물 자동 선택
bash scripts/simple_follow_up.sh --follow-only --fe     # FE 에서 대상 선택

# 지도 안 — 추종 + 위치를 BE 로 발행 (FE 지도에 카트 표시)
bash scripts/simple_follow_up.sh --fe --init 0 0 0
bash scripts/simple_follow_up.sh --map ~/maps/library_v2.yaml --init 1.2 -0.4 90

bash scripts/simple_follow_up.sh --no-ai                # 위치 스택만 (추종 없이)
```

| 인자 | 뜻 |
|---|---|
| `--follow-only` | 위치추정 스택 전체 생략 (rf2o·EKF·ZUPT·AMCL·map_server·cart_pose·MQTT) |
| `--fe` | FE 에서 대상 선택 (`fe_bridge:=true auto_select:=false`) |
| `--init x y yaw` | AMCL 초기 위치 주입. yaw 는 도(deg) |
| `--map <yaml>` | 지도 교체 (기본 `~/maps/library_v3.yaml`) |
| `--no-ai` | AI 스택을 띄우지 않음 |

기동 순서와 각 단계 기대값:

| 단계 | 내용 | 확인 |
|---|---|---|
| 0 | 기존 프로세스 정리 (`choll_all_down.sh` 호출) | — |
| 1 | STM 시리얼 브릿지 + 휠 오도메트리 | `/stm/connected` = true |
| 2 | 라이다 + `scan_mask_node` | `/scan` 6~12 Hz |
| 3 | rf2o (`publish_tf:=false`) | — |
| 4 | EKF + ZUPT + 공분산 중계 | `/odometry/filtered` 20 Hz |
| 5 | AMCL + map_server (+ lifecycle 자동 activate) | `active [3]` |
| 6 | 초기 위치 5회 발행 | — |
| 7 | `cart_pose_publisher` | `/robot_pose` 10 Hz |
| 8 | MQTT 브릿지 | 브로커 접속 로그 |
| 9 | `/cmd_vel` 발행자 0 확인 → AI 기동 | 0 아니면 **중단** |

로그는 `~/choll_logs/<MMDD_HHMMSS>/` 에 단계별로 떨어진다.

### 일부러 띄우지 않는 것 2개

- **Nav2** — `velocity_smoother` 와 AI `control_node` 가 동시에 `/cmd_vel` 을 발행하면
  두 명령이 번갈아 실려 카트가 예측 불가하게 움직인다. 9단계에서 발행자가 0이 아니면
  기동을 중단한다.
- **`goal_forwarder`** — Nav2 없이 남으면 FOLLOW_START 이후 `/target_position` 마다
  `NAV2_UNAVAILABLE` 을 `status/nav-result` 로 올려 BE 이동 세션을 망친다. 그래서
  `interface.launch.py` 대신 `cart_pose_publisher` 만 `ros2 run` 으로 띄운다.

### `--follow-only` 가 왜 성립하는가

`control_node` 는 `/target_person`(카메라 방위각)과 `/scan`(라이다 거리) **두 개만**
구독한다. TF·지도·오도메트리를 일절 쓰지 않으므로 **지도 밖에서도 추종은 그대로
동작한다.** 반대로 지도 밖에서 AMCL 을 켜 두면 스캔이 지도와 안 맞아 발산하고
`/robot_pose` 가 엉뚱한 좌표를 내보낸다 — 켜는 게 오히려 해롭다.

`--follow-only` 로 절약되는 메모리는 약 540 MB (+ AI 노드 2개 제외 215 MB).
Orin Nano 통합 메모리에서는 이게 `reid_node` 의 CUDA 할당 성공 여부를 가른다.

---

## choll_all_down.sh — 안전 종료

```bash
bash scripts/choll_all_down.sh
```

🔴 **종료 순서가 안전 수칙이다**: 구동 명령 발행자(AI/Nav2/teleop) → `/stm/pwm` 0 확인
→ 시리얼 브릿지 → 라이다. 바퀴를 굴리는 쪽을 먼저 끊지 않으면, 브릿지가 죽는 순간
마지막 명령이 STM 에 남아 카트가 계속 굴러간다. **ROS 비상정지는 없다.**

마지막에 잔존 프로세스를 나열한다 — 아무것도 안 나와야 정상.

---

## free_mem_for_ai.sh — CUDA OOM 대응

```bash
bash scripts/free_mem_for_ai.sh
```

AI 스택 + 불필요 GUI 유틸리티만 내린다. **EM 스택(라이다·SLAM·AMCL·EKF·MQTT·STM)과
데스크톱 세션(gnome-shell·Xorg)은 보존한다** — 세션을 끊으면 RViz 를 못 띄운다.

2026-08-13 실측 근거: `reid_node` 가 OSNet 을 GPU 로 올리다 죽었다.

```
NvMapMemAllocInternalTagged: error 12    (ENOMEM, Tegra 할당기)
torch.AcceleratorError: CUDA error: out of memory
tegrastats: RAM 4482/7620MB (lfb 10x4MB)
```

`lfb`(최대 연속 빈 블록)가 결정적이다. Orin Nano 는 통합 메모리라 CUDA 할당에 **연속
물리 블록**이 필요하고, zram 스왑(3.8 GB)은 CUDA 할당에 쓰이지 못한다. 총량이 남아도
조각나 있으면 실패한다.

실행 결과: RAM 4480 → 2970 MB, **lfb 10x4MB → 49x4MB**.

`drop_caches`·`compact_memory` 는 sudo 가 필요해 비밀번호 없이는 건너뛴다. 효과가
크므로 가능하면 수동으로:

```bash
sudo sh -c 'sync; echo 3 > /proc/sys/vm/drop_caches; echo 1 > /proc/sys/vm/compact_memory'
```

---

## mqtt_sniff.py — 브로커 트래픽 관측

```bash
export CHOLL_MQTT_USER=<계정>
export CHOLL_MQTT_PASS=<비밀번호>
python3 scripts/mqtt_sniff.py 25        # 25초 관측
```

**읽기 전용** — 아무것도 발행하지 않는다. `mosquitto_sub` 가 설치돼 있지 않아 paho 로
직접 구현했다. `client_id` 를 브릿지와 다르게 잡아야 상호 강퇴가 없다.

🔴 자격증명은 하드코딩하지 않는다. 없으면 사용법을 출력하고 종료한다.
`rc != 0` 을 실패로 판정한다 — `fe_bridge_node` 가 rc 를 검사하지 않아 `rc=5`(인증 거부)를
성공으로 로깅한 전례가 있다(2026-08-08).

출력 예 (2026-08-13 실측):
```
[status/target]    115건  ~4.60 Hz   {"image_width":640,...,"tracks":[{"id":44,...}]}
[status/position]   45건  ~1.80 Hz   {"x":0.054,"y":0.059,"yaw":-0.0118,"timestamp":"..."}
[status/cart]        6건  ~0.24 Hz
[carts/status]       1건  ~0.04 Hz   {"status":"offline"}   ← 리테인 잔재
```

문서 3개가 서로 다른 토픽명을 적고 있었을 때, 이 도구의 `#` 구독으로 실측 확정했다
(`embedded/CLAUDE.md` 의 MQTT 계약표).

---

## scan_analyze.py — 자기차폐 각도 산정

```bash
python3 scripts/scan_analyze.py <bag_dir>
```

하나의 bag(정지→직진→정지→회전→정지→복귀→정지)에서 정지 구간을 자동 검출하고,
**여러 자세에서 (방위, 거리)가 모두 불변인 빈만** 자기 구조물로 판정한다. 실내 물체는
자세가 바뀌면 방위·거리가 변하므로 자동으로 배제된다.

⚠️ 산정 결과를 드라이버 `ignore_array` 에 넣지 말 것. 드라이버에서 자르면 rf2o 가
정지 상태에서 −0.4°/s 로 단조 드리프트한다(2026-08-07 통제 실험 4회). 마스킹은
`scan_mask_node` 에서 한다 — 자세한 근거는 그 노드의 docstring.

---

## 복구된 도구 5종 (2026-08-14)

08-10 `git clean` 으로 지워졌다가 `git stash` 의 untracked 영역에서 회수했다.
젯슨 반납 전에 보존한다. 일부는 젯슨 고유 환경(모니터 없음·이미지 편집기 없음)에
대응하려고 만든 것이라, 노트북에서는 더 나은 대안이 있을 수 있다.

| 파일 | 용도 | 상태 |
|---|---|---|
| `choll_up.sh` | Nav2 모드 원커맨드 기동 (`--map`/`--init`/`--simple-follow`/`--linear`/`--angular`/`--down`) | `~/.bashrc` 의 `choll-up`·`choll-down` 별칭이 이 파일을 가리킨다 |
| `choll_ai.sh` | AI 스택만 깨끗하게 1회 기동 (중복 방지) | AI 2개 기동 시 `fe_bridge_node` 가 같은 BE 웹소켓을 다퉈 FE 영상이 검게 나오는 문제 대응 |
| `map_view.py` | `.pgm` 지도를 좌표 눈금과 함께 PNG 로 렌더 (헤드리스) | 젯슨에 이미지 편집기가 없어 만들었다 |
| `map_paint.py` | 지도의 뚫린 벽을 **미터 좌표**로 메운다 (GIMP 대용) | 구멍은 SLAM 오류가 아니라 미관측이다 — 유리·거울·검은 벽은 원리적으로 안 채워진다 |
| `fastdds_unicast_peers.xml` | 멀티캐스트가 막힌 무선망에서 노트북 RViz 가 젯슨을 찾게 하는 Fast DDS 설정 | 도메인 42 유니캐스트 메타트래픽 포트 17910~17940 |

`choll_up.sh` 와 `simple_follow_up.sh` 의 관계:

| | `choll_up.sh` | `simple_follow_up.sh` |
|---|---|---|
| 기본 모드 | **Nav2** (`legacy_control:=false`) | **단순 추종** (`legacy_control:=true`) |
| 구역 이동 | ✅ | ❌ |
| 추종 반응 | Nav2 goal 경유 (느림) | 즉응 |
| 지도 없이 | ❌ | ✅ (`--follow-only`) |
| 속도 인자 | `--linear`/`--angular` | 해당 없음 |

`choll_up.sh --linear/--angular` 는 `nav.launch.py` 의 속도 인자화에 의존한다 —
2026-08-14 통합 완료라 지금은 그대로 동작한다.

⚠️ `nav.launch.py` 의 기본값 `linear 0.45` / `angular 0.4` 는 실주행 체감 기반이고
**실측 검증이 없다.** `angular 0.4` 는 바퀴 1.169 rad/s = PWM 11.7 로 모터
데드존(20) 미만이라 제자리 회전이 안 될 수 있다. 실주행 전에 이 값부터 확인할 것.

`demo.launch.py`(`src/choll_slam_bringup/launch/`)도 함께 복구했다 — 라이다부터
MQTT 상행까지 한 번에 띄우는 런치다. `choll_up.sh` 쪽이 낡은 프로세스 정리·AMCL
lifecycle 강제 활성화·초기 위치 발행·기동 후 검증까지 해 주므로 사람은 그쪽을 쓴다.
