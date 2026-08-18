"""
영상의 시간 범위를 지정해 GIF로 변환하는 도구.

ffmpeg 2-pass 팔레트 방식(palettegen → paletteuse)으로 GIF 화질을 최적화한다.
ffmpeg는 PATH → imageio-ffmpeg 내장 바이너리 순으로 자동 탐색.

사용법:
    python vid2gif.py input.mp4 output.gif --start 24 --end 31
    python vid2gif.py input.mp4 output.gif --start 1:24 --end 1:31 --fps 15 --width 480
"""
import argparse
import os
import shutil
import subprocess
import sys
import tempfile


def find_ffmpeg():
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        return None


def parse_time(s):
    """'24', '24.5', '1:24', '1:02:03' → 초(float)"""
    parts = s.split(":")
    if len(parts) > 3:
        sys.exit(f"시간 형식 오류: {s}")
    sec = 0.0
    for p in parts:
        sec = sec * 60 + float(p)
    return sec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input")
    ap.add_argument("output")
    ap.add_argument("--start", default="0", help="시작 시간 (초 또는 mm:ss)")
    ap.add_argument("--end", default=None, help="끝 시간 (초 또는 mm:ss). 생략 시 영상 끝까지")
    ap.add_argument("--fps", type=float, default=12, help="GIF 프레임레이트 (기본 12)")
    ap.add_argument("--width", type=int, default=480,
                    help="GIF 가로 크기 px, 세로는 비율 유지 (기본 480, 원본 유지는 -1)")
    args = ap.parse_args()

    ffmpeg = find_ffmpeg()
    if ffmpeg is None:
        sys.exit("ffmpeg를 찾을 수 없습니다. `pip install imageio-ffmpeg` 후 다시 실행하세요.")

    start = parse_time(args.start)
    cut = ["-ss", f"{start:.3f}"]
    if args.end is not None:
        end = parse_time(args.end)
        if end <= start:
            sys.exit("끝 시간이 시작 시간보다 앞입니다.")
        cut += ["-t", f"{end - start:.3f}"]

    vf = f"fps={args.fps},scale={args.width}:-1:flags=lanczos"
    palette = os.path.join(tempfile.gettempdir(), "vid2gif_palette.png")

    # 1-pass: 구간의 색상 팔레트 생성
    r = subprocess.run(
        [ffmpeg, "-y", *cut, "-i", args.input,
         "-vf", vf + ",palettegen=stats_mode=diff", palette],
        capture_output=True)
    if r.returncode != 0:
        print(r.stderr.decode(errors="replace")[-800:])
        sys.exit("팔레트 생성 실패")

    # 2-pass: 팔레트를 적용해 GIF 생성
    r = subprocess.run(
        [ffmpeg, "-y", *cut, "-i", args.input, "-i", palette,
         "-lavfi", vf + "[x];[x][1:v]paletteuse=dither=bayer:bayer_scale=4",
         "-loop", "0", args.output],
        capture_output=True)
    if r.returncode != 0:
        print(r.stderr.decode(errors="replace")[-800:])
        sys.exit("GIF 변환 실패")
    os.remove(palette)

    mb = os.path.getsize(args.output) / 1024 / 1024
    print(f"완료: {args.output} ({mb:.1f}MB)")


if __name__ == "__main__":
    main()
