"""쫄래쫄래 선반카트 라이다 자기차폐 각도 객관 산정.

한 개의 bag(정지→직진→정지→회전→정지→복귀→정지 시퀀스)에서
정지 구간을 자동 검출하고, 여러 자세에서 (방위, 거리)가 모두 불변인 빈만
'자기 구조물'로 판정한다. 실내 물체는 자세가 바뀌면 방위·거리가 변한다.

사용: python3 scan_analyze.py <bag_dir>
"""

import math
import sys

import numpy as np
import rclpy.serialization as ser
import rosbag2_py
from sensor_msgs.msg import LaserScan

BIN = 1.0  # 도
SELF_MAX_R = 1.6  # 자기 구조물 후보 최대 거리 [m]
SELF_STD = 0.03  # 구간 내 std 허용 [m]
SELF_DRIFT = 0.05  # 자세 간 중위수 변동 허용 [m]
SELF_VALID = 0.60  # 구간 내 유효율 하한
DEAD_VALID = 0.20  # 완전 차폐 판정 유효율 상한
STOP_MIN_SEC = 2.5  # 정지 구간 최소 길이


def read_bag(path: str) -> tuple[np.ndarray, np.ndarray, LaserScan]:
    """bag에서 (스탬프[s], ranges 행렬, 첫 메시지)를 읽는다."""
    r = rosbag2_py.SequentialReader()
    r.open(
        rosbag2_py.StorageOptions(uri=path, storage_id="sqlite3"),
        rosbag2_py.ConverterOptions("", ""),
    )
    ts, rows, first = [], [], None
    while r.has_next():
        topic, data, t = r.read_next()
        if topic != "/scan":
            continue
        m = ser.deserialize_message(data, LaserScan)
        if first is None:
            first = m
        ts.append(t / 1e9)
        rows.append(np.asarray(m.ranges, dtype=np.float64))
    return np.asarray(ts), np.vstack(rows), first


def valid_mask(a: np.ndarray, rmin: float, rmax: float) -> np.ndarray:
    """유효 측정 마스크. 마스킹/무반사 빔은 0.0으로 오므로 제외한다."""
    return np.isfinite(a) & (a >= rmin) & (a <= rmax) & (a > 0.0)


def segments(
    ts: np.ndarray, A: np.ndarray, vm: np.ndarray
) -> tuple[np.ndarray, float, list[list], list[tuple[int, int]]]:
    """프레임별 운동에너지로 정지/이동 구간을 분할한다."""
    n = len(ts)
    e = np.zeros(n)
    for k in range(1, n):
        both = vm[k] & vm[k - 1]
        if both.sum() > 20:
            e[k] = np.median(np.abs(A[k, both] - A[k - 1, both]))
    e[0] = e[1] if n > 1 else 0.0
    thr = max(np.percentile(e, 25) * 3.0, 0.02)
    moving = e > thr
    # 짧은 튐 제거 (3프레임 이하)
    out, i = [], 0
    while i < n:
        j = i
        while j + 1 < n and moving[j + 1] == moving[i]:
            j += 1
        out.append([i, j, bool(moving[i])])
        i = j + 1
    merged = []
    for s in out:
        if merged and (s[1] - s[0] + 1) <= 3:
            merged[-1][1] = s[1]
        else:
            merged.append(s)
    stops = [
        (a, b) for a, b, mv in merged if not mv and (ts[b] - ts[a]) >= STOP_MIN_SEC
    ]
    return e, thr, merged, stops


def bin_stats(
    A: np.ndarray, vm: np.ndarray, bearings: np.ndarray, lo: int, hi: int
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """구간 [lo,hi]의 1도 빈별 (유효율, 중위수, std)."""
    edges = np.arange(-180.0, 180.0 + BIN, BIN)
    idx = np.clip(np.digitize(bearings, edges) - 1, 0, len(edges) - 2)
    nb = len(edges) - 1
    ratio, med, std = np.zeros(nb), np.full(nb, np.nan), np.full(nb, np.nan)
    sub, subv = A[lo : hi + 1], vm[lo : hi + 1]
    for b in range(nb):
        cols = np.where(idx == b)[0]
        if not len(cols):
            continue
        vals = sub[:, cols]
        ok = subv[:, cols]
        tot = vals.size
        ratio[b] = ok.sum() / tot if tot else 0.0
        if ok.sum() >= 5:
            v = vals[ok]
            med[b] = float(np.median(v))
            std[b] = float(np.std(v))
    return edges[:-1], ratio, med, std


def merge_runs(
    flag: np.ndarray,
    centers: np.ndarray,
    hole: int = 3,
    minrun: int = 4,
    margin: float = 1.5,
) -> list[tuple[float, float]]:
    """부울 배열을 구간으로 병합(구멍 닫기 → 짧은 런 제거 → 마진)."""
    f = flag.copy()
    n = len(f)
    i = 0
    while i < n:  # 구멍 닫기
        if not f[i]:
            j = i
            while j < n and not f[j]:
                j += 1
            if 0 < i and j < n and (j - i) <= hole:
                f[i:j] = True
            i = j
        else:
            i += 1
    runs, i = [], 0
    while i < n:
        if f[i]:
            j = i
            while j + 1 < n and f[j + 1]:
                j += 1
            if (j - i + 1) >= minrun:
                runs.append((centers[i] - margin, centers[j] + margin))
            i = j + 1
        else:
            i += 1
    return runs


def fit_translation(
    med_a: np.ndarray, med_b: np.ndarray, centers: np.ndarray, env: np.ndarray
) -> dict[str, float] | None:
    """정지자세 A→B가 순수 병진이라 가정하고 방향·거리를 최소제곱 추정.

    dr_i = -d * cos(theta_i - theta_fwd) = a*cos + b*sin  =>  fwd = atan2(-b,-a)
    """
    m = env & np.isfinite(med_a) & np.isfinite(med_b)
    if m.sum() < 30:
        return None
    dr = med_b[m] - med_a[m]
    th = np.radians(centers[m])
    M = np.vstack([np.cos(th), np.sin(th)]).T
    coef, *_ = np.linalg.lstsq(M, dr, rcond=None)
    pred = M @ coef
    ss = float(np.sum((dr - pred) ** 2))
    tot = float(np.sum((dr - dr.mean()) ** 2))
    r2 = 1.0 - ss / tot if tot > 0 else 0.0
    return dict(
        fwd_deg=math.degrees(math.atan2(-coef[1], -coef[0])),
        dist=float(math.hypot(*coef)),
        r2=r2,
        n=int(m.sum()),
    )


def best_shift(
    med_a: np.ndarray, med_b: np.ndarray, env: np.ndarray
) -> tuple[float, float]:
    """정지자세 A→B의 순환 시프트(회전) 추정. 부호로 inverted 판정."""
    a = np.where(env & np.isfinite(med_a), med_a, np.nan)
    b = np.where(env & np.isfinite(med_b), med_b, np.nan)
    best, bs = -1e18, 0
    for s in range(len(a)):
        bb = np.roll(b, s)
        m = np.isfinite(a) & np.isfinite(bb)
        if m.sum() < 40:
            continue
        x, y = a[m], bb[m]
        sc = -float(np.mean(np.abs(x - y)))  # 음의 평균절대차 = 유사도
        if sc > best:
            best, bs = sc, s
    return (bs + 180) % 360 - 180, best


def main() -> None:
    """bag을 분석해 자기차폐 구간·전방각·회전부호를 보고한다."""
    bag = sys.argv[1]
    ts, A, first = read_bag(bag)
    rmin, rmax = first.range_min, first.range_max
    bearings = np.degrees(
        first.angle_min + np.arange(A.shape[1]) * first.angle_increment
    )
    bearings = (bearings + 180.0) % 360.0 - 180.0
    vm = valid_mask(A, rmin, rmax)
    dur = ts[-1] - ts[0]
    print(f"bag={bag}")
    print(
        f"frames={len(ts)} dur={dur:.1f}s hz={len(ts)/dur:.2f} "
        f"beams={A.shape[1]} inc={math.degrees(first.angle_increment):.4f}deg "
        f"range=[{rmin:.2f},{rmax:.2f}]"
    )

    e, thr, segs, stops = segments(ts, A, vm)
    print(
        f"\n운동에너지 임계={thr:.4f} m, 검출 구간={len(segs)}, "
        f"정지구간={len(stops)}"
    )
    for k, (a, b) in enumerate(stops):
        print(f"  stop#{k}: frames {a}-{b}  t={ts[a]-ts[0]:.1f}~{ts[b]-ts[0]:.1f}s")
    if len(stops) < 2:
        print("\n!! 정지 자세가 2개 미만 — 자세 간 비교 불가. 주행 시퀀스 재수집 필요")
        return

    S = [bin_stats(A, vm, bearings, a, b) for a, b in stops]
    centers = S[0][0]
    R = np.vstack([s[1] for s in S])
    M = np.vstack([s[2] for s in S])
    D = np.vstack([s[3] for s in S])

    with np.errstate(invalid="ignore"):
        near = np.nanmax(M, axis=0) < SELF_MAX_R
        tight = np.nanmax(D, axis=0) < SELF_STD
        drift = (np.nanmax(M, axis=0) - np.nanmin(M, axis=0)) < SELF_DRIFT
        seen = np.nanmin(R, axis=0) > SELF_VALID
        self_f = near & tight & drift & seen & np.all(np.isfinite(M), axis=0)
        dead_f = np.nanmax(R, axis=0) < DEAD_VALID
        env_f = ~self_f & ~dead_f & np.any(np.isfinite(M), axis=0)

    print(f"\n판정: SELF={self_f.sum()} DEAD={dead_f.sum()} ENV={env_f.sum()} / 360 빈")
    print(f"{'구간(deg)':>16} {'폭':>4} {'med(m)':>8} {'std':>6} {'drift':>6} {'판정'}")
    for label, fl in (("SELF", self_f), ("DEAD", dead_f)):
        for lo, hi in merge_runs(fl, centers, margin=0.0):
            sel = (centers >= lo) & (centers <= hi)
            has = bool(np.isfinite(M[:, sel]).any())
            mm = np.nanmedian(M[:, sel]) if has else float("nan")
            ds = np.nanmax(D[:, sel]) if has else float("nan")
            dr = (
                np.nanmax(np.nanmax(M[:, sel], 0) - np.nanmin(M[:, sel], 0))
                if has
                else float("nan")
            )
            print(
                f"{f'{lo:+.0f}..{hi:+.0f}':>16} {hi-lo+1:>4.0f} {mm:>8.3f} "
                f"{ds:>6.3f} {dr:>6.3f} {label}"
            )

    mask = self_f | dead_f
    runs = merge_runs(mask, centers)
    pairs = []
    for lo, hi in runs:
        lo, hi = max(lo, -180.0), min(hi, 180.0)
        pairs += [f"{lo:.0f}", f"{hi:.0f}"]
    print("\n제안 ignore_array (마진 1.5deg, 구멍 3deg 닫기, 최소 4deg):")
    print(f'  ignore_array: "{",".join(pairs)}"')
    total = sum(hi2 - lo2 for lo2, hi2 in runs)
    print(f"  구간 {len(runs)}개, 마스킹 폭 합계 {total:.0f}deg")

    print("\n=== 전방각/회전 추정 (연속 정지자세 쌍) ===")
    for k in range(len(stops) - 1):
        f = fit_translation(M[k], M[k + 1], centers, env_f)
        sh, sc = best_shift(M[k], M[k + 1], env_f)
        ft = (
            f"병진: fwd={f['fwd_deg']:+.1f}deg d={f['dist']:.2f}m "
            f"R2={f['r2']:.2f} n={f['n']}"
            if f
            else "병진: 추정 불가"
        )
        print(f"  stop#{k}->#{k+1}  {ft} | 회전시프트={sh:+.0f}deg (유사도 {sc:.3f})")
    print(
        "\n해석: R2>0.8 이고 d가 실제 이동거리와 ±20% 일치하는 쌍의 fwd가 전방각.\n"
        "      회전시프트 부호가 실제 회전방향(CCW=+)의 반대여야 inverted=false 정상."
    )


if __name__ == "__main__":
    main()
