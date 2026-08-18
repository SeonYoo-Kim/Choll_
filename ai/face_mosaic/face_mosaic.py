"""
영상 얼굴 모자이크 파이프라인 (CUDA 가속 + tqdm 진행률 + 2K->1K 리사이징 적용)
"""
import argparse
import os
import shutil
import subprocess
import sys

import cv2
import numpy as np
from tqdm import tqdm

def find_ffmpeg():
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        return None

# ---------------- 해상도 리사이즈 유틸리티 ----------------

def get_scaled_size(w, h, threshold=2000, target=1024):
    """
    원본 해상도의 최대 길이가 threshold(2K: 2000) 이상이면, 
    최대 길이를 target(1K: 1024)에 맞춰 비율대로 줄인 해상도를 반환합니다.
    """
    max_dim = max(w, h)
    if max_dim >= threshold:
        scale = target / max_dim
        # 영상 코덱 호환성을 위해 짝수로 맞춤
        new_w = int(w * scale) // 2 * 2
        new_h = int(h * scale) // 2 * 2
        return new_w, new_h
    return int(w), int(h)

# ---------------- 검출 ----------------

def detect_all_frames(video_path, model_path, conf, use_cuda=True):
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        sys.exit(f"영상 열기 실패: {video_path}")
    
    orig_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    orig_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    # 2K 이상 영상 1K로 리사이즈 대상 해상도 구하기
    target_w, target_h = get_scaled_size(orig_w, orig_h)
    if target_w != orig_w:
        print(f"    ▶ 고해상도 감지: {orig_w}x{orig_h} -> {target_w}x{target_h} (1K) 해상도로 다운스케일하여 처리합니다.")

    # GPU(CUDA) 사용 설정
    backend = cv2.dnn.DNN_BACKEND_CUDA if use_cuda else cv2.dnn.DNN_BACKEND_DEFAULT
    target = cv2.dnn.DNN_TARGET_CUDA if use_cuda else cv2.dnn.DNN_TARGET_CPU

    det = cv2.FaceDetectorYN.create(model_path, "", (target_w, target_h), conf, 0.3, 5000, backend, target)
    det.setInputSize((target_w, target_h))

    per_frame = []
    
    with tqdm(total=total_frames, desc="1/3 얼굴 검출", unit="프레임") as pbar:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            
            # 리사이즈가 필요한 경우 프레임 축소
            if target_w != orig_w:
                frame = cv2.resize(frame, (target_w, target_h), interpolation=cv2.INTER_AREA)

            _, faces = det.detect(frame)
            boxes = []
            if faces is not None:
                for f in faces:
                    x, y, bw, bh, score = f[0], f[1], f[2], f[3], f[-1]
                    boxes.append((float(x), float(y), float(bw), float(bh), float(score)))
            per_frame.append(boxes)
            pbar.update(1)

    cap.release()
    return per_frame, (target_w, target_h)


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
    tracks = []
    active = []

    for fi, boxes in tqdm(enumerate(per_frame), total=len(per_frame), desc="2/3 트랙 구성", unit="프레임"):
        used = [False] * len(boxes)
        next_active = []
        for track, last_fi, last_box in active:
            if fi - last_fi > max_gap:
                continue
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
                for g in range(last_fi + 1, fi):
                    t = (g - last_fi) / (fi - last_fi)
                    track['boxes'][g] = tuple(
                        last_box[k] * (1 - t) + b[k] * t for k in range(4))
                track['boxes'][fi] = b
                track['hits'].append((fi, boxes[best_j][4]))
                next_active.append((track, fi, b))
            else:
                next_active.append((track, last_fi, last_box))
        for j, b in enumerate(boxes):
            if not used[j]:
                t = {'boxes': {fi: b[:4]}, 'hits': [(fi, b[4])]}
                tracks.append(t)
                next_active.append((t, fi, b[:4]))
        active = next_active

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
        fb, lb = t['boxes'][first], t['boxes'][last]
        for g in range(max(0, first - pad), first):
            final[g].append(fb)
        for g in range(last + 1, min(n, last + 1 + pad)):
            final[g].append(lb)
            
    print(f"    ▶ 트랙 {len(tracks)}개 중 {kept}개 유지 (오탐 필터링 완료)")
    return final


# ---------------- 모자이크 렌더링 ----------------

def overlay_mask(frame):
    b, g, r = cv2.split(frame.astype(np.int16))
    pure = (
        ((g > 180) & (r < 90) & (b < 90)) |
        ((b > 180) & (r < 90) & (g < 110)) |
        ((r > 180) & (g < 90) & (b < 90))
    ).astype(np.uint8) * 255
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
        mosaic[m] = roi[m]
    frame[y1:y2, x1:x2] = mosaic

def render(video_path, out_path, boxes_per_frame, margin, target_size, protect_overlay=False):
    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    orig_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    orig_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    
    tmp = out_path + ".noaudio.mp4"
    # 타겟(리사이즈된) 해상도로 비디오 라이터 초기화
    vw = cv2.VideoWriter(tmp, cv2.VideoWriter_fourcc(*"mp4v"), fps, target_size)

    fi = 0
    with tqdm(total=total_frames, desc="3/3 영상 렌더링", unit="프레임") as pbar:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
                
            # 원본 크기가 리사이즈 크기와 다르면 프레임 축소 적용
            if (orig_w, orig_h) != target_size:
                frame = cv2.resize(frame, target_size, interpolation=cv2.INTER_AREA)

            if fi < len(boxes_per_frame) and boxes_per_frame[fi]:
                protect = overlay_mask(frame) if protect_overlay else None
                for (bx, by, bw, bh) in boxes_per_frame[fi]:
                    mx, my = bw * margin, bh * margin
                    mosaic_region(frame, bx - mx, by - my,
                                  bw + 2 * mx, bh + 2 * my, protect=protect)
            vw.write(frame)
            fi += 1
            pbar.update(1)
            
    cap.release()
    vw.release()

    ffmpeg = find_ffmpeg()
    if ffmpeg is None:
        shutil.move(tmp, out_path)
        print("경고: ffmpeg를 찾지 못해 오디오 없이 저장했습니다.")
        return
        
    print("    ▶ FFmpeg 오디오 병합 및 H.264 인코딩 중...")
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
                  protect_overlay=False, use_cuda=True):
    img = cv2.imread(in_path)
    if img is None:
        sys.exit(f"이미지 열기 실패: {in_path}")
    orig_h, orig_w = img.shape[:2]
    
    # 2K 이상 이미지도 동일하게 1K로 리사이즈
    target_w, target_h = get_scaled_size(orig_w, orig_h)
    if (orig_w, orig_h) != (target_w, target_h):
        img = cv2.resize(img, (target_w, target_h), interpolation=cv2.INTER_AREA)
        print(f"    ▶ 이미지 해상도 다운스케일: {orig_w}x{orig_h} -> {target_w}x{target_h}")
    
    backend = cv2.dnn.DNN_BACKEND_CUDA if use_cuda else cv2.dnn.DNN_BACKEND_DEFAULT
    target = cv2.dnn.DNN_TARGET_CUDA if use_cuda else cv2.dnn.DNN_TARGET_CPU
    
    det = cv2.FaceDetectorYN.create(model_path, "", (target_w, target_h), conf, 0.3, 5000, backend, target)
    det.setInputSize((target_w, target_h))
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
    per_frame, target_size = detect_all_frames(in_path, args.model, args.conf, args.use_cuda)[:2]
    raw = sum(len(b) for b in per_frame)
    print(f"    ▶ 원시 검출 {raw}건 완료\n")

    final = build_tracks(per_frame, max_gap=args.max_gap)
    covered = sum(1 for b in final if b)
    print(f"    ▶ 모자이크 적용: {covered}/{len(final)}프레임, 박스 총 {sum(len(b) for b in final)}건\n")

    render(in_path, out_path, final, args.margin, target_size=target_size, protect_overlay=args.protect_overlay)
    print(f"\n최종 완료: {out_path}")

def process_folder(in_dir, out_dir, args):
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
        out_name = f"{stem}_mosaic{ext}" if same_dir else name
        in_path = os.path.join(in_dir, name)
        out_path = os.path.join(out_dir, out_name)
        
        print("-" * 50)
        print(f"[{i}/{len(targets)}] 파일 처리 중: {name}")
        
        try:
            if ext.lower() in IMAGE_EXTS:
                process_image(in_path, out_path, args.model,
                              args.conf, args.margin, args.protect_overlay, args.use_cuda)
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
    ap.add_argument("--conf", type=float, default=0.6, help="검출 confidence threshold")
    ap.add_argument("--margin", type=float, default=0.25, help="박스 확장 비율 (0.25 = 25%%)")
    ap.add_argument("--max-gap", type=int, default=15, help="검출 끊김 보간 최대 프레임 수")
    ap.add_argument("--protect-overlay", action="store_true", help="오버레이 보호")
    ap.add_argument("--use-cuda", action="store_true", default=True, help="GPU 가속 사용")
    
    args = ap.parse_args()

    # 윈도우 환경에서 파이썬 3.8+ CUDA DLL 로드 에러 방지를 위한 땜빵 처리
    if args.use_cuda and os.name == 'nt':
        import sys
        if sys.version_info >= (3, 8):
            # 사용중인 CUDA 버전에 맞게 수정하셔도 됩니다.
            cuda_path = r"C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.8\bin"
            if os.path.exists(cuda_path):
                os.add_dll_directory(cuda_path)

    if os.path.isdir(args.input):
        process_folder(args.input, args.output, args)
        return
    if os.path.splitext(args.input)[1].lower() in IMAGE_EXTS:
        process_image(args.input, args.output, args.model,
                      args.conf, args.margin, args.protect_overlay, args.use_cuda)
        return
    process_video(args.input, args.output, args)

if __name__ == "__main__":
    main()