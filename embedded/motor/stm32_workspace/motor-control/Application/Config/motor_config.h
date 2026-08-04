#ifndef MOTOR_CONFIG_H
#define MOTOR_CONFIG_H

#include <stdint.h>

/* =========================================================
 * motor_config.h
 * - Motor 하드웨어(모터/기어박스/엔코더/PWM) 및 제어 루프(Feedforward/PI)
 *   관련 설정값을 모아둔다.
 * - 코드 안에 380/100/0.1 같은 숫자를 직접 쓰지 않고, 이 파일의 매크로를
 *   통해서만 참조한다. 값을 바꿔야 하면 이 파일만 수정하면 된다.
 * - 앞으로 Application/Config/ 아래에 communication_config.h, robot_config.h
 *   등이 추가될 예정이며, 이 파일은 그 중 Motor 도메인 담당이다.
 * ========================================================= */

/* =========================================================
 * Motor / Gearbox / Encoder 사양
 * - 모델: PM36-3657-2465E, 24V, 2채널 AB 인크리멘탈 엔코더
 * - 구매 사양: Encoder 380 CPR, Gear Ratio 51:1
 *   (2026-08-03 정정: 이전에 100:1로 적혀 있었으나 실제 구매한 감속비 옵션은 51:1이다)
 * ========================================================= */

/* 기어 감속비 (모터축 51회전 = 바퀴축 1회전). 구매 사양 기준값. */
#define MOTOR_GEAR_RATIO 51.0f

/* 모터 데이터시트 상 Encoder CPR(Counts Per Revolution) */
#define MOTOR_ENCODER_CPR 380.0f

/* ⚠️ 임시 가정(실기 검증 필요): 380 CPR가 Quadrature(x4) 디코딩 "이전" 값인지
 * "이후" 값인지 아직 확정되지 않았다. TIM2/TIM8이 .ioc에서
 * TIM_ENCODERMODE_TI12(양쪽 채널의 양쪽 edge를 모두 카운트하는 x4 디코딩)로
 * 설정되어 있으므로, 이 매크로는 "380 CPR가 x4 디코딩 이전(=채널 1개당 라인 수)"
 * 이라는 가정 하에 4.0f로 두었다. 실기 측정(예: 바퀴 1바퀴 수동 회전 후 Encoder
 * Count 절대값 비교)으로 반박되면 이 값만 1.0f 등으로 수정하면 된다. 다른 코드는
 * 손댈 필요 없다. */
#define MOTOR_ENCODER_QUADRATURE_MULTIPLIER 4.0f

/* 바퀴(출력축) 1회전당 누적 Encoder Count.
 * = Encoder CPR x Gear Ratio x Quadrature Multiplier
 * 위 세 매크로만 정정하면 이 값도 자동으로 갱신된다.
 *
 * ⚠️ 이 값은 **구매 사양 기준의 명목값**이며 실측 보정값이 아니다.
 *    현재: 380 x 51 x 4 = 77520 count/wheel-rev
 *
 * === 2026-08-03 출력축 수동 회전 실측 (좌우 각 4회전, 총 8회전) ===
 *   Left  평균 68107.75 count/rev
 *   Right 평균 68217.25 count/rev
 *   좌우 전체 평균 68162.5 count/rev
 *
 *   명목값 77520 대비 약 -12.1% (실측이 더 작다).
 *   좌우 측정값은 서로 약 0.16% 차이로 매우 일관적이므로 측정 오차나 한쪽 하드웨어
 *   이상이라기보다 사양/설정 쪽 원인일 가능성이 높다.
 *
 *   원인은 **아직 미확정**이다. 아래 중 어느 것인지 이 데이터만으로는 구분할 수 없다:
 *     - CPR 380의 정의(채널당 라인 수인지, 이미 quadrature 적용된 값인지)
 *     - Quadrature 배율(TI12 = x4 가정이 맞는지)
 *     - 타이머 입력 필터(IC1Filter/IC2Filter = 8)로 인한 edge 누락
 *     - 실제 하드웨어 사양이 구매 사양과 다름
 *   참고로 실측을 정확히 맞추려면 유효 감속비 약 44.84:1 또는 유효 CPR 약 334.1이
 *   필요하지만, 그 값들을 코드에 강제 적용하지 않았다 — 원인을 모른 채 숫자만 맞추면
 *   다른 조건에서 다시 틀어진다.
 *
 *   → 후속 캘리브레이션 필요. 그때까지 STATUS의 LA/RA(actual_rad_s)는 실제보다
 *     약 12% 작게 보고된다는 점을 전제로 해석해야 한다. */
#define MOTOR_ENCODER_COUNTS_PER_WHEEL_REV \
    (MOTOR_ENCODER_CPR * MOTOR_GEAR_RATIO * MOTOR_ENCODER_QUADRATURE_MULTIPLIER)

/* =========================================================
 * Actual Wheel Velocity 계산 주기
 * - Motor_Process()는 Main Loop 매 tick(수 ms 미만 간격 추정)마다 호출되므로,
 *   매 tick 엔코더 델타로 속도를 계산하면 델타가 너무 작아 양자화 오차가
 *   지배적이게 된다. 따라서 별도의 고정 주기로만 계산한다.
 * - STATUS Packet 송신 주기(STATUS_REPORTER_INTERVAL_MS, status_reporter.c)와는
 *   의도적으로 분리된 별개의 설정값이다: 속도 계산(Motor, 향후 PID의 입력)과
 *   텔레메트리 송신 주기(Communication)는 서로 다른 이유로 바뀔 수 있는
 *   독립적인 관심사이기 때문이다. 현재는 우연히 같은 100ms를 쓰지만, 예를 들어
 *   PID 도입 후 제어 주기를 더 촘촘하게(예: 10~20ms) 가져가야 한다면 이 값만
 *   바꾸면 되고 STATUS 송신 주기는 그대로 유지할 수 있다.
 * ========================================================= */
#define MOTOR_SAMPLE_PERIOD_SEC 0.1f

/* HAL_GetTick()(ms 단위)과 비교하기 위해 MOTOR_SAMPLE_PERIOD_SEC로부터 파생.
 * 숫자를 별도로 새로 쓰지 않고 위 값에서만 계산한다. */
#define MOTOR_SAMPLE_PERIOD_MS ((uint32_t)(MOTOR_SAMPLE_PERIOD_SEC * 1000.0f))

/* =========================================================
 * PWM
 * ========================================================= */

/* TIM3/TIM4 PWM 유효 범위(0~99)와 동일 (motor.c Motor_LimitPwm 참고) */
#define MOTOR_PWM_MAX 99

/* =========================================================
 * Feedforward (Open-Loop) 변환 파라미터
 * - PI Speed Controller 도입 이후에도 이 값들은 그대로 Feedforward
 *   추정치 계산에 재사용된다("target -> 대략적인 PWM" 순수 함수).
 * - 값은 motor.c에서 그대로 옮겨온 것이며 변경하지 않았다. 실기 검증 전
 *   잠정값이라는 성격도 동일하게 유지된다.
 * ========================================================= */
#define MOTOR_OPEN_LOOP_PWM_PER_RAD_S  10.0f   /* 잠정값: 실기 테스트로 조정 */
#define MOTOR_TARGET_DEADBAND_RAD_S    0.05f   /* 잠정값: 실기 테스트로 조정 */

/* 좌우 모터 장착 방향 보정: 1 또는 -1.
 * 기본값은 기존 Motor_Forward()/Motor_Backward()의 채널 매핑과 동일하게
 * 맞춰져 있다. 실제 로봇에서 SET_WHEEL_VEL,5,5 명령에 특정 바퀴가
 * 반대로 회전하면 해당 매크로만 -1로 바꾼다. */
#define MOTOR_LEFT_DIRECTION_SIGN      1
#define MOTOR_RIGHT_DIRECTION_SIGN     1

/* 좌우 엔코더 회전 방향 보정: 1 또는 -1. MOTOR_LEFT/RIGHT_DIRECTION_SIGN과는
 * 독립적인 값이다(엔코더 A/B 채널 배선 극성은 모터 +/- 배선과 별개이기 때문).
 * 기본값은 "PWM 양수(전진)일 때 Encoder Count도 증가한다"고 가정한 것이다.
 * 실기에서 바퀴를 손으로 전진 방향으로 돌렸을 때 Actual(LA/RA)이 음수로
 * 나오면 해당 매크로만 -1로 바꾼다. */
#define MOTOR_LEFT_ENCODER_DIRECTION_SIGN   1
#define MOTOR_RIGHT_ENCODER_DIRECTION_SIGN  1

/* =========================================================
 * PI Speed Control
 * - Feedforward(위 MOTOR_OPEN_LOOP_PWM_PER_RAD_S 기반)가 추정한 PWM에 대한
 *   보정치만 계산한다. 최종 PWM = Feedforward + PI Correction.
 * - Kp/Ki는 실기 튜닝 편의를 위해 컴파일 타임 상수가 아닌 런타임 변수로
 *   관리한다(값을 바꿀 때마다 Build/Flash를 반복하지 않기 위함). 정의와
 *   기본값은 motor_config.c에 있으며, 여기서는 extern 선언만 한다.
 * - 기본값은 이전 매크로와 동일하게 0.0f다. 둘 다 0이면 PI 보정이 항상
 *   0이 되어 Feedforward만 동작하던 이전 Open-loop 동작과 완전히 동일하다
 *   — 즉 이 값을 튜닝하기 전까지는 기존 동작을 깨지 않는다.
 * - 향후 UART SET_PI_GAINS 명령(미구현)이 이 변수에 직접 대입하는 방식으로
 *   확장될 수 있도록 준비된 구조다.
 * ========================================================= */
extern float motor_pi_kp;   /* 기본값 0.0f(잠정): 실기 튜닝 필요, motor_config.c 참고 */
extern float motor_pi_ki;   /* 기본값 0.0f(잠정): 실기 튜닝 필요, motor_config.c 참고 */

/* UART SET_PI_GAINS 명령(motor/docs/serial_protocol.md)이 허용하는 Kp/Ki 범위.
 * Motor_SetPiGains()가 이 범위를 벗어나면 아무 것도 바꾸지 않고 실패를 반환한다.
 * ⚠️ 실기 튜닝 전 잠정값 — 아래 근거를 바탕으로 한 보수적 추정치다. 실기 튜닝
 * 결과 이 범위가 실제로 필요한 값보다 좁은 것으로 확인되면 이 네 값만 조정한다.
 *
 * - MIN은 둘 다 0.0f: 음의 게인은 오차 부호에 반대로 반응해 피드백을 발산시킬
 *   수 있어 튜닝 목적상 허용하지 않는다(SET_PI_GAINS 요구사항: 음수 게인 차단).
 * - KP_MAX = 50.0f: Feedforward 게인(MOTOR_OPEN_LOOP_PWM_PER_RAD_S = 10.0f)의
 *   5배. P항만으로 오차 2rad/s(Python Tool 기본 속도 1.0 rad/s의 2배 수준)에서
 *   이미 100 PWM%(=MOTOR_PWM_MAX 근방)에 도달하는 지점이라, 그 이상은 최종 PWM
 *   saturation에 걸려 튜닝 관점에서 의미가 없고 과도한 순간 출력만 유발한다.
 * - KI_MAX = 20.0f: Integral은 MOTOR_PI_INTEGRAL_PWM_LIMIT(49.5)로 이미
 *   clamp되어 PWM 범위를 벗어나지는 않지만, Ki가 너무 크면 그 한계에 너무 빨리
 *   도달해 출력이 급변할 수 있다. 정상상태 오차 1rad/s, MOTOR_SAMPLE_PERIOD_SEC
 *   (0.1s) 기준 20.0f는 tick당 Integral을 2.0 PWM%씩 늘려 한계 도달까지 약
 *   2.5초가 걸리는 수준 — 튜닝 중 이상 동작을 보고 ESTOP으로 대응할 시간을
 *   남기면서도 체감 가능한 응답 속도를 확보한다.
 */
#define MOTOR_PI_KP_MIN 0.0f
#define MOTOR_PI_KP_MAX 50.0f
#define MOTOR_PI_KI_MIN 0.0f
#define MOTOR_PI_KI_MAX 20.0f

/* Integral(PWM 단위로 누적)의 clamp 한계. Anti-windup 목적이며, 최종 PWM을
 * MOTOR_PWM_MAX로 saturation하는 것과는 별개의 처리다. 우선 MOTOR_PWM_MAX의
 * 절반을 시작값으로 둔다 — 실기 튜닝 결과에 따라 조정한다. */
#define MOTOR_PI_INTEGRAL_PWM_LIMIT ((float)MOTOR_PWM_MAX / 2.0f)

/* =========================================================
 * Speed Profile (가속/감속 제한 + 방향 전환 보호)
 * - W/A/S/D를 매우 빠르게 전환할 때 한쪽 모터가 멈추는 현상이 실기에서
 *   관측되어 도입한다. BTS7960가 정/역방향을 순간적으로 전환하는 상황에서
 *   보호 동작(과전류 차단 등)에 들어가는 것으로 추정된다.
 * - Feedforward+PI는 이제 requested(요청값)가 아니라 limited(이 프로파일을
 *   통과한 값)를 목표로 삼는다. requested -> limited 변환은 motor.c의
 *   Motor_AdvanceSpeedProfile()이 담당한다.
 * - ⚠️ 아래 5개 값은 모두 하드웨어 전류 한계 등 실측 데이터가 없는 상태의
 *   잠정값이다(MOTOR_PI_KP/KI와 마찬가지로 실기 튜닝 필요). 너무 낮으면
 *   응답이 굼떠지고, 너무 높으면 보호 목적을 달성하지 못한다.
 * ========================================================= */

/* 일반 가속/감속 제한(rad/s^2). 같은 방향 안에서의 속도 변화에 적용된다.
 * 방향이 반전되는 경우는 아래 MOTOR_DIRECTION_CHANGE_DECEL_RAD_S2를 대신 쓴다. */
#define MOTOR_ACCEL_LIMIT_RAD_S2 4.0f  /* 잠정값: 실기 튜닝 필요 */
#define MOTOR_DECEL_LIMIT_RAD_S2 4.0f  /* 잠정값: 실기 튜닝 필요 */

/* 방향 전환(부호가 반대로 바뀌는 요청) 감지 시, requested를 무시하고 limited를
 * 0으로 몰아가는 감속률. 일반 감속(MOTOR_DECEL_LIMIT_RAD_S2)보다 더 급격하게
 * 잡아 0 근처에서 머무는 시간을 짧게 유지한다. */
#define MOTOR_DIRECTION_CHANGE_DECEL_RAD_S2 8.0f  /* 잠정값: 실기 튜닝 필요 */

/* limited가 0에 도달한 뒤, Actual(엔코더 실측값)이 이 값 이내로 들어와야
 * "물리적으로 거의 멈췄다"고 판단하고 Hold 단계로 넘어간다. limited==0
 * 만으로는 부족하다 — PI가 아직 반대 방향 보정 전류를 걸고 있을 수 있어서,
 * 실측 Actual까지 확인하는 것이 이번 보호 기능의 핵심이다. */
#define MOTOR_DIRECTION_ZERO_THRESHOLD_RAD_S 0.1f  /* 잠정값: 실기 튜닝 필요 */

/* 정지 확인 후 반대 방향 가속을 시작하기 전 대기 시간(ms). */
#define MOTOR_DIRECTION_CHANGE_HOLD_MS 200u  /* 잠정값: 실기 튜닝 필요 */

/* =========================================================
 * Stall Detection (소프트웨어 기반 모터 보호)
 * - 목적: 바퀴가 물리적으로 막혀(벽에 걸림, 사람이 손으로 잡음 등) Actual이
 *   거의 0인데도 PI가 Error를 계속 크게 판단해 PWM을 최대치까지 밀어붙이는
 *   상황을 감지해, 그보다 먼저 소프트웨어 단에서 안전하게 정지시킨다.
 * - ⚠️ 전류 센서/ADC 기반이 아니라 PWM/Encoder(Actual Wheel Velocity)만으로
 *   추정하는 간접 보호다. BTS7960 자체의 과전류/과열 보호(하드웨어)를
 *   대체하지 않으며, 그보다 앞단에서 더 이른 시점에 개입하는 것이 목적이다.
 * - ⚠️ 아래 4개 값은 모두 실기 미검증 잠정값이다(다른 Speed Profile/PI 상수와
 *   동일한 성격 — 실기 튜닝 전까지는 근거 기반 추정치로만 취급한다).
 * ========================================================= */

/* PWM duty(0~99, MOTOR_PWM_MAX 기준) 임계값. |motor_last_left/right_pwm|이
 * 이 값 이상이어야 "충분히 강하게 밀고 있다"고 본다. MOTOR_PWM_MAX(99)의
 * 약 80%선으로, 일반적인 기동/가속 구간의 순간적으로 높은 PWM과는 구분하되
 * 실제로 막혔을 때 도달하는 근포화 영역은 포착하도록 잡은 잠정값이다. */
#define MOTOR_STALL_PWM_THRESHOLD 80

/* 목표(limited) 각속도 임계값(rad/s). |motor_limited_left/right_rad_s|가
 * 이 값 이상이어야 "실제로 움직이려는 의도가 있다"고 본다.
 * MOTOR_TARGET_DEADBAND_RAD_S(0.05f)보다 확실히 높게 잡아, 사실상 정지
 * 요청에 가까운 낮은 Target까지 Stall 판정에 끌어들이지 않는다. */
#define MOTOR_STALL_TARGET_RAD_S 0.2f

/* 실측(actual) 각속도 임계값(rad/s). |motor_actual_left/right_rad_s|가 이
 * 값 이하여야 "거의 안 움직인다"고 본다.
 * MOTOR_DIRECTION_ZERO_THRESHOLD_RAD_S와 현재 값(0.1f)은 같지만, 방향 전환
 * Hold 판정과 Stall 판정은 서로 다른 관심사이므로(하나를 튜닝해도 다른
 * 하나가 영향받지 않도록) 의도적으로 별도 매크로로 분리한다. */
#define MOTOR_STALL_ACTUAL_RAD_S 0.1f

/* 위 세 조건이 끊김 없이 연속으로 유지되어야 하는 최소 시간(ms).
 * MOTOR_SAMPLE_PERIOD_SEC(100ms)의 5배로, 최소 5회의 독립된 Actual 샘플이
 * 연속으로 조건을 만족해야 확정되므로 단발성 샘플/일시적 부하로 인한
 * 오검출을 줄인다. 조건이 중간에 한 번이라도 깨지면 타이머는 0부터 다시
 * 시작한다(누적이 아니라 연속 유지 조건). */
#define MOTOR_STALL_DURATION_MS 500u

#endif /* MOTOR_CONFIG_H */
