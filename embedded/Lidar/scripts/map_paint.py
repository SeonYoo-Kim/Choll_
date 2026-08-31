"""저장한 지도의 뚫린 벽을 좌표로 메운다 (GIMP 대용, 헤드리스).

## 왜 이 방식인가

지도의 구멍은 SLAM 이 틀린 게 아니라 **라이다가 그 자리를 못 본 것**이다
(2026-08-10 실측: 애매한 셀 0%, 미관측 65%). 유리·거울·검은 벽은 몇 번을
지나가도 반사가 안 와 원리적으로 안 채워진다. 그런 구간은 사람이 "여기는
벽이다"라고 직접 찍어 주는 게 표준 관행이다.

젯슨에 이미지 편집기가 없어(gimp 등 전부 미설치) 좌표 기반 CLI 로 만들었다.
마우스보다 오히려 정확하다 — **미터 좌표**로 찍으므로 BE 구역 좌표와 같은
기준에서 이야기할 수 있다.

## 🔴 안전 규칙

- **`.yaml` 은 절대 건드리지 않는다.** `resolution`·`origin` 이 바뀌면 BE 에
  등록된 구역 폴리곤 좌표가 전부 틀어진다.
- 칠하는 값은 **정확히 0**(점유). 안티앨리어싱으로 중간값이 생기면 costmap 이
  애매하게 읽는다. 이 도구는 정수만 쓰므로 중간값이 생기지 않는다.
- 원본은 `.pgm.bak` 으로 자동 백업한다.

## 사용

    # ① 먼저 눈으로 확인
    python3 map_view.py ~/maps/library_v2.yaml

    # ② 벽 그리기 (미터 좌표, map 프레임)
    python3 map_paint.py ~/maps/library_v2.yaml --line 1.2 -0.4 3.8 -0.4
    python3 map_paint.py ~/maps/library_v2.yaml --rect -2.0 1.0 -1.6 3.5

    # ③ 지우기 (잘못 칠했을 때 자유공간으로)
    python3 map_paint.py ~/maps/library_v2.yaml --line 1.2 -0.4 3.8 -0.4 --erase

    # ④ 되돌리기
    python3 map_paint.py ~/maps/library_v2.yaml --restore

`--line` 은 `x1 y1 x2 y2`, `--rect` 는 `x1 y1 x2 y2` (반대 모서리) 이고
여러 번 줄 수 있다. 두께는 `--width`(픽셀, 기본 2 = 10 cm).
"""

import argparse
import os
import shutil
import sys

import numpy as np
import yaml
from PIL import Image, ImageDraw

OCCUPIED = 0
FREE = 254


def map_to_pixel(
    x: float, y: float, meta: dict, height: int
) -> tuple[int, int]:
    """Convert map-frame metres to image pixel coordinates.

    map 프레임 미터 좌표를 이미지 픽셀 좌표로 바꾼다.

    ROS map_server 규약: 이미지의 y 축은 map 의 y 축과 **반대**다.

    Args:
        x: map 프레임 x [m].
        y: map 프레임 y [m].
        meta: map yaml 딕셔너리 (resolution, origin 사용).
        height: 이미지 높이 [px].

    Returns:
        `(px, py)` 정수 픽셀 좌표.
    """
    resolution = float(meta["resolution"])
    origin_x, origin_y = float(meta["origin"][0]), float(meta["origin"][1])
    px = int(round((x - origin_x) / resolution))
    py = int(round(height - (y - origin_y) / resolution))
    return px, py


def main() -> int:
    """인자대로 지도에 선/사각형을 그리고 저장한다.

    Returns:
        종료 코드 (0=성공).
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("map_yaml", help="지도 yaml 경로")
    parser.add_argument("--line", nargs=4, type=float, action="append",
                        metavar=("X1", "Y1", "X2", "Y2"),
                        help="선 (미터). 여러 번 지정 가능")
    parser.add_argument("--rect", nargs=4, type=float, action="append",
                        metavar=("X1", "Y1", "X2", "Y2"),
                        help="채운 사각형 (미터). 여러 번 지정 가능")
    parser.add_argument("--width", type=int, default=2,
                        help="선 두께[px] (기본 2 = 해상도 0.05 기준 10cm)")
    parser.add_argument("--erase", action="store_true",
                        help="점유(0) 대신 자유공간(254)으로 칠한다")
    parser.add_argument("--restore", action="store_true",
                        help=".pgm.bak 에서 원본을 되돌린다")
    args = parser.parse_args()

    with open(args.map_yaml) as handle:
        meta = yaml.safe_load(handle)
    map_dir = os.path.dirname(os.path.abspath(args.map_yaml))
    image_path = os.path.join(map_dir, meta["image"])
    backup_path = image_path + ".bak"

    if args.restore:
        if not os.path.isfile(backup_path):
            print(f"🔴 백업이 없다: {backup_path}")
            return 1
        shutil.copy2(backup_path, image_path)
        print(f"✅ 원본 복구: {backup_path} -> {image_path}")
        return 0

    if not args.line and not args.rect:
        print("🔴 --line 또는 --rect 를 하나 이상 지정할 것 (--help 참조)")
        return 2

    if not os.path.isfile(backup_path):
        shutil.copy2(image_path, backup_path)
        print(f"백업 생성: {backup_path}")

    image = Image.open(image_path).convert("L")
    height = image.height
    draw = ImageDraw.Draw(image)
    value = FREE if args.erase else OCCUPIED
    label = "자유공간(254)" if args.erase else "점유/벽(0)"

    for x1, y1, x2, y2 in args.line or []:
        p1 = map_to_pixel(x1, y1, meta, height)
        p2 = map_to_pixel(x2, y2, meta, height)
        # ImageDraw 는 'L' 모드에서 안티앨리어싱을 하지 않는다 -> 중간값 안 생김
        draw.line([p1, p2], fill=value, width=args.width)
        print(f"  선  ({x1:+.2f},{y1:+.2f}) -> ({x2:+.2f},{y2:+.2f}) m"
              f"   px {p1} -> {p2}   {label}")

    for x1, y1, x2, y2 in args.rect or []:
        p1 = map_to_pixel(x1, y1, meta, height)
        p2 = map_to_pixel(x2, y2, meta, height)
        box = [min(p1[0], p2[0]), min(p1[1], p2[1]),
               max(p1[0], p2[0]), max(p1[1], p2[1])]
        draw.rectangle(box, fill=value)
        print(f"  사각 ({x1:+.2f},{y1:+.2f}) -> ({x2:+.2f},{y2:+.2f}) m"
              f"   px {box}   {label}")

    image.save(image_path)

    pixels = np.array(image, dtype=np.uint8)
    stray = int(((pixels > 50) & (pixels < 230) & (pixels != 205)).sum())
    print(f"\n저장: {image_path}")
    print(f"  점유 {int((pixels <= 50).sum())} / "
          f"자유 {int((pixels >= 230).sum())} / "
          f"미관측 {int((pixels == 205).sum())}")
    if stray:
        print(f"  🔴 규약 밖 중간값 {stray}개 — costmap 이 애매하게 읽는다")
    else:
        print("  ✅ 중간값 없음 (0/205/254 만 존재)")
    print("  ⚠️ .yaml 은 건드리지 않았다 — resolution/origin 유지")
    return 0


if __name__ == "__main__":
    sys.exit(main())
