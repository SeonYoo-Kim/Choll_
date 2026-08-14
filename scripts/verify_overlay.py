"""mosaic_faces.py 결과 검증 — 오버레이 글자가 모자이크로 뭉개지지 않았는지 확인.

사용법:
    python scripts/verify_overlay.py <원본> <모자이크결과>

원본에서 배너·라벨(채움 막대) 영역을 찾아 그 안의 흰 글자 픽셀 수를 세고,
결과 영상의 같은 영역과 비교한다. 비율이 0.7 미만인 프레임이 있으면
글자가 가려진 것이므로 OVERLAY_COLORS 실측값을 다시 확인해야 한다.

정상 범위: 0.8~1.0 (H.264 재인코딩으로 글자 경계가 약간 부드러워져 1.0 미만이 나온다)

눈으로 몇 프레임 보는 검수로는 부족하다 — 모자이크가 실제로 라벨 위에 겹친
프레임에서만 결함이 드러나는데, 그런 프레임을 손으로 골라내기 어렵기 때문이다.
"""

import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from mosaic_faces import overlay_restore_mask  # noqa: E402

SAMPLE_EVERY = 15  # N 프레임마다 검사
MIN_WHITE = 50  # 흰 글자 픽셀이 이보다 적은 프레임은 표본에서 제외
FAIL_RATIO = 0.7


def white_pixels(img: np.ndarray, mask: np.ndarray) -> int:
    """마스크 영역 안의 흰 글자 픽셀 수."""
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    white = (hsv[:, :, 2] > 190) & (hsv[:, :, 1] < 70)
    return int((white & (mask > 0)).sum())


def main() -> None:
    """CLI 진입점 — 표본 프레임의 글자 보존 비율을 집계해 판정한다."""
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(1)
    src, out = sys.argv[1], sys.argv[2]
    cap_src, cap_out = cv2.VideoCapture(src), cv2.VideoCapture(out)

    index = degraded = checked = 0
    worst_ratio, worst_frame = 1.0, -1
    while True:
        ok1, frame_src = cap_src.read()
        ok2, frame_out = cap_out.read()
        if not (ok1 and ok2):
            break
        if index % SAMPLE_EVERY == 0:
            mask = overlay_restore_mask(frame_src)
            if mask.any():
                before = white_pixels(frame_src, mask)
                if before > MIN_WHITE:
                    checked += 1
                    ratio = white_pixels(frame_out, mask) / before
                    if ratio < worst_ratio:
                        worst_ratio, worst_frame = ratio, index
                    if ratio < FAIL_RATIO:
                        degraded += 1
        index += 1
    cap_src.release()
    cap_out.release()

    verdict = "OK" if degraded == 0 else "FAIL"
    print(
        f"[{verdict}] {Path(src).name}: checked={checked} frames, "
        f"degraded={degraded}, worst_ratio={worst_ratio:.2f} @frame {worst_frame}"
    )
    sys.exit(0 if degraded == 0 else 1)


if __name__ == "__main__":
    main()
