"""저장한 지도를 눈으로 보기 좋게 PNG 로 렌더링한다 (좌표 눈금 포함).

## 왜 필요한가

젯슨에 이미지 편집기가 하나도 없다(gimp/krita/pinta 전부 미설치, 2026-08-10 확인).
지도의 어디가 뚫렸는지 보려면 뭔가로 띄워야 하는데, 원본 `.pgm` 은 작고(예: 289x207)
회색조라 화면에서 판별이 어렵다. 이 도구는 확대 + 색 구분 + 좌표 눈금을 넣어
"어디를 칠해야 하는지"를 **미터 좌표로 지목할 수 있게** 만든다.

## 색 규약 (ROS map_server)

    0   = 점유(벽)      -> 검정
    205 = 미관측        -> 회색   ← "뚫린 부분"의 정체
    254 = 자유공간      -> 흰색

미관측은 노란 기가 도는 회색으로 따로 칠해 자유공간과 확실히 구분한다.

## 사용

    python3 map_view.py ~/maps/library_v2.yaml [출력.png] [--scale 4]
    python3 map_view.py ~/maps/library_v2.yaml --ascii     # 터미널에 바로 출력

🔴 **GUI 가 필요 없다.** 이 도구는 화면에 아무것도 띄우지 않고 PNG 파일만 만든다.
   젯슨에 모니터가 없어도 된다. 보는 방법은 둘 중 하나:
     ① 출력 PNG 를 워크스페이스 안에 두고 VS Code 탐색기에서 클릭
        (SSH 원격이어도 노트북 화면에 렌더된다)
     ② `--ascii` — 터미널에 문자로 그린다. 아무것도 설치·전송할 필요가 없다.
"""

import argparse
import os
import sys

import numpy as np
import yaml
from PIL import Image, ImageDraw

#: ROS map_server 의 픽셀 값 규약.
OCCUPIED = 0
UNKNOWN = 205
FREE = 254

#: 렌더링 색 (R, G, B).
COLOR_OCCUPIED = (20, 20, 20)
COLOR_FREE = (250, 250, 250)
COLOR_UNKNOWN = (168, 160, 120)
COLOR_OTHER = (220, 60, 60)      # 규약 밖 값 — 안티앨리어싱 사고를 눈에 띄게
COLOR_GRID = (120, 160, 220)
COLOR_AXIS = (220, 80, 80)


def load_map(yaml_path: str) -> tuple[np.ndarray, dict]:
    """지도 yaml 과 pgm 을 읽는다.

    Args:
        yaml_path: map yaml 경로.

    Returns:
        `(픽셀 배열(H, W) uint8, yaml 딕셔너리)`.

    Raises:
        FileNotFoundError: yaml 또는 이미지 파일이 없을 때.
    """
    with open(yaml_path) as handle:
        meta = yaml.safe_load(handle)
    map_dir = os.path.dirname(os.path.abspath(yaml_path))
    image_path = os.path.join(map_dir, meta["image"])
    if not os.path.isfile(image_path):
        raise FileNotFoundError(image_path)
    pixels = np.array(Image.open(image_path).convert("L"), dtype=np.uint8)
    return pixels, meta


def colorize(pixels: np.ndarray) -> np.ndarray:
    """픽셀 값을 사람이 구분하기 쉬운 RGB 로 바꾼다.

    Args:
        pixels: (H, W) uint8 지도.

    Returns:
        (H, W, 3) uint8 RGB.
    """
    rgb = np.zeros((*pixels.shape, 3), dtype=np.uint8)
    rgb[:] = COLOR_OTHER                       # 규약 밖 값은 빨강으로 튀게 둔다
    rgb[pixels <= 50] = COLOR_OCCUPIED
    rgb[(pixels > 50) & (pixels < 230)] = COLOR_UNKNOWN
    rgb[pixels >= 230] = COLOR_FREE
    return rgb


def render_ascii(pixels: np.ndarray, meta: dict, cols: int) -> None:
    """지도를 터미널에 문자로 그린다 (이미지 뷰어가 없을 때).

    가로:세로 문자 비율이 약 1:2 라 세로를 절반으로 더 줄여야 정사각형으로 보인다.

    Args:
        pixels: (H, W) uint8 지도.
        meta: map yaml 딕셔너리.
        cols: 출력 가로 문자 수.
    """
    height, width = pixels.shape
    resolution = float(meta["resolution"])
    origin_x, origin_y = float(meta["origin"][0]), float(meta["origin"][1])
    step = max(1, int(np.ceil(width / cols)))
    print(f"\n  1문자 = {step}x{step * 2} px = "
          f"{step * resolution:.2f} x {step * 2 * resolution:.2f} m")
    print("  '#'=벽  '.'=자유공간  ' '=미관측\n")

    header = "     " + "".join(
        "|" if (px * step) % (10 * step) == 0 else " "
        for px in range(0, width // step)
    )
    print(header)
    for py in range(0, height, step * 2):
        row = []
        for px in range(0, width, step):
            block = pixels[py:py + step * 2, px:px + step]
            if block.size == 0:
                row.append(" ")
            elif (block <= 50).any():
                row.append("#")
            elif (block >= 230).any():
                row.append(".")
            else:
                row.append(" ")
        y_m = origin_y + (height - py) * resolution
        print(f"{y_m:+5.1f}" + "".join(row))
    x_left = origin_x
    x_right = origin_x + width * resolution
    print(f"\n  가로: x = {x_left:+.2f} m (왼쪽 끝) ~ {x_right:+.2f} m (오른쪽 끝)")
    print("  세로 숫자 = map 프레임 y [m]")


def main() -> None:
    """지도를 확대·착색하고 미터 눈금을 얹어 PNG 로 저장한다."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("map_yaml", help="지도 yaml 경로")
    parser.add_argument("out_png", nargs="?", default=None, help="출력 PNG")
    parser.add_argument("--scale", type=int, default=4, help="확대 배율 (기본 4)")
    parser.add_argument("--grid-m", type=float, default=1.0, help="눈금 간격[m]")
    parser.add_argument("--ascii", action="store_true",
                        help="PNG 대신 터미널에 문자로 그린다 (GUI·뷰어 불필요)")
    parser.add_argument("--cols", type=int, default=110,
                        help="--ascii 의 가로 문자 수 (기본 110)")
    args = parser.parse_args()

    pixels, meta = load_map(args.map_yaml)
    height, width = pixels.shape
    resolution = float(meta["resolution"])
    origin_x, origin_y = float(meta["origin"][0]), float(meta["origin"][1])

    counts = {
        "점유(벽)": int((pixels <= 50).sum()),
        "자유공간": int((pixels >= 230).sum()),
        "미관측": int(((pixels > 50) & (pixels < 230)).sum()),
    }
    total = height * width
    print(f"지도 {width}x{height} @ {resolution:.3f} m "
          f"= {width * resolution:.2f} x {height * resolution:.2f} m")
    print(f"origin = ({origin_x}, {origin_y})")
    for name, value in counts.items():
        print(f"  {name:10s} {value:7d} ({value / total * 100:5.1f}%)")

    if args.ascii:
        render_ascii(pixels, meta, args.cols)
        return

    image = Image.fromarray(colorize(pixels), mode="RGB").resize(
        (width * args.scale, height * args.scale), Image.NEAREST
    )
    draw = ImageDraw.Draw(image)

    # 눈금은 map 프레임의 정수 미터마다. 픽셀 변환은 ROS 규약을 그대로 따른다:
    #   px = (x - origin_x) / resolution,  py = height - (y - origin_y) / resolution
    x_start = np.ceil(origin_x / args.grid_m) * args.grid_m
    x_value = x_start
    while x_value < origin_x + width * resolution:
        px = (x_value - origin_x) / resolution * args.scale
        color = COLOR_AXIS if abs(x_value) < 1e-6 else COLOR_GRID
        draw.line([(px, 0), (px, image.height)], fill=color, width=1)
        draw.text((px + 2, 2), f"{x_value:.0f}", fill=color)
        x_value += args.grid_m

    y_start = np.ceil(origin_y / args.grid_m) * args.grid_m
    y_value = y_start
    while y_value < origin_y + height * resolution:
        py = (height - (y_value - origin_y) / resolution) * args.scale
        color = COLOR_AXIS if abs(y_value) < 1e-6 else COLOR_GRID
        draw.line([(0, py), (image.width, py)], fill=color, width=1)
        draw.text((2, py + 2), f"{y_value:.0f}", fill=color)
        y_value += args.grid_m

    out = args.out_png or os.path.splitext(args.map_yaml)[0] + "_view.png"
    image.save(out)
    print(f"\n저장: {out}  ({image.width}x{image.height}, {args.scale}배 확대)")
    print("  검정=벽  회색=미관측  흰색=자유공간  빨강=규약 밖 값(있으면 문제)")
    print(f"  파란 눈금 {args.grid_m:.0f} m 간격, 빨간 선 = 0 축")
    if counts["미관측"] / total > 0.5:
        print("\n  ⚠️ 미관측이 절반을 넘는다 — 아직 덜 돈 상태다. "
              "칠하기 전에 더 주행하는 편이 낫다.")


if __name__ == "__main__":
    sys.exit(main())
