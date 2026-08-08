"""지도 좌표 캘리브레이션 — SLAM 세계 좌표 ↔ FE 평면도 픽셀의 아핀 변환을 대응점으로 푼다.

평면도(map.png)는 SLAM 지도에서 회전·좌우반전·크롭을 거쳐 만들어져, BE의 기존
resolution·origin 방식으로는 좌표가 맞지 않는다. 이 스크립트는 대응점 3개 이상으로
일반 아핀 변환(픽셀 = A·세계좌표 + t)을 최소제곱으로 풀고, `library_maps`에 넣을
UPDATE SQL을 출력한다. BE는 아핀 계수가 채워진 지도에 대해 이 변환을 우선 사용한다
(SlamCoordinateConverter, 2026-08-07).

현장 캘리브레이션 절차 (5분):
  1. 카트(Jetson+LiDAR)를 이 지도로 localization 모드로 띄운다
  2. 평면도상 위치를 아는 지점(예: 반납 테이블 아래 정차점, 사서 테이블 오른쪽 끝,
     Z2 통로 중앙)에 카트를 놓고, 그때 발행되는 SLAM 좌표(status/position)를 받아적는다
  3. 지점당 한 쌍씩, 3쌍 이상(서로 일직선이 아니게!)으로 실행:

     python scripts/calibrate_map_transform.py \
         --pair "1.23,-0.45=925,138" \
         --pair "-2.10,0.80=350,138" \
         --pair "0.50,-3.20=541,570"

     (형식: "세계x,세계y=픽셀x,픽셀y" — 세계는 미터, 픽셀은 평면도 1000x600 기준)
  4. 출력된 UPDATE SQL을 DB에 실행하고 BE를 재시작 없이 그대로 쓴다
     (변환은 요청마다 DB에서 읽는다)

잔차(residual)가 픽셀로 출력된다 — 10px(≈10cm)를 넘으면 대응점을 다시 찍을 것.
"""

from __future__ import annotations

import argparse
import sys


def solve_affine(
    pairs: list[tuple[float, float, float, float]],
) -> tuple[list[float], list[float]]:
    """최소제곱으로 아핀 6계수를 푼다. 반환: ([a11,a12,tx], [a21,a22,ty])"""
    # 픽셀x = a11·wx + a12·wy + tx 와 픽셀y = a21·wx + a22·wy + ty 는 서로 독립 —
    # 같은 3x3 정규방정식을 우변만 바꿔 두 번 푼다 (외부 의존 없이 가우스 소거)
    sxx = sxy = syy = sx = sy = n = 0.0
    bx = [0.0, 0.0, 0.0]
    by = [0.0, 0.0, 0.0]
    for wx, wy, px, py in pairs:
        sxx += wx * wx
        sxy += wx * wy
        syy += wy * wy
        sx += wx
        sy += wy
        n += 1
        bx[0] += wx * px
        bx[1] += wy * px
        bx[2] += px
        by[0] += wx * py
        by[1] += wy * py
        by[2] += py
    matrix = [
        [sxx, sxy, sx],
        [sxy, syy, sy],
        [sx, sy, n],
    ]

    def gauss(m: list[list[float]], b: list[float]) -> list[float]:
        a = [row[:] + [rhs] for row, rhs in zip(m, b)]
        size = len(a)
        for col in range(size):
            pivot = max(range(col, size), key=lambda r: abs(a[r][col]))
            if abs(a[pivot][col]) < 1e-12:
                raise ValueError("대응점들이 일직선입니다 — 서로 떨어진 지점으로 다시 찍으세요")
            a[col], a[pivot] = a[pivot], a[col]
            for row in range(size):
                if row == col:
                    continue
                factor = a[row][col] / a[col][col]
                for k in range(col, size + 1):
                    a[row][k] -= factor * a[col][k]
        return [a[i][size] / a[i][i] for i in range(size)]

    return gauss(matrix, bx), gauss(matrix, by)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--pair",
        action="append",
        required=True,
        metavar='"wx,wy=px,py"',
        help="대응점: SLAM 세계좌표(m)=평면도 픽셀. 3개 이상, 일직선 금지",
    )
    parser.add_argument("--map-id", type=int, default=2, help="library_maps id (기본 2)")
    args = parser.parse_args()

    if len(args.pair) < 3:
        sys.exit("대응점이 %d개 — 아핀 변환은 최소 3개(일직선 아님)가 필요합니다" % len(args.pair))

    pairs = []
    for raw in args.pair:
        world, _, pixel = raw.partition("=")
        wx, wy = (float(v) for v in world.split(","))
        px, py = (float(v) for v in pixel.split(","))
        pairs.append((wx, wy, px, py))

    (a11, a12, tx), (a21, a22, ty) = solve_affine(pairs)

    print("아핀 변환 (픽셀 = A·세계 + t):")
    print(f"  A = [[{a11:.6f}, {a12:.6f}], [{a21:.6f}, {a22:.6f}]]  t = ({tx:.3f}, {ty:.3f})")
    det = a11 * a22 - a12 * a21
    print(f"  행렬식 {det:.3f} ({'반전 포함' if det < 0 else '반전 없음'}), "
          f"평면도 1px = 약 {1.0 / abs(det) ** 0.5:.4f} m")

    print("\n잔차 (대응점별, 픽셀):")
    worst = 0.0
    for wx, wy, px, py in pairs:
        ex = a11 * wx + a12 * wy + tx - px
        ey = a21 * wx + a22 * wy + ty - py
        err = (ex * ex + ey * ey) ** 0.5
        worst = max(worst, err)
        print(f"  world({wx}, {wy}) -> 오차 {err:.1f}px")
    if worst > 10:
        print("  [주의] 최대 오차가 10px를 넘습니다 — 대응점을 다시 찍는 것을 권합니다")

    print("\n-- library_maps 반영 SQL --")
    print(
        "UPDATE library_maps SET\n"
        f"    affine_a11 = {a11:.9f}, affine_a12 = {a12:.9f},\n"
        f"    affine_a21 = {a21:.9f}, affine_a22 = {a22:.9f},\n"
        f"    affine_tx = {tx:.9f}, affine_ty = {ty:.9f}\n"
        f"WHERE id = {args.map_id};"
    )


if __name__ == "__main__":
    main()
