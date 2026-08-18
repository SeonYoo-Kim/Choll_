"""
영상 얼굴 모자이크 파이프라인
- 검출: YuNet (OpenCV cv2.FaceDetectorYN) — 얼굴 전용 검출기
- 안정화: 2-pass 방식. 1차로 전 프레임 검출 → 트랙 구성(IoU 매칭) →
  검출이 끊긴 구간은 앞뒤 박스로 보간 → 2차로 모자이크 렌더링
- 모자이크: 박스를 마진만큼 확장 후 다운스케일-업스케일(픽셀화)

사용법:
    python face_mosaic.py input.mp4 output.mp4 [--conf 0.6] [--margin 0.25]
"""
import argparse
import os
import shutil
import subprocess
import sys

import cv2
import numpy as np


def find_ffmpeg():
    """PATH의 ffmpeg → imageio-ffmpeg 내장 바이너리 순으로 탐색."""
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        return None

# ---------------- 검출 ----------------

def detect_all_frames(video_path, model_path, conf):
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        sys.exit(f"영상 열기 실패: {video_path}")
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0

    det = cv2.FaceDetectorYN.create(model_path, "", (w, h), conf, 0.3, 5000)
    det.setInputSize((w, h))

    per_frame = []  # frame index -> list of (x, y, w, h, score)
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        _, faces = det.detect(frame)
        boxes = []
        if faces is not None:
            for f in faces:
                x, y, bw, bh, score = f[0], f[1], f[2], f[3], f[-1]
                boxes.append((float(x), float(y), float(bw), float(bh), float(score)))
        per_frame.append(boxes)
    cap.release()
    return per_frame, (w, h, fps)


# ---------------- 트래킹 + 보간 ----------------

def iou(a, b):
    ax1, ay1, ax2, ay2 = a[0], a[1], a[0] + a[2], a[1] + a[3]
    bx1, by1, bx2, by2 = b[0], b[1], b[0] + b[2], b[1] + b[3]
    ix = max(0, min(ax2, bx2) - max(ax1, bx1))
    iy = max(0, min(ay2, by2) - max(ay1, by1))
    inter = ix * iy
    union = a[2] * a[3] + b[2] * b[3] - inter
    return inter / union if union > 0 else 0.0


def build_tracks(per_frame, iou_thresh=0.25, max_gap=15,
                 min_hits=3, min_hit_ratio=0.35, min_median_score=0.72,
                 pad=6):
    """검출 박스들을 IoU로 이어붙여 트랙 생성. 끊긴 구간은 선형 보간으로 채움.

    트랙 단위 오탐 필터링:
    - min_hits: 실제 검출(보간 제외)이 이 횟수 미만이면 단발성 오탐으로 제거
    - min_hit_ratio: 트랙 구간 대비 실제 검출 비율. 진짜 얼굴은 거의 매
      프레임 검출되지만(0.8~1.0), 무늬/프린팅 오탐은 띄엄띄엄 걸림(<0.3)
    - min_median_score: 트랙의 검출 점수 중앙값. 오탐은 높게 나와도
      일관되게 높지 않음
    - pad: 필터를 통과한 트랙의 시작/끝을 이 프레임 수만큼 연장
      (검출기가 몇 프레임 늦게 잡기 시작해도 얼굴이 노출되지 않도록)
    """
    tracks = []          # 각 트랙: {'boxes': {fi: box}, 'hits': [(fi, score)]}
    active = []          # (track, last_frame, last_box)

    for fi, boxes in enumerate(per_frame):
        used = [False] * len(boxes)
        next_active = []
        for track, last_fi, last_box in active:
            if fi - last_fi > max_gap:
                continue  # 트랙 종료
            best_j, best_iou = -1, iou_thresh
            for j, b in enumerate(boxes):
                if used[j]:
                    continue
                v = iou(last_box, b)
                if v > best_iou:
                    best_iou, best_j = v, j
            if best_j >= 0:
                used[best_j] = True
                b = boxes[best_j][:4]
                # 끊긴 구간 선형 보간
                for g in range(last_fi + 1, fi):
                    t = (g - last_fi) / (fi - last_fi)
                    track['boxes'][g] = tuple(
                        last_box[k] * (1 - t) + b[k] * t for k in range(4))
                track['boxes'][fi] = b
                track['hits'].append((fi, boxes[best_j][4]))
                next_active.append((track, fi, b))
            else:
                next_active.append((track, last_fi, last_box))
        # 매칭 안 된 검출 → 새 트랙
        for j, b in enumerate(boxes):
            if not used[j]:
                t = {'boxes': {fi: b[:4]}, 'hits': [(fi, b[4])]}
                tracks.append(t)
                next_active.append((t, fi, b[:4]))
        active = next_active

    # 트랙 품질 필터링 + 프레임별 박스로 변환
    n = len(per_frame)
    final = [[] for _ in range(n)]
    kept = 0
    for t in tracks:
        hits = t['hits']
        if len(hits) < min_hits:
            continue
        first, last = hits[0][0], hits[-1][0]
        span = last - first + 1
        hit_ratio = len(hits) / span
        scores = sorted(s for _, s in hits)
        median = scores[len(scores) // 2]
        if hit_ratio < min_hit_ratio or median < min_median_score:
            continue
        kept += 1
        for fi, b in t['boxes'].items():
            final[fi].append(b)
        # 트랙 앞뒤 패딩 (첫/마지막 박스 복제)
        fb, lb = t['boxes'][first], t['boxes'][last]
        for g in range(max(0, first - pad), first):
            final[g].append(fb)
        for g in range(last + 1, min(n, last + 1 + pad)):
            final[g].append(lb)
    print(f"    트랙 {len(tracks)}개 중 {kept}개 유지 (오탐 필터링)")
    return final


# ---------------- 모자이크 렌더링 ----------------

def overlay_mask(frame):
    """영상에 이미 그려진 디버그 오버레이(순수 원색 라벨/박스 + 내부 흰 글씨)
    픽셀 마스크. 이 영역은 모자이크에서 제외해 라벨 가독성을 유지한다."""
    b, g, r = cv2.split(frame.astype(np.int16))
    pure = (
        ((g > 180) & (r < 90) & (b < 90)) |   # 초록 (TARGET 라벨/박스)
        ((b > 180) & (r < 90) & (g < 110)) |  # 파랑 (ID 라벨/박스)
        ((r > 180) & (g < 90) & (b < 90))     # 빨강 (RECOVERED 배너)
    ).astype(np.uint8) * 255
    # 라벨 배경 안의 흰 글씨까지 포함되도록 닫힘 연산으로 구멍 메움
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (25, 25))
    return cv2.morphologyEx(pure, cv2.MORPH_CLOSE, kernel)


def mosaic_region(frame, x, y, w, h, block=14, protect=None):
    H, W = frame.shape[:2]
    x1, y1 = max(0, int(x)), max(0, int(y))
    x2, y2 = min(W, int(x + w)), min(H, int(y + h))
    if x2 - x1 < 2 or y2 - y1 < 2:
        return
    roi = frame[y1:y2, x1:x2]
    small_w = max(1, (x2 - x1) // block)
    small_h = max(1, (y2 - y1) // block)
    small = cv2.resize(roi, (small_w, small_h), interpolation=cv2.INTER_LINEAR)
    mosaic = cv2.resize(
        small, (x2 - x1, y2 - y1), interpolation=cv2.INTER_NEAREST)
    if protect is not None:
        m = protect[y1:y2, x1:x2] > 0
        mosaic[m] = roi[m]  # 오버레이 픽셀은 원본 유지
    frame[y1:y2, x1:x2] = mosaic


def render(video_path, out_path, boxes_per_frame, margin, protect_overlay=False):
    cap = cv2.VideoCapture(video_path)
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    tmp = out_path + ".noaudio.mp4"
    vw = cv2.VideoWriter(tmp, cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))

    fi = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if fi < len(boxes_per_frame) and boxes_per_frame[fi]:
            protect = overlay_mask(frame) if protect_overlay else None
            for (bx, by, bw, bh) in boxes_per_frame[fi]:
                mx, my = bw * margin, bh * margin
                mosaic_region(frame, bx - mx, by - my,
                              bw + 2 * mx, bh + 2 * my, protect=protect)
        vw.write(frame)
        fi += 1
    cap.release()
    vw.release()

    # H.264 재인코딩 + 원본 오디오 복사 (재생 호환성)
    ffmpeg = find_ffmpeg()
    if ffmpeg is None:
        # ffmpeg 없으면 재인코딩/오디오 병합 생략 (mp4v, 무음)
        shutil.move(tmp, out_path)
        print("경고: ffmpeg를 찾지 못해 오디오 없이 저장했습니다. "
              "`pip install imageio-ffmpeg` 하면 오디오가 유지됩니다.")
        return
    r = subprocess.run(
        [ffmpeg, "-y", "-i", tmp, "-i", video_path,
         "-map", "0:v", "-map", "1:a?", "-c:v", "libx264",
         "-pix_fmt", "yuv420p", "-crf", "20", "-c:a", "copy", out_path],
        capture_output=True)
    if r.returncode != 0:
        print(r.stderr.decode(errors="replace")[-800:])
        sys.exit("ffmpeg 인코딩 실패")
    os.remove(tmp)


IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
VIDEO_EXTS = {".mp4", ".avi", ".mov", ".mkv", ".webm", ".wmv"}


def process_image(in_path, out_path, model_path, conf, margin,
                  protect_overlay=False):
    """단일 이미지 처리. 트랙 필터링이 불가능하므로 검출 결과를 그대로 사용
    (오탐이 생기면 --conf를 0.7~0.8로 올려서 조절)."""
    img = cv2.imread(in_path)
    if img is None:
        sys.exit(f"이미지 열기 실패: {in_path}")
    h, w = img.shape[:2]
    det = cv2.FaceDetectorYN.create(model_path, "", (w, h), conf, 0.3, 5000)
    det.setInputSize((w, h))
    _, faces = det.detect(img)
    protect = overlay_mask(img) if protect_overlay else None
    n = 0
    if faces is not None:
        for f in faces:
            bx, by, bw, bh = f[0], f[1], f[2], f[3]
            mx, my = bw * margin, bh * margin
            mosaic_region(img, bx - mx, by - my,
                          bw + 2 * mx, bh + 2 * my, protect=protect)
            n += 1
    cv2.imwrite(out_path, img)
    print(f"완료: {out_path} (얼굴 {n}개 모자이크)")


def process_video(in_path, out_path, args):
    print("1/3 전 프레임 얼굴 검출 중...")
    per_frame, (w, h, fps) = detect_all_frames(in_path, args.model, args.conf)
    raw = sum(len(b) for b in per_frame)
    print(f"    {len(per_frame)}프레임, 원시 검출 {raw}건")

    print("2/3 트랙 구성 + 끊김 보간...")
    final = build_tracks(per_frame, max_gap=args.max_gap)
    covered = sum(1 for b in final if b)
    print(f"    모자이크 적용 프레임: {covered}/{len(final)}, "
          f"박스 총 {sum(len(b) for b in final)}건")

    print("3/3 모자이크 렌더링...")
    render(in_path, out_path, final, args.margin,
           protect_overlay=args.protect_overlay)
    print(f"완료: {out_path}")


def process_folder(in_dir, out_dir, args):
    """폴더 안의 모든 이미지/영상을 일괄 모자이크 처리."""
    os.makedirs(out_dir, exist_ok=True)
    same_dir = os.path.abspath(in_dir) == os.path.abspath(out_dir)
    targets = []
    for name in sorted(os.listdir(in_dir)):
        ext = os.path.splitext(name)[1].lower()
        if ext in IMAGE_EXTS or ext in VIDEO_EXTS:
            targets.append(name)
    if not targets:
        sys.exit(f"처리할 이미지/영상이 없습니다: {in_dir}")

    print(f"대상 {len(targets)}개 파일 (입력 폴더: {in_dir})")
    done, failed = 0, []
    for i, name in enumerate(targets, 1):
        stem, ext = os.path.splitext(name)
        # 입력 폴더 == 출력 폴더면 원본 보호를 위해 _mosaic 접미사
        out_name = f"{stem}_mosaic{ext}" if same_dir else name
        in_path = os.path.join(in_dir, name)
        out_path = os.path.join(out_dir, out_name)
        print(f"\n[{i}/{len(targets)}] {name}")
        try:
            if ext.lower() in IMAGE_EXTS:
                process_image(in_path, out_path, args.model,
                              args.conf, args.margin, args.protect_overlay)
            else:
                process_video(in_path, out_path, args)
            done += 1
        except SystemExit as e:
            print(f"    실패: {e}")
            failed.append(name)
    print(f"\n일괄 처리 완료: 성공 {done} / 실패 {len(failed)}")
    if failed:
        print("실패 목록: " + ", ".join(failed))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input", help="입력 영상/이미지 파일 또는 폴더")
    ap.add_argument("output", help="출력 파일 또는 폴더(입력이 폴더인 경우)")
    ap.add_argument("--model", default="yunet.onnx")
    ap.add_argument("--conf", type=float, default=0.6,
                    help="검출 confidence threshold")
    ap.add_argument("--margin", type=float, default=0.25,
                    help="박스 확장 비율 (0.25 = 25%%)")
    ap.add_argument("--max-gap", type=int, default=15,
                    help="검출 끊김 보간 최대 프레임 수")
    ap.add_argument("--protect-overlay", action="store_true",
                    help="영상에 이미 그려진 원색 라벨/박스 오버레이를 "
                         "모자이크에서 제외")
    args = ap.parse_args()

    # 폴더 입력 → 일괄 처리
    if os.path.isdir(args.input):
        process_folder(args.input, args.output, args)
        return
    # 이미지 입력 → 단일 이미지 모드
    if os.path.splitext(args.input)[1].lower() in IMAGE_EXTS:
        process_image(args.input, args.output, args.model,
                      args.conf, args.margin, args.protect_overlay)
        return
    # 그 외 → 영상 모드
    process_video(args.input, args.output, args)


if __name__ == "__main__":
    main()
