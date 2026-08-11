# 시연 런북 — 로컬 구동 (2026-08-09)

시연 당일 이 문서 하나만 보고 진행할 수 있게 정리한 절차서.
카트(EM) 상태에 따라 **시나리오 A/B/C**로 갈라진다 — 어느 쪽인지는 당일 [판정 절차](#2-당일-판정-절차)로 5분 안에 결정.

| 시나리오 | 조건 | 되는 것 | 빠지는 것 |
|---|---|---|---|
| **A** | localization + navigation 모두 정상 | 추종 · 위치/구역/팝업/LED · **지도 클릭 이동** | — |
| **B** | localization만 정상 | 추종 · 위치/구역/팝업/LED | 지도 클릭 이동 (누르지 말 것) |
| **C** | 둘 다 불안정 | 추종(실물) · 위치/구역/팝업은 **수동 발행 대행** | 지도 클릭 이동 |

---

## 1. 공통 준비 (시연 전날 + 당일 아침)

### 노트북 (BE·FE·브로커·DB)

```powershell
# 0) 서비스 확인 — 둘 다 Running이어야 함
Get-Service MySQL80, mosquitto

# 1) BE (터미널 1) — .env가 원격 브로커를 보므로 반드시 이 오버라이드로 기동
cd <저장소>\backend
$env:MQTT_BROKER_URL='tcp://localhost:1883'; $env:MQTT_USERNAME=''; $env:MQTT_PASSWORD=''
$env:MQTT_POSITION_TOPIC='status/position'; $env:MQTT_POSITION_UNIT='meters'
.\gradlew.bat bootRun

# 2) FE (터미널 2)
cd <저장소>\frontend
pnpm dev --port 8081        # 다른 기기에서 볼 거면: pnpm dev --port 8081 --host
```

- `frontend/.env.development.local`: `VITE_ENABLE_MSW=false` 인지 확인 (실서버 연동)
- DB 확인: 지도 클릭 한 번 해봐서 마커가 반응하면 시드·아핀 다 들어간 것.
  새 PC라면 `backend/src/main/resources/db/`의 `test-room-3zones.sql` →
  `library-map-affine-initial.sql` 순서로 실행
- 방화벽 (관리자 PowerShell, 1회):
  ```powershell
  netsh advfirewall firewall add rule name="MQTT 1883" dir=in action=allow protocol=TCP localport=1883
  ```

### 카트 쪽 (EM·AI에 전달)

- Jetson·라즈베리파이의 MQTT 브로커 주소 = **노트북 고정 IP**
- Jetson: 저장 지도(`library_map`) localization 기동 → RViz **2D Pose Estimate**로
  초기 위치 지정 (카트 실제 위치 클릭 + 바라보는 방향으로 드래그) →
  라이다 점이 지도 벽에 붙는지 확인. **카트를 껐다 켤 때마다 반복**
- 위치 브릿지(`status/position` 발행)와 nav-result 브릿지 기동

---

## 2. 당일 판정 절차 (5분)

카트 기동·Pose Estimate 완료 후, 노트북에서:

```powershell
& "C:\Program Files\mosquitto\mosquitto_sub.exe" -t status/position
```

1. **값이 안 나옴** → 브릿지/네트워크 문제부터 확인 (아래 트러블슈팅). 끝내 안 나오면 **C**
2. **값이 나옴** → 카트를 밀어 이동시키며 관찰:
   - 좌표가 부드럽게 따라오고, 화면(8081) 마커가 실제 위치와 일치 → localization OK
   - 좌표가 튀거나(수 m 점프) 실제와 동떨어짐 → 2D Pose Estimate 재시도 1회 → 그래도면 **C**
3. localization OK면 → 화면에서 **구역 하나 클릭**:
   - 카트가 실제로 출발해 도착 → **A**
   - 무반응 또는 "이동하지 못했어요" → **B**

> 마커 위치가 실제와 수십 cm 이상 어긋나면 [5. 캘리브레이션](#5-캘리브레이션-필요-시에만) 실행 (5분).

---

## 3. 시나리오별 진행

### A. 풀 시연 (localization + navigation)

시연 순서 제안:
1. **추종**: 영상에서 사서 선택 → 추종 시작 → 사서를 따라 구역 진입 →
   화면에 "N구역에 도착했어요!" 팝업 + 슬롯 LED 점등 + 마커·방향 실시간 표시
2. **지도 클릭 이동**: 추종 종료 → 다른 구역/서가/테이블 클릭 → 카트 자율 주행 →
   도착 팝업(서가·구역) 또는 토스트(테이블)
3. **장애물**: 이동 경로에 의자 투입 → 카트가 우회 (리허설에서 1회 확인해둘 것)
4. 반납 테이블로 복귀 클릭으로 마무리

### B. 추종 + 위치 표시 (localization만)

- 시연 순서 A의 1번만 수행. **지도 클릭은 절대 하지 않는다**
  (카트가 무반응이고 30초 뒤 "카트 응답이 없어요"가 떠서 김이 샌다)
- 진행자 멘트를 "카트는 사서를 따라다니고, 관제 화면은 위치·구역·정리할 책을 보여준다"로 구성
- 장애물 데모는 추종 중 경로에 의자 투입으로 대체 (추종 경로가 어떻게 반응하는지 리허설 필수)

### C. 추종 + 수동 위치 대행 (최악)

- **EM에게 위치 브릿지 OFF 요청** (이중 발행 시 마커 널뜀 — 필수!)
- 노트북 터미널 3에서:
  ```powershell
  python scripts/manual_position.py
  ```
- 카트(추종)는 실물로 움직이고, 운영자가 카트를 눈으로 보며 위치를 타이핑:

  | 입력 | 동작 |
  |---|---|
  | `z1` `z2` `z3` | 통로 중앙으로 활주 (통로 경유, 0.5 m/s) |
  | `사서` `반납` `s800` `s200` `s100` `s000` | 테이블/서가 정차점으로 활주 |
  | `jump z2` | 순간이동 (마커가 뒤처졌을 때 따라잡기) |
  | `speed 1.5` | 활주 속도 변경 |
  | `540,355` | 평면도 픽셀 직접 지정 |
  | `q` | 종료 |

- 구역 진입 팝업·LED·구역 표시는 실물 위치와 동일하게 동작한다 (FE·BE는 출처를 모름)
- 리허설에서 카트 걸음에 맞는 `speed` 값을 찾아둘 것 (사람 보행 ≈ 1.2 m/s)

---

## 4. 트러블슈팅

| 증상 | 확인 순서 |
|---|---|
| 마커가 안 움직임 | ① mosquitto_sub로 값 오는지 ② BE 로그에 "카트 위치 수신" 있는지 ③ BE가 meters 모드인지 ④ FE가 MSW off인지 |
| Jetson이 브로커 접속 실패 | ① 노트북 IP 맞는지(ipconfig) ② 방화벽 1883 ③ 같은 네트워크인지 |
| 카트가 OFFLINE 표시 | 하트비트(status/cart) 발행 여부 — 수동 발행기는 하트비트 대행함 |
| 마커 위치가 실제와 어긋남 | 캘리브레이션 재실행 (아래 5) |
| 마커가 두 위치를 널뜀 | 이중 발행 — Jetson 브릿지와 수동 발행기 중 하나 끌 것 |
| 도착 팝업이 안 뜸 | 팝업은 **구역 진입 순간** 1회. 이미 구역 안에서 새로고침하면 안 뜸(정상) — 구역 밖으로 나갔다 재진입해야 다시 뜸 |
| 지도 클릭 후 "이동하지 못했어요" | Nav2가 goal 거부(ABORTED/REJECTED) — B 시나리오로 전환 판단 |

## 5. 캘리브레이션 (필요 시에만)

마커가 실제 위치와 어긋날 때. 카트를 아는 세 지점에 차례로 놓고:

1. 각 지점에서 `mosquitto_sub -t status/position -C 1`로 SLAM 좌표 기록
2. 세 쌍으로 실행 (지점: 반납 정차점=925,138 / 사서 정차점=350,138 / Z2 중앙=540,355):
   ```powershell
   python scripts/calibrate_map_transform.py --pair="x1,y1=925,138" --pair="x2,y2=350,138" --pair="x3,y3=540,355"
   ```
3. 출력된 UPDATE SQL을 로컬 MySQL(chollae)에 실행 — BE 재시작 불필요
4. **`scripts/manual_position.py` 상단 AFFINE 상수도 같은 값으로 갱신** (C 시나리오 대비)

> 지도를 다시 뜨면(re-mapping) 좌표계가 바뀌므로 캘리브레이션도 다시 해야 한다.

## 6. 참고

- 시연 좌표계·변환의 정본: `library_maps` 아핀 6계수 (backend/CLAUDE.md "status/position" 절)
- 수동 발행기·캘리브레이션 도구 사용법: 각 스크립트 도크스트링
- 이 구성의 검증 기록: [tests/TEST_LOG.md](../tests/TEST_LOG.md) 2026-08-07 ~ 08-09 항목
