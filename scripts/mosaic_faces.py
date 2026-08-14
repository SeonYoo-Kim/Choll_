r"""디버그 영상·스크린샷의 얼굴을 모자이크하고 오버레이는 원본 그대로 복원한다.

공개용(GitHub Releases 등) 자료를 만들 때 사용. 얼굴만 가리고
Re-ID 디버그 오버레이(배너·ID 라벨·추적 박스·상태줄)는 판독 가능하게 남긴다.

사용법:
    python scripts/mosaic_faces.py <입력> <출력>
    python scripts/mosaic_faces.py img/result.mp4 img/release/result.mp4
    python scripts/mosaic_faces.py img/result15.jpg img/release/result15.jpg

사전 준비:
    pip install opencv-contrib-python      # 4.x 계열 (5.0은 haarcascade 미포함)
    # YuNet 얼굴 탐지 모델을 이 스크립트와 같은 폴더에 둔다:
    curl -L -o scripts/yunet.onnx \\
      https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx
    # ffmpeg (H.264 재인코딩용) — winget install Gyan.FFmpeg

동작 원리
---------
1. 얼굴 탐지: YuNet을 2배 업스케일 프레임에 적용(작은 얼굴 리콜 향상).
   영상은 프레임별 결과를 ±SMOOTH 프레임 합집합으로 적용해 한두 프레임
   탐지 실패로 얼굴이 새는 것을 막는다. 탐지 결과는 .npz로 캐시한다.

2. 오버레이 복원: 오버레이는 렌더러가 화면 위에 **불투명하게** 덧그린
   픽셀이므로, 모자이크 후 그 자리를 원본으로 되돌려도 얼굴이 드러나지 않는다.
   - 채움 막대(배너·라벨)와 테두리 선(추적 박스)을 열림 연산으로 분리한다.
   - 막대는 바운딩 박스 전체를 복원 → 안의 흰 글자까지 살아난다.
   - 테두리 선은 순색 픽셀만 복원 → **박스 내부는 건드리지 않는다**
     (박스 내부를 복원하면 그 안의 얼굴이 노출되므로 절대 금지).

주의: 오버레이 색은 순색이 아니다. H.264 인코딩을 거치면 파랑이
(255,0,0)이 아니라 (252,78,27)로 실측된다. 순색만 기준으로 잡으면
라벨이 마스크에서 통째로 빠져 글자가 모자이크된 채 남는다.
다른 렌더러/코덱 자료에 재사용할 때는 아래 OVERLAY_COLORS를 실측해 갱신할 것
(채도 높은 픽셀의 최빈색을 세어보면 된다).

검증: 눈으로 몇 프레임 보는 것으로는 부족하다. verify_overlay.py로
전 프레임에서 막대 안 흰 글자 픽셀 수를 원본과 비교할 것.
"""

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import cv2
import numpy as np

MODEL = str(Path(__file__).parent / "yunet.onnx")
CACHE_DIR = Path(__file__).parent / ".detcache"

SCORE = 0.5  # YuNet 신뢰도 임계값
UPSCALE = 2.0  # 탐지 전 확대 배율 (작은 얼굴 리콜)
SMOOTH = 6  # 앞뒤 ±N 프레임 탐지 결과를 합집합으로 적용
PAD = 0.35  # 탐지 박스를 사방으로 확장하는 비율
# 얼굴 한 변을 나눌 블록 수. 12로 했더니 블록이 너무 잘아 인물이 식별됐다 (2026-08-14)
MOSAIC = 5
MIN_BLOCK_PX = 8  # 블록 최소 크기 — 작은 얼굴도 이보다 잘게 쪼개지 않는다
TOL = 50  # 오버레이 색 허용 오차 (채널당)
MIN_BAR_AREA = 150  # 이 넓이 미만의 덩어리는 막대로 보지 않음

# 디버그 렌더러가 실제로 그리는 색 (BGR). 앞의 3개는 H.264 인코딩 후 실측값,
# 뒤의 3개는 순색 — 플레이어 스크린샷(jpg)은 색이 더 순수해서 둘 다 필요하다.
OVERLAY_COLORS = [
    (37, 38, 236),  # 빨강 배너 (RECOVERED)
    (38, 219, 58),  # 초록 배너·박스 (TARGET)
    (252, 78, 27),  # 파랑 라벨·박스 (ID)
    (0, 0, 255),
    (0, 255, 0),
    (255, 0, 0),
]

Boxes = list[tuple[int, int, int, int]]


def overlay_restore_mask(img: np.ndarray) -> np.ndarray:
    """복원할 오버레이 영역 마스크 = 채움 막대의 bbox 전체 + 테두리 선 자체."""
    color = np.zeros(img.shape[:2], np.uint8)
    for b, g, r in OVERLAY_COLORS:
        lo = np.array([max(0, b - TOL), max(0, g - TOL), max(0, r - TOL)], np.uint8)
        hi = np.array(
            [min(255, b + TOL), min(255, g + TOL), min(255, r + TOL)], np.uint8
        )
        color |= cv2.inRange(img, lo, hi)

    # 열림으로 얇은 테두리 선을 지우면 채움 막대(배너·라벨)만 남는다
    solid = cv2.morphologyEx(color, cv2.MORPH_OPEN, np.ones((7, 7), np.uint8))
    mask = color.copy()
    count, _, stats, _ = cv2.connectedComponentsWithStats(solid, 8)
    for i in range(1, count):
        x, y, w, h, area = stats[i]
        if area >= MIN_BAR_AREA:
            mask[y : y + h, x : x + w] = 255  # 막대 안의 흰 글자까지 복원
    return mask


def mosaic_faces(img: np.ndarray, boxes: Boxes) -> np.ndarray:
    """얼굴 박스를 모자이크한 뒤 오버레이를 원본으로 되돌린다."""
    height, width = img.shape[:2]
    original = img.copy()
    for x, y, bw, bh in boxes:
        px, py = int(bw * PAD), int(bh * PAD)
        x0, y0 = max(0, x - px), max(0, y - py)
        x1, y1 = min(width, x + bw + px), min(height, y + bh + py)
        roi = img[y0:y1, x0:x1]
        if roi.size == 0:
            continue
        block = max((y1 - y0) // MOSAIC, (x1 - x0) // MOSAIC, MIN_BLOCK_PX)
        mh, mw = max(1, (y1 - y0) // block), max(1, (x1 - x0) // block)
        small = cv2.resize(roi, (mw, mh), interpolation=cv2.INTER_AREA)
        img[y0:y1, x0:x1] = cv2.resize(
            small, (x1 - x0, y1 - y0), interpolation=cv2.INTER_NEAREST
        )

    mask = overlay_restore_mask(original)
    img[mask > 0] = original[mask > 0]
    return img


def detect_faces(detector: "cv2.FaceDetectorYN", frame: np.ndarray) -> Boxes:
    """원본 좌표계 기준 얼굴 박스 목록."""
    height, width = frame.shape[:2]
    big = cv2.resize(
        frame,
        (int(width * UPSCALE), int(height * UPSCALE)),
        interpolation=cv2.INTER_LINEAR,
    )
    _, faces = detector.detect(big)
    if faces is None:
        return []
    return [tuple(int(v / UPSCALE) for v in face[:4]) for face in faces]


def find_ffmpeg() -> str:
    """PATH 또는 winget 설치 경로에서 ffmpeg를 찾는다."""
    found = shutil.which("ffmpeg")
    if found:
        return found
    packages = Path.home() / "AppData/Local/Microsoft/WinGet/Packages"
    for candidate in packages.glob("Gyan.FFmpeg*/**/bin/ffmpeg.exe"):
        return str(candidate)
    raise FileNotFoundError(
        "ffmpeg를 찾을 수 없습니다. winget install Gyan.FFmpeg 로 설치하세요."
    )


def process_image(src: str, dst: str, detector: "cv2.FaceDetectorYN") -> None:
    """이미지 한 장을 모자이크해 저장한다."""
    img = cv2.imdecode(np.fromfile(src, np.uint8), cv2.IMREAD_COLOR)  # 한글 경로 대응
    if img is None:
        raise ValueError(f"이미지를 읽을 수 없습니다: {src}")
    height, width = img.shape[:2]
    detector.setInputSize((int(width * UPSCALE), int(height * UPSCALE)))
    boxes = detect_faces(detector, img)
    encoded = cv2.imencode(
        ".jpg", mosaic_faces(img, boxes), [cv2.IMWRITE_JPEG_QUALITY, 90]
    )[1]
    encoded.tofile(dst)
    print(f"[done] {Path(dst).name}: {width}x{height}, faces={len(boxes)}", flush=True)


def load_or_detect(src: str, detector: "cv2.FaceDetectorYN", total: int) -> list[Boxes]:
    """프레임별 얼굴 박스. 캐시가 있으면 재사용한다(탐지가 가장 오래 걸린다)."""
    CACHE_DIR.mkdir(exist_ok=True)
    cache = CACHE_DIR / (Path(src).stem + ".npz")
    if cache.exists():
        dets = list(np.load(cache, allow_pickle=True)["dets"])
        print(f"  detect cached: {sum(len(d) for d in dets)} faces", flush=True)
        return dets

    dets: list[Boxes] = []
    cap = cv2.VideoCapture(src)
    index = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        dets.append(detect_faces(detector, frame))
        index += 1
        if index % 500 == 0:
            print(f"  detect {index}/{total}", flush=True)
    cap.release()
    np.savez_compressed(cache, dets=np.array(dets, dtype=object))
    print(f"  detect done: {sum(len(d) for d in dets)} faces", flush=True)
    return dets


def process_video(src: str, dst: str, detector: "cv2.FaceDetectorYN") -> None:
    """영상 전체를 모자이크해 H.264 mp4로 저장한다."""
    cap = cv2.VideoCapture(src)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    cap.release()
    print(f"[{Path(src).name}] {width}x{height} {fps:.1f}fps {total}frames", flush=True)

    detector.setInputSize((int(width * UPSCALE), int(height * UPSCALE)))
    dets = load_or_detect(src, detector, total)

    tmp_out = str(Path(tempfile.mkdtemp()) / "raw.mp4")
    writer = cv2.VideoWriter(
        tmp_out, cv2.VideoWriter_fourcc(*"mp4v"), fps, (width, height)
    )
    cap = cv2.VideoCapture(src)
    index = 0
    while True:
        ok, img = cap.read()
        if not ok:
            break
        union: Boxes = []
        for j in range(max(0, index - SMOOTH), min(len(dets), index + SMOOTH + 1)):
            union.extend(dets[j])
        writer.write(mosaic_faces(img, union))
        index += 1
        if index % 500 == 0:
            print(f"  write {index}/{total}", flush=True)
    writer.release()
    cap.release()

    # mp4v는 호환성·용량이 나빠 H.264로 다시 인코딩한다
    subprocess.run(
        [
            find_ffmpeg(),
            "-y",
            "-i",
            tmp_out,
            "-c:v",
            "libx264",
            "-crf",
            "23",
            "-preset",
            "medium",
            "-pix_fmt",
            "yuv420p",
            dst,
        ],
        check=True,
        capture_output=True,
    )
    size_mb = Path(dst).stat().st_size / 1e6
    print(f"[done] {Path(dst).name}: {size_mb:.1f}MB", flush=True)


def main() -> None:
    """CLI 진입점 — 입력 확장자로 이미지/영상을 구분해 처리한다."""
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(1)
    src, dst = sys.argv[1], sys.argv[2]
    if not Path(MODEL).exists():
        raise FileNotFoundError(
            f"YuNet 모델이 없습니다: {MODEL} (사용법 주석의 curl 명령 참조)"
        )
    Path(dst).parent.mkdir(parents=True, exist_ok=True)

    detector = cv2.FaceDetectorYN.create(MODEL, "", (320, 320), SCORE)
    if Path(src).suffix.lower() in (".jpg", ".jpeg", ".png"):
        process_image(src, dst, detector)
    else:
        process_video(src, dst, detector)


if __name__ == "__main__":
    main()
